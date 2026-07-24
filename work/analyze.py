"""Pore analysis in the OCT ROI after landmark-based registration.
 1) count pores in the OCT area (ROI) in BOTH modalities
 2) match pores (mutual nearest neighbour): shared / OCT-only / immuno-only
 3) inter-pore (nearest-neighbour) distance of matched pores, in micrometres
Transform: affine OCT->immuno from manual landmarks (fit.npz).
Physical scale from OCT calibration: 10 mm over 1044 px (x) and 1154 px (y).
"""
import os, json, numpy as np, cv2, csv
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

SX, SY = 10000.0 / 1044, 10000.0 / 1154   # OCT micrometre/pixel (x,y)

f = np.load(os.path.join(OUT, "fit.npz"))
A, t = f["Aa"], f["ta"]                    # OCT(x,y) -> immuno(x,y)
Ainv = np.linalg.inv(A)

octg = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
immr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
Hh, Ww = immr.shape

Opts = np.load(os.path.join(OUT, "oct_pts.npy")).astype(float)[:, ::-1]   # (x,y)
Ipts = np.load(os.path.join(OUT, "imm_pts.npy")).astype(float)[:, ::-1]

# ---- OCT valid region (exclude black bands / scan artefacts) = ROI in OCT space ----
oct_valid = (octg > 25).astype(np.uint8)
oct_valid = cv2.morphologyEx(oct_valid, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
oct_valid = cv2.erode(oct_valid, np.ones((9, 9), np.uint8))

def in_octvalid(xy):
    xi = np.clip(xy[:, 0].astype(int), 0, octg.shape[1] - 1)
    yi = np.clip(xy[:, 1].astype(int), 0, octg.shape[0] - 1)
    return oct_valid[yi, xi] > 0

# OCT pores inside ROI
oct_in = in_octvalid(Opts)
O = Opts[oct_in]
# map OCT pores to immuno frame
Om = O @ A.T + t

# ROI polygon in immuno frame = warped OCT valid mask
roi_imm = cv2.warpAffine(oct_valid * 255, np.hstack([A, t.reshape(2, 1)]).astype(np.float32),
                         (Ww, Hh), flags=cv2.INTER_NEAREST)
def in_roi_imm(xy):
    xi = np.clip(xy[:, 0].astype(int), 0, Ww - 1)
    yi = np.clip(xy[:, 1].astype(int), 0, Hh - 1)
    return roi_imm[yi, xi] > 0

# immuno print body mask (where immuno actually has signal)
blur = cv2.GaussianBlur(immr, (0, 0), 25)
mm = (blur > np.percentile(blur, 85)).astype(np.uint8)
nl, lab, st, _ = cv2.connectedComponentsWithStats(mm)
big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
imm_print = (lab == big).astype(np.uint8)
imm_print = cv2.morphologyEx(imm_print, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
imm_print = cv2.erode(imm_print, np.ones((15, 15), np.uint8))
# fair-comparison region = OCT ROI intersected with immuno print body
overlap = ((roi_imm > 0) & (imm_print > 0)).astype(np.uint8)

def in_overlap(xy):
    xi = np.clip(xy[:, 0].astype(int), 0, Ww - 1)
    yi = np.clip(xy[:, 1].astype(int), 0, Hh - 1)
    return overlap[yi, xi] > 0

# immuno pores inside ROI
imm_in = in_roi_imm(Ipts)
I = Ipts[imm_in]

print(f"OCT pores total={len(Opts)}  in ROI={len(O)}")
print(f"IMM pores total={len(Ipts)}  in ROI={len(I)}")
area_roi = int((roi_imm > 0).sum()); area_ovl = int((overlap > 0).sum())
print(f"ROI covered by immuno print body: {100*area_ovl/area_roi:.0f}% of ROI area")

# ---- inter-pore nearest-neighbour spacing in the immuno frame (px) to set match radius ----
def med_nn(pts):
    if len(pts) < 2:
        return np.nan
    tr = cKDTree(pts); d, _ = tr.query(pts, k=2)
    return np.median(d[:, 1])
nn_imm_px = med_nn(I)
print(f"median NN spacing (immuno-frame px): OCT_mapped={med_nn(Om):.1f}  immuno={nn_imm_px:.1f}")

# ---- mutual nearest-neighbour matching in immuno frame ----
def match(radius):
    tO = cKDTree(Om); tI = cKDTree(I)
    dO, jO = tI.query(Om)          # nearest immuno for each mapped OCT
    dI, jI = tO.query(I)           # nearest OCT for each immuno
    shared = []
    for k in range(len(Om)):
        j = jO[k]
        if dO[k] <= radius and jI[j] == k:
            shared.append((k, j, dO[k]))
    matched_O = set(s[0] for s in shared)
    matched_I = set(s[1] for s in shared)
    return shared, matched_O, matched_I

med_radius = 0.45 * nn_imm_px
for frac in (0.35, 0.45, 0.55):
    sh, mO, mI = match(frac * nn_imm_px)
    print(f"  radius={frac:.2f}xNN ({frac*nn_imm_px:.0f}px): shared={len(sh)} "
          f"OCT-only={len(O)-len(mO)} immuno-only={len(I)-len(mI)}")

RAD = med_radius
shared, mO, mI = match(RAD)
print(f"\nCHOSEN radius = 0.45xNN = {RAD:.0f}px immuno (~{RAD/ (nn_imm_px):.2f} spacing)")
print("[A] FULL OCT ROI (as requested):")
print(f"  OCT pores={len(O)}  immuno pores={len(I)}")
print(f"  shared={len(shared)}  OCT-only={len(O)-len(mO)}  immuno-only={len(I)-len(mI)}")

# [B] fair region: only where immuno print has signal
O_ovl = in_overlap(Om); I_ovl = in_overlap(I)
sh_ovl = [s for s in shared if O_ovl[s[0]] and I_ovl[s[1]]]
mO_ovl = set(s[0] for s in sh_ovl); mI_ovl = set(s[1] for s in sh_ovl)
octonly_ovl = int(O_ovl.sum() - len(mO_ovl))
immonly_ovl = int(I_ovl.sum() - len(mI_ovl))
print("[B] FAIR region (OCT ROI intersect immuno print body):")
print(f"  OCT pores={int(O_ovl.sum())}  immuno pores={int(I_ovl.sum())}")
print(f"  shared={len(sh_ovl)}  OCT-only={octonly_ovl}  immuno-only={immonly_ovl}")
if I_ovl.sum():
    print(f"  -> {100*len(sh_ovl)/int(I_ovl.sum()):.0f}% of immuno pores have an OCT match; "
          f"OCT finds {int(O_ovl.sum())/max(int(I_ovl.sum()),1):.1f}x as many pores as immuno here")

# ---- distances in micrometres (OCT calibration) ----
def to_um_from_oct(xy_oct):
    return np.stack([xy_oct[:, 0] * SX, xy_oct[:, 1] * SY], 1)
def imm_to_um(xy_imm):
    oct_xy = (xy_imm - t) @ Ainv.T
    return to_um_from_oct(oct_xy)

# matched-pair positional agreement (registration/measurement accuracy)
pair_res_um = []
for (k, j, dpx) in shared:
    a = to_um_from_oct(O[k:k+1])[0]
    b = imm_to_um(I[j:j+1])[0]
    pair_res_um.append(np.linalg.norm(a - b))
pair_res_um = np.array(pair_res_um)

# inter-pore (NN) spacing among matched pores, per modality, in um
O_sh_um = to_um_from_oct(O[[s[0] for s in shared]])
I_sh_um = imm_to_um(I[[s[1] for s in shared]])
def nn_um(pts):
    tr = cKDTree(pts); d, _ = tr.query(pts, k=2); return d[:, 1]
ipd_oct = nn_um(O_sh_um)
ipd_imm = nn_um(I_sh_um)
# also all-pore NN spacing in ROI
ipd_oct_all = nn_um(to_um_from_oct(O))
ipd_imm_all = nn_um(imm_to_um(I))

def stats(a):
    return f"median={np.median(a):.0f}  mean={a.mean():.0f}  sd={a.std():.0f}  n={len(a)}  [{np.percentile(a,10):.0f}-{np.percentile(a,90):.0f}]"

print("\n--- inter-pore nearest-neighbour distance (micrometre) ---")
print(f" matched pores, OCT-measured   : {stats(ipd_oct)}")
print(f" matched pores, immuno-measured: {stats(ipd_imm)}")
print(f" all ROI pores, OCT-measured   : {stats(ipd_oct_all)}")
print(f" all ROI pores, immuno-measured: {stats(ipd_imm_all)}")
print(f"\n matched-pair position agreement (um): median={np.median(pair_res_um):.0f} mean={pair_res_um.mean():.0f} max={pair_res_um.max():.0f}")

# ---- ROI area & densities ----
roi_area_oct_mm2 = (oct_valid.sum() * SX * SY) / 1e6
print(f"\n ROI area = {roi_area_oct_mm2:.1f} mm^2")
print(f" pore density: OCT={len(O)/roi_area_oct_mm2:.1f}/mm^2  immuno={len(I)/roi_area_oct_mm2:.1f}/mm^2")

# ---- save CSV of matched pairs ----
with open(os.path.join(OUT, "matched_pairs.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["oct_x_px", "oct_y_px", "imm_x_px", "imm_y_px", "pair_dist_um"])
    for (k, j, dpx), r in zip(shared, pair_res_um):
        w.writerow([f"{O[k,0]:.1f}", f"{O[k,1]:.1f}", f"{I[j,0]:.1f}", f"{I[j,1]:.1f}", f"{r:.1f}"])

# ---- visualization in immuno frame, cropped to ROI ----
imm_e = cv2.createCLAHE(3.0, (16, 16)).apply(immr)
vis = cv2.cvtColor(imm_e, cv2.COLOR_GRAY2BGR)
# ROI outline
cnts, _ = cv2.findContours(roi_imm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
cv2.drawContours(vis, cnts, -1, (0, 165, 255), 2)
cnts2, _ = cv2.findContours(overlap, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
cv2.drawContours(vis, cnts2, -1, (255, 120, 0), 2)   # blue = fair comparison region
for k in range(len(O)):
    if k not in mO:
        p = Om[k].astype(int); cv2.drawMarker(vis, tuple(p), (255, 0, 255), cv2.MARKER_TILTED_CROSS, 12, 2)  # OCT-only magenta
for j in range(len(I)):
    if j not in mI:
        p = I[j].astype(int); cv2.circle(vis, tuple(p), 6, (0, 255, 255), 2)  # immuno-only yellow
for (k, j, dpx) in shared:
    a = Om[k].astype(int); b = I[j].astype(int)
    cv2.circle(vis, tuple(b), 7, (0, 255, 0), 2)                     # shared green
    cv2.line(vis, tuple(a), tuple(b), (0, 255, 0), 1)
ys, xs = np.where(roi_imm > 0)
x0, y0, x1, y1 = xs.min() - 30, ys.min() - 30, xs.max() + 30, ys.max() + 30
x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(Ww, x1), min(Hh, y1)
leg = vis[y0:y1, x0:x1].copy()
cv2.putText(leg, "green=shared  magenta=OCT-only  yellow=immuno-only", (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
cv2.imwrite(os.path.join(OUT, "analysis.png"), leg)
print("\nwrote analysis.png, matched_pairs.csv")
