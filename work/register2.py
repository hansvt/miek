"""Registration driven directly by ridge-orientation agreement.
Scale pinned near 0.53 (from ridge-period ratio OCT:IMM = 64:34).
Coarse: scan scale x rotation x translation, score = fraction of OCT pore sites
whose rotated ridge orientation matches the immuno orientation within 15deg.
Refine: local hill-climb on orientation, then small-tolerance pore ICP polish.
"""
import cv2, numpy as np, os, time
from scipy.spatial import cKDTree
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

O = np.load(os.path.join(OUT, "oct_pts.npy")).astype(float)[:, ::-1].copy()
I = np.load(os.path.join(OUT, "imm_pts.npy")).astype(float)[:, ::-1].copy()
imm_tree = cKDTree(I)
Ocen = O.mean(0)
Imin, Imax = I.min(0), I.max(0)

oct_g = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
imm_bgr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))
imm_g = imm_bgr[:, :, 2]
Hh, Ww = imm_g.shape
to, co = orientation_field(oct_g, 1.5, 10.0)
ti, ci = orientation_field(imm_g, 1.5, 10.0)

# OCT sample grid (not just pores) for a robust orientation score
gy, gx = np.mgrid[0:oct_g.shape[0]:16, 0:oct_g.shape[1]:16]
S = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
Si = S.astype(int)
to_at = to[Si[:, 1], Si[:, 0]]
co_at = co[Si[:, 1], Si[:, 0]]
keep = co_at > 0.2
S, to_at = S[keep], to_at[keep]
# subsample to keep coarse search fast
if len(S) > 500:
    sel = np.linspace(0, len(S) - 1, 500).astype(int)
    S, to_at = S[sel], to_at[sel]
Scen = S - Ocen
print(f"orientation samples: {len(S)}")


def R_of(th):
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, -s], [s, c]])


NS = len(to_at)


def agree_from_mapped(mapped, rot, coh_min=0.15, min_cover=0.55):
    """score = fraction of ALL OCT samples that land on the coherent print AND
    match orientation within 15deg. Enforces coverage so tiny-overlap spurious
    alignments cannot win. Returns (score, coverage)."""
    mi = np.round(mapped).astype(int)
    ok = (mi[:, 0] >= 0) & (mi[:, 0] < Ww) & (mi[:, 1] >= 0) & (mi[:, 1] < Hh)
    mx = np.clip(mi[:, 0], 0, Ww - 1); my = np.clip(mi[:, 1], 0, Hh - 1)
    coh = ok & (ci[my, mx] > coh_min)
    cover = coh.sum() / NS
    if cover < min_cover:
        return 0.0, float(cover)
    a = to_at + rot
    b = ti[my, mx]
    d = (a - b) % np.pi
    d = np.minimum(d, np.pi - d)
    match = (coh & (np.rad2deg(d) < 15)).sum()
    return float(match / NS), float(cover)


def coarse():
    scales = np.arange(0.46, 0.605, 0.02)
    thetas = np.deg2rad(np.arange(0, 360, 5))
    gxx = np.arange(Imin[0] - 80, Imax[0] + 81, 36)
    gyy = np.arange(Imin[1] - 80, Imax[1] + 81, 36)
    TX, TY = np.meshgrid(gxx, gyy)
    Tg = np.stack([TX.ravel(), TY.ravel()], 1).astype(float)  # (M,2)
    M = len(Tg)
    best = []
    t0 = time.time()
    for s in scales:
        for th in thetas:
            base = s * (Scen @ R_of(th).T)              # (N,2)
            # mapped[m,n] = base[n] + Tg[m]
            mx = np.round(base[:, 0][None, :] + Tg[:, 0][:, None]).astype(np.int32)  # (M,N)
            my = np.round(base[:, 1][None, :] + Tg[:, 1][:, None]).astype(np.int32)
            inb = (mx >= 0) & (mx < Ww) & (my >= 0) & (my < Hh)
            mxc = np.clip(mx, 0, Ww - 1); myc = np.clip(my, 0, Hh - 1)
            cih = ci[myc, mxc]
            b = ti[myc, mxc]
            coh = inb & (cih > 0.15)
            a = (to_at + th)[None, :]
            d = (a - b) % np.pi
            d = np.minimum(d, np.pi - d)
            good = coh & (np.rad2deg(d) < 15)
            cover = coh.sum(1) / S.shape[0]
            fa = np.where(cover >= 0.55, good.sum(1) / S.shape[0], 0.0)
            k = int(np.argmax(fa))
            if fa[k] > 0.30:
                best.append((float(fa[k]), s, th, float(Tg[k, 0]), float(Tg[k, 1]), float(cover[k])))
        print(f"  scale {s:.2f} best={max((b[0] for b in best), default=0):.3f} ({time.time()-t0:.0f}s)")
    best.sort(key=lambda z: -z[0])
    return best[:40]


def to_At(s, th, cx, cy):
    A = s * R_of(th)
    t = np.array([cx, cy]) - A @ Ocen
    return A, t


def agree_At(A, t):
    rot = np.arctan2(A[1, 0], A[0, 0])
    return agree_from_mapped(S @ A.T + t, rot)


def refine_orient(s, th, cx, cy, s_lo=0.49, s_hi=0.57):
    """local hill-climb on orientation agreement; scale clamped near ridge-period value."""
    best = (agree_from_mapped(s * (Scen @ R_of(th).T) + (cx, cy), th)[0], s, th, cx, cy)
    step_t, step_th, step_s = 16.0, np.deg2rad(3), 0.01
    for _ in range(80):
        improved = False
        for ds in (-step_s, 0, step_s):
            for dth in (-step_th, 0, step_th):
                for dcx in (-step_t, 0, step_t):
                    for dcy in (-step_t, 0, step_t):
                        s2 = min(max(best[1] + ds, s_lo), s_hi)
                        th2, cx2, cy2 = best[2] + dth, best[3] + dcx, best[4] + dcy
                        fa = agree_from_mapped(s2 * (Scen @ R_of(th2).T) + (cx2, cy2), th2)[0]
                        if fa > best[0] + 1e-4:
                            best = (fa, s2, th2, cx2, cy2); improved = True
        if not improved:
            step_t *= 0.5; step_th *= 0.5; step_s *= 0.5
            if step_t < 1:
                break
    return best


def icp_polish(A, t, iters=30, tol=8.0):
    """rigid ICP: refine rotation+translation, KEEP the current scale fixed."""
    scale = np.sqrt(abs(np.linalg.det(A)))
    for _ in range(iters):
        pts = O @ A.T + t
        d, idx = imm_tree.query(pts)
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
        A = scale * Rn; t = mu_d - A @ mu_s      # scale locked
    pts = O @ A.T + t; d, idx = imm_tree.query(pts)
    return A, t, int((d < tol).sum())


def save_overlay(A, t, tag=""):
    M = np.hstack([A, t.reshape(2, 1)]).astype(np.float32)
    warp = cv2.warpAffine(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), M, (Ww, Hh))
    wg = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)
    over = imm_bgr.copy()
    over[:, :, 1] = np.maximum(over[:, :, 1], imm_bgr[:, :, 2])
    over[:, :, 2] = np.maximum(over[:, :, 2], wg)
    over[:, :, 0] = np.maximum(over[:, :, 0], wg)
    cv2.imwrite(os.path.join(OUT, f"overlay{tag}.png"), over)
    corners = np.array([[0, 0], [oct_g.shape[1], 0], [oct_g.shape[1], oct_g.shape[0]], [0, oct_g.shape[0]]], float)
    cc = corners @ A.T + t
    x0, y0 = np.maximum(cc.min(0).astype(int) - 20, 0)
    x1, y1 = np.minimum(cc.max(0).astype(int) + 20, [Ww, Hh])
    if x1 > x0 and y1 > y0:
        cv2.imwrite(os.path.join(OUT, f"overlay_crop{tag}.png"), over[y0:y1, x0:x1])


def main():
    cands = coarse()
    print(f"\n{len(cands)} coarse candidates > 0.45 agreement; top:")
    for c in cands[:6]:
        print(f"  agree={c[0]:.2f} s={c[1]:.2f} th={np.rad2deg(c[2]):.0f} c=({c[3]:.0f},{c[4]:.0f})")
    def inliers(A, t, tol=8.0):
        d, _ = imm_tree.query(O @ A.T + t)
        return int((d < tol).sum())

    scored = []
    for (fa, s, th, cx, cy, ns) in cands[:20]:
        r = refine_orient(s, th, cx, cy)
        A, t = to_At(r[1], r[2], r[3], r[4])
        A2, t2, ninl = icp_polish(A, t)          # rigid polish (scale locked)
        faA = agree_At(A, t)[0]
        faB = agree_At(A2, t2)[0]
        Ac, tc = (A2, t2) if faB >= faA - 0.03 else (A, t)  # prefer polished unless it hurts
        scored.append((agree_At(Ac, tc)[0], inliers(Ac, tc), Ac, tc))
    # keep candidates with strong orientation agreement, then pick most pore inliers
    top = max(z[0] for z in scored)
    good = [z for z in scored if z[0] >= top - 0.05]   # near-best orientation
    pool = good if good else scored
    pool.sort(key=lambda z: -z[1])
    fa_fin, ninl, Af, tf = pool[0]
    print("\ncandidate (orient, pore_inliers):",
          sorted([(round(z[0], 2), z[1]) for z in scored], key=lambda x: -x[1])[:6])
    scale = np.sqrt(abs(np.linalg.det(Af))); rot = np.rad2deg(np.arctan2(Af[1, 0], Af[0, 0]))
    print(f"FINAL orient_agree(<15)={fa_fin:.2f}  pore_inliers={ninl}/{len(O)}  scale={scale:.3f} rot={rot:.1f}")
    np.savez(os.path.join(OUT, "transform.npz"), A=Af, t=tf)
    save_overlay(Af, tf)
    print("saved overlay + transform")


if __name__ == "__main__":
    main()
