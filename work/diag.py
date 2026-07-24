import cv2, numpy as np, os
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
d = np.load(os.path.join(OUT, "transform.npz")); A, t = d["A"], d["t"]
rot = np.arctan2(A[1, 0], A[0, 0])

octg = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
immr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
Hh, Ww = immr.shape
clahe = cv2.createCLAHE(3.0, (16, 16))
imm_e = clahe.apply(immr)
oct_e = clahe.apply(octg)

M = np.hstack([A, t.reshape(2, 1)]).astype(np.float32)
warp = cv2.warpAffine(oct_e, M, (Ww, Hh))
warp_mask = cv2.warpAffine(np.full_like(oct_e, 255), M, (Ww, Hh))

# blended: immuno enhanced (gray) + warped OCT ridges (as cyan where OCT dark ridges)
base = cv2.cvtColor(imm_e, cv2.COLOR_GRAY2BGR)
# OCT ridges are dark; make ridge map
octr = 255 - warp
octr[warp_mask == 0] = 0
octr = cv2.normalize(octr, None, 0, 255, cv2.NORM_MINMAX)
overlay = base.copy()
overlay[:, :, 1] = np.maximum(overlay[:, :, 1], (octr * 0.9).astype(np.uint8))  # cyan-ish (G)
overlay[:, :, 0] = np.maximum(overlay[:, :, 0], (octr * 0.9).astype(np.uint8))  # +B

# footprint
corners = np.array([[0, 0], [octg.shape[1], 0], [octg.shape[1], octg.shape[0]], [0, octg.shape[0]]], float)
cc = (corners @ A.T + t).astype(int)
cv2.polylines(overlay, [cc.reshape(-1, 1, 2)], True, (0, 0, 255), 3)

# match map on a dense grid
to, co = orientation_field(octg, 1.5, 10.0)
ti, ci = orientation_field(immr, 1.5, 10.0)
gy, gx = np.mgrid[0:octg.shape[0]:14, 0:octg.shape[1]:14]
S = np.stack([gx.ravel(), gy.ravel()], 1).astype(float)
Si = S.astype(int)
keepc = co[Si[:, 1], Si[:, 0]] > 0.2
S = S[keepc]; Si = Si[keepc]
mapped = S @ A.T + t
mi = np.round(mapped).astype(int)
mm = overlay.copy()
nmatch = ncov = 0
for (sx, sy), (mx, my) in zip(Si, mi):
    if 0 <= mx < Ww and 0 <= my < Hh and ci[my, mx] > 0.15:
        ncov += 1
        a = to[sy, sx] + rot; b = ti[my, mx]
        dd = (a - b) % np.pi; dd = min(dd, np.pi - dd)
        ok = np.rad2deg(dd) < 15
        nmatch += ok
        cv2.circle(mm, (mx, my), 4, (0, 255, 0) if ok else (0, 0, 255), -1)
print(f"samples={len(S)} coverage={ncov/len(S):.2f} match_frac_all={nmatch/len(S):.2f} match_in_overlap={nmatch/max(ncov,1):.2f}")
print("scale", round(np.sqrt(abs(np.linalg.det(A))), 3), "rot", round(np.rad2deg(rot), 1))

x0, y0 = np.maximum(cc.min(0) - 40, 0)
x1, y1 = np.minimum(cc.max(0) + 40, [Ww, Hh])
cv2.imwrite(os.path.join(OUT, "diag_overlay.png"), overlay[y0:y1, x0:x1])
cv2.imwrite(os.path.join(OUT, "diag_matchmap.png"), mm[y0:y1, x0:x1])
# also whole-print context
xs = np.where(imm_e.max(0) > 0)[0]
cv2.imwrite(os.path.join(OUT, "diag_context.png"), mm)
print("wrote diag_overlay.png, diag_matchmap.png, diag_context.png")
