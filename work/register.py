"""Register OCT pore cloud onto the immunolabel, using pore inliers for coarse
candidates and RIDGE ORIENTATION AGREEMENT as the discriminating criterion.

Model: similarity  p_imm = s * R(theta) @ p_oct + t   (affine optional in refine)
"""
import cv2, numpy as np, os, time
from scipy.spatial import cKDTree
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

O = np.load(os.path.join(OUT, "oct_pts.npy")).astype(float)[:, ::-1].copy()  # (x,y)
I = np.load(os.path.join(OUT, "imm_pts.npy")).astype(float)[:, ::-1].copy()
imm_tree = cKDTree(I)
Ocen = O.mean(0)
Imin, Imax = I.min(0), I.max(0)

oct_g = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
imm_g = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
Hh, Ww = imm_g.shape
to, co = orientation_field(oct_g)
ti, ci = orientation_field(imm_g)
# orientation sampled at OCT pore locations (they sit on ridges -> coherent)
Oi = O.astype(int)
to_at = to[Oi[:, 1], Oi[:, 0]]
co_at = co[Oi[:, 1], Oi[:, 0]]


def R_of(th):
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, -s], [s, c]])


def orient_agree(A, t, coh_min=0.15):
    rot = np.arctan2(A[1, 0], A[0, 0])
    m = (O @ A.T + t)
    mi = np.round(m).astype(int)
    ok = (mi[:, 0] >= 0) & (mi[:, 0] < Ww) & (mi[:, 1] >= 0) & (mi[:, 1] < Hh)
    if ok.sum() < 10:
        return 0.0, 0
    mx, my = mi[ok, 0], mi[ok, 1]
    cih = ci[my, mx]
    sel = (co_at[ok] > coh_min) & (cih > coh_min)
    if sel.sum() < 10:
        return 0.0, 0
    a = to_at[ok][sel] + rot
    b = ti[my, mx][sel]
    d = (a - b) % np.pi
    d = np.minimum(d, np.pi - d)
    return float((np.rad2deg(d) < 15).mean()), int(sel.sum())


def coarse(topK=400, tol=15.0):
    scales = np.arange(0.85, 1.19, 0.03)
    thetas = np.deg2rad(np.arange(0, 360, 5))
    gx = np.arange(Imin[0], Imax[0] + 1, 35)
    gy = np.arange(Imin[1], Imax[1] + 1, 35)
    Oc = O - Ocen
    cand = []
    t0 = time.time()
    for s in scales:
        for th in thetas:
            base = (s * (Oc @ R_of(th).T))
            for cx in gx:
                for cy in gy:
                    pts = base + (cx, cy)
                    d, _ = imm_tree.query(pts)
                    n = int((d < tol).sum())
                    cand.append((n, s, th, cx, cy))
    cand.sort(key=lambda z: -z[0])
    print(f"coarse done {len(cand)} cands in {time.time()-t0:.0f}s; top inliers={cand[0][0]}")
    return cand[:topK]


def to_At(s, th, cx, cy):
    A = s * R_of(th)
    t = np.array([cx, cy]) - A @ Ocen
    return A, t


def icp(A, t, iters=50, tol=12.0):
    for _ in range(iters):
        pts = O @ A.T + t
        d, idx = imm_tree.query(pts)
        inl = d < tol
        if inl.sum() < 4:
            break
        src, dst = O[inl], I[idx[inl]]
        mu_s, mu_d = src.mean(0), dst.mean(0)
        Sc, Dc = src - mu_s, dst - mu_d
        U, D, Vt = np.linalg.svd(Dc.T @ Sc / len(src))
        Rn = U @ Vt
        if np.linalg.det(Rn) < 0:
            U[:, -1] *= -1; Rn = U @ Vt
        sc = np.trace(np.diag(D)) / ((Sc ** 2).sum() / len(src))
        A = sc * Rn
        t = mu_d - A @ mu_s
    pts = O @ A.T + t
    d, idx = imm_tree.query(pts)
    return A, t, int((d < tol).sum()), d


def main():
    cands = coarse()
    # rescore top candidates by orientation agreement
    rescored = []
    for (n, s, th, cx, cy) in cands:
        A, t = to_At(s, th, cx, cy)
        fa, ns = orient_agree(A, t)
        rescored.append((fa, n, s, th, cx, cy))
    rescored.sort(key=lambda z: -z[0])
    print("top by orientation agreement (frac<15deg, inliers):")
    for r in rescored[:8]:
        print(f"  agree={r[0]:.2f} inl={r[1]} s={r[2]:.2f} th={np.rad2deg(r[3]):.0f}")

    # ICP-refine the best few orientation candidates; final pick by orientation agreement
    best = None
    for (fa, n, s, th, cx, cy) in rescored[:12]:
        A, t = to_At(s, th, cx, cy)
        A, t, ninl, d = icp(A, t)
        fa2, ns = orient_agree(A, t)
        if best is None or fa2 > best[0]:
            best = (fa2, ninl, A, t)
    fa, ninl, A, t = best
    scale = np.sqrt(abs(np.linalg.det(A)))
    rot = np.rad2deg(np.arctan2(A[1, 0], A[0, 0]))
    print(f"\nBEST: orient_agree(<15deg)={fa:.2f}  pore_inliers={ninl}/{len(O)}  scale={scale:.3f} rot={rot:.1f}")
    np.savez(os.path.join(OUT, "transform.npz"), A=A, t=t)

    # overlay
    oct_bgr = cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg"))
    imm_bgr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))
    M = np.hstack([A, t.reshape(2, 1)]).astype(np.float32)
    warp = cv2.warpAffine(oct_bgr, M, (Ww, Hh))
    warp_g = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)
    over = imm_bgr.copy()
    over[:, :, 1] = np.maximum(over[:, :, 1], imm_bgr[:, :, 2])
    over[:, :, 2] = np.maximum(over[:, :, 2], warp_g)
    over[:, :, 0] = np.maximum(over[:, :, 0], warp_g)
    cv2.imwrite(os.path.join(OUT, "overlay.png"), over)
    corners = np.array([[0, 0], [oct_bgr.shape[1], 0], [oct_bgr.shape[1], oct_bgr.shape[0]], [0, oct_bgr.shape[0]]], float)
    cc = corners @ A.T + t
    x0, y0 = np.maximum(cc.min(0).astype(int) - 20, 0)
    x1, y1 = np.minimum(cc.max(0).astype(int) + 20, [Ww, Hh])
    cv2.imwrite(os.path.join(OUT, "overlay_crop.png"), over[y0:y1, x0:x1])
    print("wrote overlay.png, overlay_crop.png, transform.npz")


if __name__ == "__main__":
    main()
