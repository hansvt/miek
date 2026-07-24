"""ROI pore counting, cross-modality matching, and inter-pore distance."""
import os
import csv
import json
from datetime import datetime
import numpy as np
import cv2
from scipy.spatial import cKDTree

from .transform import Transform
from .detect import enhance
from . import report
from . import overlay_viewer


def _med_nn(pts):
    if len(pts) < 2:
        return np.nan
    d, _ = cKDTree(pts).query(pts, k=2)
    return np.median(d[:, 1])


def _nn(pts):
    d, _ = cKDTree(pts).query(pts, k=2)
    return d[:, 1]


def _nn_rows(coords_px, coords_um):
    """Per-pore nearest-neighbour table (WI-5).
    Angle convention: degrees of atan2(dy, dx) in image coords (x right, y down),
    so 0°=neighbour to the right, +90°=below, measured clockwise. Distance in µm."""
    n = len(coords_px)
    rows = []
    if n < 2:
        return rows
    tree = cKDTree(coords_um)
    d, j = tree.query(coords_um, k=2)
    for i in range(n):
        nn = int(j[i, 1])
        dx, dy = coords_um[nn] - coords_um[i]
        rows.append({"Porie_ID": i + 1,
                     "Coordinates": f"({coords_px[i,0]:.0f}, {coords_px[i,1]:.0f})",
                     "Nearest_neighbour_ID": nn + 1,
                     "Distance_neighbour": round(float(d[i, 1]), 1),
                     "Angle_neighbour": round(float(np.degrees(np.arctan2(dy, dx))), 1)})
    return rows


def _save_nn_csv(path, rows):
    cols = ["Porie_ID", "Coordinates", "Nearest_neighbour_ID", "Distance_neighbour", "Angle_neighbour"]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _save_numbered_map(base_gray, coords_px, rows, out_path, color=(0, 0, 255)):
    """Numbered pore map: ID label + centroid cross + dashed line to nearest neighbour."""
    vis = cv2.cvtColor(enhance(base_gray), cv2.COLOR_GRAY2BGR)
    for r in rows:
        i = r["Porie_ID"] - 1
        x, y = int(round(coords_px[i, 0])), int(round(coords_px[i, 1]))
        nn = r["Nearest_neighbour_ID"] - 1
        nx, ny = int(round(coords_px[nn, 0])), int(round(coords_px[nn, 1]))
        cv2.line(vis, (x, y), (nx, ny), (90, 90, 90), 1, cv2.LINE_AA)
    for r in rows:
        i = r["Porie_ID"] - 1
        x, y = int(round(coords_px[i, 0])), int(round(coords_px[i, 1]))
        cv2.drawMarker(vis, (x, y), color, cv2.MARKER_CROSS, 7, 1, cv2.LINE_AA)
        cv2.putText(vis, str(r["Porie_ID"]), (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX,
                    0.3, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.imwrite(out_path, vis)


def _matlab_match(Om, I, oct_area_um, imm_area_um, thr=0.1):
    """MATLAB-style matching (OCT_FM.txt): combine normalised position + area into one
    feature vector, then bidirectional nearest-neighbour with a single distance threshold.
    Positions are normalised by the max [x,y] over both sets; areas (in µm², comparable)
    by the max area over both. Falls back to position-only if areas are missing."""
    maxXY = np.maximum(Om.max(0), I.max(0))
    maxXY[maxXY == 0] = 1.0
    f1, f2 = Om / maxXY, I / maxXY
    if oct_area_um is not None and imm_area_um is not None and len(oct_area_um) == len(Om):
        mA = max(float(np.max(oct_area_um)), float(np.max(imm_area_um)), 1e-9)
        f1 = np.column_stack([f1, oct_area_um / mA])
        f2 = np.column_stack([f2, imm_area_um / mA])
    tI, tO = cKDTree(f2), cKDTree(f1)
    d1, j1 = tI.query(f1)
    _, j2 = tO.query(f2)
    shared = [(i, int(j1[i]), float(d1[i])) for i in range(len(f1))
              if d1[i] <= thr and j2[j1[i]] == i]
    return shared, {s[0] for s in shared}, {s[1] for s in shared}


def compute_aoi(T, oct_valid, imm_print, Hh, Ww):
    """Forward-map the OCT valid-tissue mask through transform T into the immuno frame to get
    `roi` (= objective-1's full ROI expressed in immuno pixels), then intersect with the
    immuno print body for `overlap` (= the AOI / "eerlijk gebied", where both modalities have
    signal). Shared by the CLI/GUI analyze step and the app's step-2 "compute overlay" preview,
    so the AOI the user sees before detection is exactly the AOI used for counting."""
    ys, xs = np.where(oct_valid > 0)
    sub = slice(None, None, 3)
    mapped = T.apply(np.stack([xs[sub], ys[sub]], 1).astype(float))
    roi = np.zeros((Hh, Ww), np.uint8)
    mx = np.clip(mapped[:, 0].astype(int), 0, Ww - 1)
    my = np.clip(mapped[:, 1].astype(int), 0, Hh - 1)
    roi[my, mx] = 1
    roi = cv2.morphologyEx(roi, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    roi = cv2.morphologyEx(roi, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    overlap = ((roi > 0) & (imm_print > 0)).astype(np.uint8)
    return roi, overlap


def _mutual_match(Om, I, radius):
    tO, tI = cKDTree(Om), cKDTree(I)
    dO, jO = tI.query(Om)
    _, jI = tO.query(I)
    shared = [(k, jO[k], dO[k]) for k in range(len(Om)) if dO[k] <= radius and jI[jO[k]] == k]
    return shared, {s[0] for s in shared}, {s[1] for s in shared}


def run(out_dir, points_path, oct_mm=(10.0, 10.0), transform_kind="affine",
        match_frac=0.45, radii_fracs=(0.35, 0.45, 0.55), match_margin_k=0.5,
        refine_with_pores=False, refine_iters=3, refine_weight=3, imm_points_path=None,
        match_method="mutual-nn", match_thresh=0.1):
    meta = json.load(open(os.path.join(out_dir, "meta.json")))
    oct_bgr = cv2.imread(meta["oct"])
    imm_bgr = cv2.imread(meta["imm"])
    Hh, Ww = imm_bgr.shape[:2]
    Hoct, Woct = oct_bgr.shape[:2]
    SX, SY = oct_mm[0] * 1000.0 / Woct, oct_mm[1] * 1000.0 / Hoct     # um/px

    Opts = np.load(os.path.join(out_dir, "oct_pts.npy")).astype(float)[:, ::-1]   # (x,y)
    if imm_points_path:                       # WI-E: use manually curated immuno pores
        cur = json.load(open(imm_points_path))["points"]
        Ipts = np.array(cur, float).reshape(-1, 2)          # already [x,y]
        imm_eqr = None
    else:
        Ipts = np.load(os.path.join(out_dir, "imm_pts.npy")).astype(float)[:, ::-1]
    oct_valid = np.load(os.path.join(out_dir, "oct_valid.npy"))
    imm_print = np.load(os.path.join(out_dir, "imm_valid.npy"))
    # per-immuno-pore region size (WI-4 match margin); only aligned when region is primary
    eqr_path = os.path.join(out_dir, "imm_equiv_radius.npy")
    imm_eqr = np.load(eqr_path) if os.path.exists(eqr_path) else None
    if imm_eqr is not None and len(imm_eqr) != len(Ipts):
        imm_eqr = None

    pj = json.load(open(points_path))["pairs"]
    O_lm = np.array([p["o"] for p in pj], float)
    I_lm = np.array([p["i"] for p in pj], float)

    # OCT pores within valid tissue = ROI
    oi = oct_valid[np.clip(Opts[:, 1].astype(int), 0, Hoct - 1),
                   np.clip(Opts[:, 0].astype(int), 0, Woct - 1)] > 0
    O = Opts[oi]

    # initial transform from manual landmarks
    T = Transform(transform_kind, O_lm, I_lm)

    def lm_resid(tr):
        d = np.linalg.norm(tr.apply(O_lm) - I_lm, axis=1)
        return float(d.mean()), float(d.max())
    res0_mean, res0_max = lm_resid(T)

    # WI-2: optional local refinement using matched pore correspondences (landmarks weighted
    # higher by duplication). Safe here because it is seeded from an already-good manual fit.
    refined = False
    res1_mean, res1_max, n_pore_pairs = res0_mean, res0_max, 0
    if refine_with_pores and transform_kind in ("affine", "similarity"):
        nn0 = _med_nn(Ipts)
        med_eqr_all = float(np.median(imm_eqr)) if imm_eqr is not None and len(imm_eqr) else 0.0
        r_ref = match_frac * nn0 + match_margin_k * med_eqr_all
        prev = res0_mean
        for _ in range(refine_iters):
            sh, _, _ = _mutual_match(T.apply(O), Ipts, r_ref)
            if len(sh) < 4:
                break
            m_oct = O[[s[0] for s in sh]]
            m_imm = Ipts[[s[1] for s in sh]]
            src = np.vstack([np.repeat(O_lm, refine_weight, axis=0), m_oct])
            dst = np.vstack([np.repeat(I_lm, refine_weight, axis=0), m_imm])
            T = Transform(transform_kind, src, dst)
            n_pore_pairs = len(sh)
            refined = True
            rm, _ = lm_resid(T)
            if abs(prev - rm) < 0.1:
                break
            prev = rm
        res1_mean, res1_max = lm_resid(T)

    tinfo = T.describe()
    tinfo["residual_mean_px"] = round(res1_mean, 2)      # report landmark residual, not union
    tinfo["residual_max_px"] = round(res1_max, 2)
    tinfo["refined_with_pores"] = refined
    tinfo["residual_landmarks_only_px"] = round(res0_mean, 2)
    tinfo["residual_after_refine_px"] = round(res1_mean, 2)
    tinfo["n_pore_pairs_used"] = n_pore_pairs
    Om = T.apply(O)
    roi, overlap = compute_aoi(T, oct_valid, imm_print, Hh, Ww)

    ii = roi[np.clip(Ipts[:, 1].astype(int), 0, Hh - 1),
             np.clip(Ipts[:, 0].astype(int), 0, Ww - 1)] > 0
    I = Ipts[ii]

    nn_imm = _med_nn(I)
    base_radius = match_frac * nn_imm                       # spacing-based term
    # WI-4: add an error margin for immuno's "halo" (excreted material) = k * median pore-region radius
    med_eqr = float(np.median(imm_eqr[ii])) if imm_eqr is not None and ii.any() else 0.0
    margin = match_margin_k * med_eqr
    radius = base_radius + margin

    # areas in µm² (for MATLAB position+area matching, OCT_FM); OCT via calibration,
    # immuno via the transform scale so both are comparable
    scale2 = max(abs(np.linalg.det(T.A)), 1e-9)
    oct_area_path = os.path.join(out_dir, "oct_area.npy")
    oct_area_all = np.load(oct_area_path) if os.path.exists(oct_area_path) else None
    oct_area_um = (oct_area_all[oi] * SX * SY) if oct_area_all is not None and len(oct_area_all) == len(Opts) else None
    imm_area_um = (np.pi * (imm_eqr[ii] ** 2) * SX * SY / scale2) if imm_eqr is not None and ii.any() else None

    sens = {}
    if match_method == "matlab":
        for th in (0.05, 0.1, 0.15):
            sh, mO, mI = _matlab_match(Om, I, oct_area_um, imm_area_um, th)
            sens[th] = (len(sh), len(O) - len(mO), len(I) - len(mI))
        shared, mO, mI = _matlab_match(Om, I, oct_area_um, imm_area_um, match_thresh)
    else:
        for fr in radii_fracs:
            sh, mO, mI = _mutual_match(Om, I, fr * nn_imm)
            sens[fr] = (len(sh), len(O) - len(mO), len(I) - len(mI))
        shared, mO, mI = _mutual_match(Om, I, radius)

    def in_ovl(xy):
        return overlap[np.clip(xy[:, 1].astype(int), 0, Hh - 1),
                       np.clip(xy[:, 0].astype(int), 0, Ww - 1)] > 0
    O_ovl, I_ovl = in_ovl(Om), in_ovl(I)
    sh_ovl = [s for s in shared if O_ovl[s[0]] and I_ovl[s[1]]]
    mO_o = {s[0] for s in sh_ovl}; mI_o = {s[1] for s in sh_ovl}

    # distances in micrometres
    def oct_um(xy):
        return np.stack([xy[:, 0] * SX, xy[:, 1] * SY], 1)

    def imm_um(xy):
        return oct_um(T.inverse(xy))

    O_sh_um = oct_um(O[[s[0] for s in shared]])
    I_sh_um = imm_um(I[[s[1] for s in shared]])
    pair_um = np.linalg.norm(O_sh_um - I_sh_um, axis=1) if shared else np.array([])
    ipd = {
        "matched_oct": _nn(O_sh_um) if len(shared) > 1 else np.array([]),
        "matched_imm": _nn(I_sh_um) if len(shared) > 1 else np.array([]),
        "all_oct": _nn(oct_um(O)),
        "all_imm": _nn(imm_um(I)),
    }
    roi_mm2 = float(oct_valid.sum() * SX * SY / 1e6)

    def st(a):
        a = np.asarray(a)
        if a.size == 0:
            return None
        return {"median": float(np.median(a)), "mean": float(a.mean()),
                "sd": float(a.std()), "n": int(a.size)}

    results = {
        "images": {"oct": meta["oct"], "imm": meta["imm"]},
        "calibration_um_per_px": {"x": SX, "y": SY, "oct_mm": list(oct_mm)},
        "transform": tinfo,
        "imm_detection": {"detector": meta.get("imm_detect"), "params": meta.get("imm_params"),
                          "rejected": meta.get("imm_rejected"), "region_mask": meta.get("imm_region_mask")},
        "roi_mm2": roi_mm2,
        "roi_covered_by_print_pct": round(100 * (overlap > 0).sum() / max((roi > 0).sum(), 1), 1),
        "counts_full_roi": {"oct": int(len(O)), "imm": int(len(I))},
        "counts_fair_region": {"oct": int(O_ovl.sum()), "imm": int(I_ovl.sum())},
        "match_radius_px": round(radius, 1),
        "match_radius_detail": {"base_frac_x_NN": round(base_radius, 1),
                                "margin_k_x_region": round(margin, 1),
                                "match_frac": match_frac, "margin_k": match_margin_k,
                                "median_region_radius_px": round(med_eqr, 1)},
        "matching_full_roi": {"shared": len(shared), "oct_only": len(O) - len(mO),
                              "imm_only": len(I) - len(mI)},
        "matching_fair_region": {"shared": len(sh_ovl),
                                 "oct_only": int(O_ovl.sum() - len(mO_o)),
                                 "imm_only": int(I_ovl.sum() - len(mI_o))},
        "match_method": match_method,
        "match_radius_sensitivity": {
            (f"thr={k:.2f}" if match_method == "matlab" else f"{k:.2f}xNN"):
            {"shared": v[0], "oct_only": v[1], "imm_only": v[2]} for k, v in sens.items()},
        "interpore_distance_um": {k: st(v) for k, v in ipd.items()},
        "matched_pair_agreement_um": st(pair_um),
        "density_per_mm2": {"oct": round(len(O) / roi_mm2, 2), "imm": round(len(I) / roi_mm2, 2)},
    }

    # CSV of matched pairs
    with open(os.path.join(out_dir, "matched_pairs.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["oct_x_px", "oct_y_px", "imm_x_px", "imm_y_px", "pair_dist_um"])
        for (k, j, _), r in zip(shared, pair_um):
            w.writerow([f"{O[k,0]:.1f}", f"{O[k,1]:.1f}", f"{I[j,0]:.1f}", f"{I[j,1]:.1f}", f"{r:.1f}"])

    # WI-5: nearest-neighbour tables + numbered pore maps
    oct_gray = cv2.cvtColor(oct_bgr, cv2.COLOR_BGR2GRAY)
    imm_gray = imm_bgr[:, :, 2]
    mO_idx = [s[0] for s in shared]; mI_idx = [s[1] for s in shared]
    oct_rows = _nn_rows(O, oct_um(O))
    imm_rows = _nn_rows(I, imm_um(I))
    matched_rows = _nn_rows(O[mO_idx], oct_um(O[mO_idx])) if mO_idx else []
    _save_nn_csv(os.path.join(out_dir, "oct_nn.csv"), oct_rows)
    _save_nn_csv(os.path.join(out_dir, "imm_nn.csv"), imm_rows)
    _save_nn_csv(os.path.join(out_dir, "matched_nn.csv"), matched_rows)
    _save_numbered_map(oct_gray, O, oct_rows, os.path.join(out_dir, "oct_pores_numbered.png"), (230, 33, 138))
    _save_numbered_map(imm_gray, I, imm_rows, os.path.join(out_dir, "imm_pores_numbered.png"), (0, 180, 240))
    if mI_idx:
        _save_numbered_map(imm_gray, I[mI_idx], matched_rows,
                           os.path.join(out_dir, "matched_numbered.png"), (31, 157, 85))
    results["nn_tables"] = {"oct": "oct_nn.csv", "imm": "imm_nn.csv", "matched": "matched_nn.csv"}
    results["numbered_maps"] = {"oct": "oct_pores_numbered.png", "imm": "imm_pores_numbered.png",
                                "matched": "matched_numbered.png" if mI_idx else None}
    results["nn_angle_convention"] = "atan2(dy,dx) degrees; x=right, y=down; 0°=right, +=clockwise"

    _save_viz(out_dir, imm_bgr, roi, overlap, Om, I, shared, mO, mI)
    _save_overlay(out_dir, oct_bgr, imm_bgr, T, O_lm, I_lm, overlap=overlap)
    json.dump(results, open(os.path.join(out_dir, "results.json"), "w"), indent=2)
    _write_report(out_dir, results)
    results["report_html"] = report.build(out_dir, results,
                                          date_str=datetime.now().strftime("%Y-%m-%d %H:%M"))
    results["overlay_viewer_html"] = overlay_viewer.build(out_dir)
    try:
        from . import export_excel
        results["excel"] = export_excel.build(out_dir, results, meta)
    except Exception as e:
        print("Excel export skipped:", e)
    try:
        from . import protocol
        results["protocol"] = protocol.build(out_dir, results, meta)
    except Exception as e:
        print("Protocol export skipped:", e)
    return results


def _save_viz(out_dir, imm_bgr, roi, overlap, Om, I, shared, mO, mI):
    vis = cv2.cvtColor(enhance(imm_bgr[:, :, 2]), cv2.COLOR_GRAY2BGR)
    for m, col in [(roi, (0, 165, 255)), (overlap, (255, 120, 0))]:
        c, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, c, -1, col, 2)
    for k in range(len(Om)):
        if k not in mO:
            cv2.drawMarker(vis, tuple(Om[k].astype(int)), (255, 0, 255), cv2.MARKER_TILTED_CROSS, 12, 2)
    for j in range(len(I)):
        if j not in mI:
            cv2.circle(vis, tuple(I[j].astype(int)), 6, (0, 255, 255), 2)
    for (k, j, _) in shared:
        cv2.circle(vis, tuple(I[j].astype(int)), 7, (0, 255, 0), 2)
        cv2.line(vis, tuple(Om[k].astype(int)), tuple(I[j].astype(int)), (0, 255, 0), 1)
    ys, xs = np.where(roi > 0)
    if len(xs):
        x0, y0 = max(0, xs.min() - 30), max(0, ys.min() - 30)
        x1, y1 = min(vis.shape[1], xs.max() + 30), min(vis.shape[0], ys.max() + 30)
        crop = vis[y0:y1, x0:x1].copy()
    else:
        crop = vis
    cv2.putText(crop, "green=shared  magenta=OCT-only  yellow=immuno-only", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(os.path.join(out_dir, "analysis.png"), crop)


def _save_overlay(out_dir, oct_bgr, imm_bgr, T, O_lm, I_lm, overlap=None):
    """Write the full-ROI overlay, and (WI-3) an AOI-only overlay dimmed outside the AOI."""
    Hh, Ww = imm_bgr.shape[:2]
    M = np.hstack([T.A, T.t.reshape(2, 1)]).astype(np.float32)
    warp = cv2.warpAffine(oct_bgr, M, (Ww, Hh))
    wg = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)
    over = imm_bgr.copy()
    over[:, :, 1] = np.maximum(over[:, :, 1], imm_bgr[:, :, 2])
    over[:, :, 2] = np.maximum(over[:, :, 2], wg)
    over[:, :, 0] = np.maximum(over[:, :, 0], wg)
    for (ox, oy), (ix, iy) in zip(O_lm, I_lm):
        px, py = T.apply([[ox, oy]])[0].astype(int)
        cv2.circle(over, (px, py), 9, (255, 255, 0), 2)
        cv2.circle(over, (int(ix), int(iy)), 5, (0, 255, 255), -1)
    corners = np.array([[0, 0], [oct_bgr.shape[1], 0], [oct_bgr.shape[1], oct_bgr.shape[0]],
                        [0, oct_bgr.shape[0]]], float)
    cc = T.apply(corners)
    x0, y0 = np.maximum(cc.min(0).astype(int) - 30, 0)
    x1, y1 = np.minimum(cc.max(0).astype(int) + 30, [Ww, Hh])
    cv2.imwrite(os.path.join(out_dir, "overlay.png"), over[y0:y1, x0:x1])
    # aligned layers for the interactive viewer (WI-8), same crop = same pixel grid
    cv2.imwrite(os.path.join(out_dir, "layer_oct.png"), wg[y0:y1, x0:x1])
    cv2.imwrite(os.path.join(out_dir, "layer_imm.png"), enhance(imm_bgr[:, :, 2])[y0:y1, x0:x1])

    if overlap is not None and overlap.any():
        aoi = over.copy()
        outside = overlap == 0
        aoi[outside] = (aoi[outside] * 0.25).astype(np.uint8)      # dim non-AOI
        c, _ = cv2.findContours(overlap, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(aoi, c, -1, (255, 120, 0), 2)
        ys, xs = np.where(overlap > 0)
        ax0, ay0 = max(0, xs.min() - 20), max(0, ys.min() - 20)
        ax1, ay1 = min(Ww, xs.max() + 20), min(Hh, ys.max() + 20)
        cv2.imwrite(os.path.join(out_dir, "overlay_aoi.png"), aoi[ay0:ay1, ax0:ax1])


def _write_report(out_dir, r):
    def line(s):
        return s + "\n"
    ipd = r["interpore_distance_um"]

    def fmt(d):
        return f"median={d['median']:.0f} mean={d['mean']:.0f} sd={d['sd']:.0f} n={d['n']}" if d else "n/a"
    md = []
    md += [line(f"# Poriën-analyse — {os.path.basename(r['images']['oct'])} ↔ {os.path.basename(r['images']['imm'])}")]
    t = r["transform"]
    md += [line(f"\n**Transform** ({t['kind']}): residu {t['residual_mean_px']:.1f} px gem "
                f"(max {t['residual_max_px']:.1f}), schaal {t['scale']:.3f}, rotatie {t['rotation_deg']:.1f}°, "
                f"as-hoek {t['axis_angle_deg']:.1f}° · {t['n_points']} punten")]
    md += [line(f"**ROI** {r['roi_mm2']:.1f} mm² · {r['roi_covered_by_print_pct']}% valt binnen de immuno-afdruk")]
    md += [line("\n## 1 · Telling")]
    md += [line(f"- volledige ROI: OCT **{r['counts_full_roi']['oct']}** · immuno **{r['counts_full_roi']['imm']}**")]
    md += [line(f"- eerlijk gebied: OCT **{r['counts_fair_region']['oct']}** · immuno **{r['counts_fair_region']['imm']}**")]
    md += [line(f"- dichtheid: OCT {r['density_per_mm2']['oct']} /mm² · immuno {r['density_per_mm2']['imm']} /mm²")]
    md += [line("\n## 2 · Matching (eerlijk gebied)")]
    fm = r["matching_fair_region"]
    md += [line(f"- gedeeld **{fm['shared']}** · alleen-OCT **{fm['oct_only']}** · alleen-immuno **{fm['imm_only']}**")]
    md += [line(f"- match-straal {r['match_radius_px']} px; gevoeligheid: "
                + ", ".join(f"{k}: {v['shared']}" for k, v in r['match_radius_sensitivity'].items()))]
    pa = r["matched_pair_agreement_um"]
    md += [line(f"- positie-overeenkomst gematchte paren: {fmt(pa)} µm")]
    md += [line("\n## 3 · Interporie-afstand (nearest-neighbour, µm)")]
    md += [line(f"- alle ROI-poriën OCT (beste schatting): {fmt(ipd['all_oct'])}")]
    md += [line(f"- alle ROI-poriën immuno: {fmt(ipd['all_imm'])}")]
    md += [line(f"- gematchte poriën OCT: {fmt(ipd['matched_oct'])} · immuno: {fmt(ipd['matched_imm'])}")]
    md += [line("\n_Bestanden: overlay.png · analysis.png · matched_pairs.csv · results.json_")]
    open(os.path.join(out_dir, "RESULTS.md"), "w", encoding="utf-8").writelines(md)
