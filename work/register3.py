"""Anchor-based registration: pin OCT core -> immuno core (1596,780), then search
rotation + fine scale (+ small OCT-core neighbourhood) maximizing coverage-enforced
ridge-orientation agreement. Position pinned by the singular point makes orientation
discriminative. Final rigid pore-ICP polish."""
import cv2, numpy as np, os, time
from scipy.spatial import cKDTree
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

O = np.load(os.path.join(OUT, "oct_pts.npy")).astype(float)[:, ::-1].copy()
I = np.load(os.path.join(OUT, "imm_pts.npy")).astype(float)[:, ::-1].copy()
imm_tree = cKDTree(I)

oct_g = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
imm_bgr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))
imm_g = imm_bgr[:, :, 2]
Hh, Ww = imm_g.shape
to, co = orientation_field(oct_g, 1.5, 10.0)
ti, ci = orientation_field(imm_g, 1.5, 10.0)

gy, gx = np.mgrid[0:oct_g.shape[0]:14, 0:oct_g.shape[1]:14]
S = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
Si = S.astype(int)
keep = co[Si[:, 1], Si[:, 0]] > 0.2
S, to_at = S[keep], to[Si[keep][:, 1], Si[keep][:, 0]]
NS = len(S)

IMM_CORE = np.array([1596.0, 780.0])
OCT_CORE0 = np.array([540.0, 420.0])   # visual estimate of OCT loop core


def R_of(th):
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, -s], [s, c]])


def score(A, t, coh_min=0.15, min_cover=0.55):
    mapped = S @ A.T + t
    mi = np.round(mapped).astype(int)
    ok = (mi[:, 0] >= 0) & (mi[:, 0] < Ww) & (mi[:, 1] >= 0) & (mi[:, 1] < Hh)
    mx = np.clip(mi[:, 0], 0, Ww - 1); my = np.clip(mi[:, 1], 0, Hh - 1)
    coh = ok & (ci[my, mx] > coh_min)
    cover = coh.sum() / NS
    if cover < min_cover:
        return 0.0, cover
    rot = np.arctan2(A[1, 0], A[0, 0])
    d = ((to_at + rot) - ti[my, mx]) % np.pi
    d = np.minimum(d, np.pi - d)
    return float((coh & (np.rad2deg(d) < 15)).sum() / NS), float(cover)


def search():
    best = (-1, None)
    scales = np.arange(0.46, 0.605, 0.02)
    thetas = np.deg2rad(np.arange(0, 360, 2))
    cxs = OCT_CORE0[0] + np.arange(-80, 81, 20)
    cys = OCT_CORE0[1] + np.arange(-80, 81, 20)
    t0 = time.time()
    for cox in cxs:
        for coy in cys:
            oc = np.array([cox, coy])
            for s in scales:
                for th in thetas:
                    A = s * R_of(th)
                    t = IMM_CORE - A @ oc     # pin OCT core -> immuno core
                    sc, cov = score(A, t)
                    if sc > best[0]:
                        best = (sc, (s, th, oc, A, t, cov))
    print(f"anchor search best score={best[0]:.3f} cover={best[1][5]:.2f} "
          f"scale={best[1][0]:.2f} rot={np.rad2deg(best[1][1]):.1f} octcore={best[1][2]} ({time.time()-t0:.0f}s)")
    return best


def rigid_icp(A, t, iters=30, tol=8.0):
    scale = np.sqrt(abs(np.linalg.det(A)))
    for _ in range(iters):
        d, idx = imm_tree.query(O @ A.T + t)
        inl = d < tol
        if inl.sum() < 12:
            break
        src, dst = O[inl], I[idx[inl]]
        mu_s, mu_d = src.mean(0), dst.mean(0)
        Sc, Dc = src - mu_s, dst - mu_d
        U, D, Vt = np.linalg.svd(Dc.T @ Sc / len(src))
        Rn = U @ Vt
        if np.linalg.det(Rn) < 0:
            U[:, -1] *= -1; Rn = U @ Vt
        A = scale * Rn; t = mu_d - A @ mu_s
    d, idx = imm_tree.query(O @ A.T + t)
    return A, t, int((d < tol).sum())


def main():
    sc, (s, th, oc, A, t, cov) = search()
    A2, t2, ninl = rigid_icp(A, t)
    scB, covB = score(A2, t2)
    scA, covA = score(A, t)
    Af, tf = (A2, t2) if scB >= scA - 0.03 else (A, t)
    fsc, fcov = score(Af, tf)
    scale = np.sqrt(abs(np.linalg.det(Af))); rot = np.rad2deg(np.arctan2(Af[1, 0], Af[0, 0]))
    dd, _ = imm_tree.query(O @ Af.T + tf)
    print(f"FINAL orient={fsc:.2f} cover={fcov:.2f} pore_inliers(<8px)={int((dd<8).sum())}/{len(O)} "
          f"scale={scale:.3f} rot={rot:.1f}")
    np.savez(os.path.join(OUT, "transform.npz"), A=Af, t=tf)
    print("saved transform.npz")


if __name__ == "__main__":
    main()
