"""Orientation-field registration via complex cross-correlation.

Ridge orientation theta is encoded as a complex field  F = coherence * exp(2i*theta).
When the image rotates by phi, orientations rotate too, so the template's complex
values are multiplied by exp(2i*phi) in addition to rotating the pixel grid.
For each (scale, phi) we FFT-cross-correlate OCT template against the immuno field;
the correlation peak gives the translation and a matching score. Best over all
(scale, phi) -> coarse transform, disambiguate 180deg flip by pore inliers, refine.
"""
import cv2, numpy as np, os, time
from numpy.fft import fft2, ifft2
from scipy.spatial import cKDTree
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

oct_g = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
imm_bgr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))
imm_g = imm_bgr[:, :, 2]

O = np.load(os.path.join(OUT, "oct_pts.npy")).astype(float)[:, ::-1].copy()
I = np.load(os.path.join(OUT, "imm_pts.npy")).astype(float)[:, ::-1].copy()
imm_tree = cKDTree(I)

DS = 0.25  # work resolution factor


def field(gray, valid=None):
    th, coh = orientation_field(gray, sigma_grad=1.5, sigma_tensor=8.0)
    F = coh * np.exp(2j * th)
    if valid is not None:
        F = F * valid
    small = cv2.resize(np.stack([F.real, F.imag], -1), None, fx=DS, fy=DS,
                       interpolation=cv2.INTER_AREA)
    return small[..., 0] + 1j * small[..., 1]


# immuno validity mask (print body) reused from detect logic
blur = cv2.GaussianBlur(imm_g, (0, 0), 25)
m = (blur > np.percentile(blur, 85)).astype(np.uint8)
nlab, lab, stats, _ = cv2.connectedComponentsWithStats(m)
big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
imm_valid = (lab == big).astype(np.float32)
imm_valid = cv2.morphologyEx(imm_valid, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))

oct_valid = (oct_g > 25).astype(np.float32)
oct_valid = cv2.erode(oct_valid, np.ones((11, 11), np.uint8))

IF = field(imm_g, imm_valid)
OF_full = field(oct_g, oct_valid)
Hh, Ww = IF.shape
print("work sizes: IF", IF.shape, "OF", OF_full.shape)

# pad size for FFT (linear corr via full padding)
PH = Hh + OF_full.shape[0]
PW = Ww + OF_full.shape[1]
IFp = np.zeros((PH, PW), complex); IFp[:Hh, :Ww] = IF
FIF = fft2(IFp)
absIF2 = np.zeros((PH, PW)); absIF2[:Hh, :Ww] = np.abs(IF) ** 2
FabsIF2 = fft2(absIF2)


def corr_for(scale, phi):
    # scale & rotate OCT template, phase-rotate orientation by exp(2i phi)
    oh, ow = OF_full.shape
    M = cv2.getRotationMatrix2D((ow / 2, oh / 2), np.rad2deg(phi), scale)
    # rotate real/imag channels
    stack = np.stack([OF_full.real, OF_full.imag], -1).astype(np.float32)
    nw, nh = int(ow * 1.5), int(oh * 1.5)
    M[0, 2] += (nw - ow) / 2; M[1, 2] += (nh - oh) / 2
    rot = cv2.warpAffine(stack, M, (nw, nh))
    T = (rot[..., 0] + 1j * rot[..., 1]) * np.exp(2j * phi)
    th, tw = T.shape
    if th >= PH or tw >= PW:
        return -1, None, None
    Tp = np.zeros((PH, PW), complex); Tp[:th, :tw] = T
    supp = np.zeros((PH, PW)); supp[:th, :tw] = (np.abs(T) > 1e-6)
    # numerator: Re( sum conj(T) * IF ) as function of shift -> cross-correlation
    num = np.real(ifft2(FIF * np.conj(fft2(Tp))))
    # local IF energy under template support
    denomE = np.real(ifft2(FabsIF2 * np.conj(fft2(supp))))
    Tenergy = np.sum(np.abs(T) ** 2)
    denom = np.sqrt(np.maximum(denomE, 1e-6) * Tenergy)
    ncc = num / denom
    # require enough overlap
    ov = np.real(ifft2(fft2((np.abs(IF) > 1e-6).astype(float)
                            if False else absIF2 * 0 + (absIF2 > 0)) * np.conj(fft2(supp))))
    ncc[ov < 0.3 * supp.sum()] = -1
    k = np.argmax(ncc)
    yy, xx = np.unravel_index(k, ncc.shape)
    return float(ncc[yy, xx]), (yy, xx), (th, tw)


def search():
    best = (-1, None)
    t0 = time.time()
    for scale in np.arange(0.45, 0.81, 0.05):
        for phi in np.deg2rad(np.arange(0, 180, 3)):
            sc, peak, tsz = corr_for(scale, phi)
            if sc > best[0]:
                best = (sc, (scale, phi, peak, tsz))
        print(f"  scale {scale:.2f} best-so-far {best[0]:.3f}  ({time.time()-t0:.0f}s)")
    return best


def build_transform(scale, phi, peak):
    """Map full-res OCT (x,y) -> full-res immuno (x,y).
    Template built by: rotate OCT-field(center ow/2,oh/2) by phi, scale, shift into 1.5x canvas.
    Then placed at (xx,yy) offset in padded immuno (work res). Convert to full res /DS.
    """
    ow_w = OF_full.shape[1]; oh_w = OF_full.shape[0]
    nw, nh = int(ow_w * 1.5), int(oh_w * 1.5)
    # rotation+scale about work-res OCT center, in work res
    cx, cy = ow_w / 2, oh_w / 2
    ang = np.deg2rad(np.rad2deg(phi))
    c, s = np.cos(ang), np.sin(ang)
    Rm = scale * np.array([[c, -s], [s, c]])
    off = np.array([(nw - ow_w) / 2, (nh - oh_w) / 2])
    yy, xx = peak
    place = np.array([xx, yy])
    # work-res point p_oct_w -> T-canvas: Rm@(p-c)+c+off ; then + place - (canvas origin)
    # net (work res): p_imm_w = Rm@(p_oct_w - c) + c + off + place
    tw = c * 0
    def A_t_workres():
        A = Rm
        t = -Rm @ np.array([cx, cy]) + np.array([cx, cy]) + off + place
        return A, t
    A, t = A_t_workres()
    # convert work-res mapping to full-res: p_work = DS * p_full
    # DS*p_imm_full = A (DS*p_oct_full) + t  => p_imm_full = A p_oct_full + t/DS
    return A, t / DS


def orient_agree(A, t, coh_min=0.15):
    to, co = orientation_field(oct_g); ti, ci = orientation_field(imm_g)
    rot = np.arctan2(A[1, 0], A[0, 0])
    Oi = O.astype(int)
    m = O @ A.T + t; mi = np.round(m).astype(int)
    H2, W2 = imm_g.shape
    ok = (mi[:, 0] >= 0) & (mi[:, 0] < W2) & (mi[:, 1] >= 0) & (mi[:, 1] < H2)
    mx, my = mi[ok, 0], mi[ok, 1]
    sel = (co[Oi[ok, 1], Oi[ok, 0]] > coh_min) & (ci[my, mx] > coh_min)
    a = to[Oi[ok, 1], Oi[ok, 0]][sel] + rot
    b = ti[my, mx][sel]
    d = (a - b) % np.pi; d = np.minimum(d, np.pi - d)
    return float((np.rad2deg(d) < 15).mean()), int(sel.sum())


def icp(A, t, iters=60, tol=12.0):
    for _ in range(iters):
        pts = O @ A.T + t
        d, idx = imm_tree.query(pts)
        inl = d < tol
        if inl.sum() < 4: break
        src, dst = O[inl], I[idx[inl]]
        mu_s, mu_d = src.mean(0), dst.mean(0)
        Sc, Dc = src - mu_s, dst - mu_d
        U, D, Vt = np.linalg.svd(Dc.T @ Sc / len(src))
        Rn = U @ Vt
        if np.linalg.det(Rn) < 0: U[:, -1] *= -1; Rn = U @ Vt
        sc = np.trace(np.diag(D)) / ((Sc ** 2).sum() / len(src))
        A = sc * Rn; t = mu_d - A @ mu_s
    pts = O @ A.T + t; d, idx = imm_tree.query(pts)
    return A, t, int((d < tol).sum())


def save_overlay(A, t, tag=""):
    M = np.hstack([A, t.reshape(2, 1)]).astype(np.float32)
    warp = cv2.warpAffine(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), M, (imm_g.shape[1], imm_g.shape[0]))
    wg = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)
    over = imm_bgr.copy()
    over[:, :, 1] = np.maximum(over[:, :, 1], imm_bgr[:, :, 2])
    over[:, :, 2] = np.maximum(over[:, :, 2], wg)
    over[:, :, 0] = np.maximum(over[:, :, 0], wg)
    cv2.imwrite(os.path.join(OUT, f"overlay{tag}.png"), over)
    corners = np.array([[0, 0], [oct_g.shape[1], 0], [oct_g.shape[1], oct_g.shape[0]], [0, oct_g.shape[0]]], float)
    cc = corners @ A.T + t
    x0, y0 = np.maximum(cc.min(0).astype(int) - 20, 0)
    x1, y1 = np.minimum(cc.max(0).astype(int) + 20, [imm_g.shape[1], imm_g.shape[0]])
    cv2.imwrite(os.path.join(OUT, f"overlay_crop{tag}.png"), over[y0:y1, x0:x1])


def main():
    sc, (scale, phi, peak, tsz) = search()
    print(f"orientation-corr best score={sc:.3f} scale={scale:.2f} phi={np.rad2deg(phi):.0f}")
    results = []
    for extra in [0.0, np.pi]:  # resolve 180 flip
        A, t = build_transform(scale, phi + extra, peak)
        fa0, _ = orient_agree(A, t)
        A2, t2, ninl = icp(A, t)
        fa, ns = orient_agree(A2, t2)
        results.append((fa, ninl, A2, t2, np.rad2deg(phi + extra), fa0))
        print(f"  flip {np.rad2deg(extra):.0f}: pre-agree={fa0:.2f} -> ICP agree={fa:.2f} inliers={ninl}")
    results.sort(key=lambda z: -z[0])
    fa, ninl, A, t, phd, fa0 = results[0]
    scale_f = np.sqrt(abs(np.linalg.det(A))); rot = np.rad2deg(np.arctan2(A[1, 0], A[0, 0]))
    print(f"\nBEST orient_agree={fa:.2f} inliers={ninl}/{len(O)} scale={scale_f:.3f} rot={rot:.1f}")
    np.savez(os.path.join(OUT, "transform.npz"), A=A, t=t)
    save_overlay(A, t)
    print("saved overlay + transform")


if __name__ == "__main__":
    main()
