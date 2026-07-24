"""Fit OCT->immuno transform from manual landmark pairs; report residuals; validate."""
import json, os, numpy as np, cv2
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
pts = json.load(open(os.path.join(ROOT, "work", "points.json")))["pairs"]
O = np.array([p["o"] for p in pts], float)   # oct (x,y)
I = np.array([p["i"] for p in pts], float)   # imm (x,y)
n = len(O)
print(f"{n} landmark pairs")


def umeyama(src, dst, with_scale=True):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    Sc, Dc = src - mu_s, dst - mu_d
    U, D, Vt = np.linalg.svd(Dc.T @ Sc / len(src))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1; R = U @ Vt
    s = (np.trace(np.diag(D)) / ((Sc ** 2).sum() / len(src))) if with_scale else 1.0
    A = s * R
    t = mu_d - A @ mu_s
    return A, t


def affine(src, dst):
    X = np.hstack([src, np.ones((len(src), 1))])
    M, *_ = np.linalg.lstsq(X, dst, rcond=None)   # (3,2)
    A = M[:2].T
    t = M[2]
    return A, t


def resid(A, t):
    pred = O @ A.T + t
    d = np.linalg.norm(pred - I, axis=1)
    return d


As, ts = umeyama(O, I, True)
Aa, ta = affine(O, I)
ds, da = resid(As, ts), resid(Aa, ta)
scale = np.sqrt(abs(np.linalg.det(As)))
rot = np.rad2deg(np.arctan2(As[1, 0], As[0, 0]))
print(f"SIMILARITY: scale={scale:.3f} rot={rot:.1f}  residual px  mean={ds.mean():.1f} max={ds.max():.1f}  per-pt={np.round(ds,1)}")
print(f"AFFINE:                                 residual px  mean={da.mean():.1f} max={da.max():.1f}  per-pt={np.round(da,1)}")
sx = np.linalg.norm(Aa[:, 0]); sy = np.linalg.norm(Aa[:, 1])
shear = np.rad2deg(np.arccos(np.clip((Aa[:, 0] @ Aa[:, 1]) / (sx * sy), -1, 1)))
print(f"   affine scales sx={sx:.3f} sy={sy:.3f} axis-angle={shear:.1f}deg (90=no shear)")

# validate by orientation agreement using affine
octg = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
immg = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
Hh, Ww = immg.shape
to, co = orientation_field(octg, 1.5, 10.0)
ti, ci = orientation_field(immg, 1.5, 10.0)


def orient_agree(A, t):
    rot_ = np.arctan2(A[1, 0], A[0, 0])
    gy, gx = np.mgrid[0:octg.shape[0]:10, 0:octg.shape[1]:10]
    S = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
    Si = S.astype(int)
    keep = co[Si[:, 1], Si[:, 0]] > 0.2
    S, toat = S[keep], to[Si[keep][:, 1], Si[keep][:, 0]]
    m = np.round(S @ A.T + t).astype(int)
    ok = (m[:, 0] >= 0) & (m[:, 0] < Ww) & (m[:, 1] >= 0) & (m[:, 1] < Hh)
    mx = np.clip(m[:, 0], 0, Ww - 1); my = np.clip(m[:, 1], 0, Hh - 1)
    coh = ok & (ci[my, mx] > 0.15)
    d = ((toat + rot_) - ti[my, mx]) % np.pi
    d = np.minimum(d, np.pi - d)
    return (coh & (np.rad2deg(d) < 15)).sum() / len(S), coh.sum() / len(S)


for name, (A, t) in [("similarity", (As, ts)), ("affine", (Aa, ta))]:
    ag, cov = orient_agree(A, t)
    print(f"   {name}: orientation agreement(<15deg)={ag:.2f}  coverage={cov:.2f}")

np.savez(os.path.join(OUT, "fit.npz"), As=As, ts=ts, Aa=Aa, ta=ta, O=O, I=I)
print("saved fit.npz")
