"""Pore detection: small bright blobs via white top-hat + local maxima.

Two modes:
  oct : grayscale image; validity = bright tissue (excludes black bands/artefacts).
  imm : one colour channel (default red); validity = print body (largest connected component),
        which drops the ruler, stray objects and background speckle.
Threshold is adaptive by default (knee of the peak-count vs threshold curve).
"""
import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.morphology import white_tophat, disk
from skimage.filters import threshold_otsu
from skimage.measure import label, regionprops
from skimage.segmentation import watershed

CHANNELS = {"blue": 0, "green": 1, "red": 2}

# artefact classes (WI-C); None (kept) is drawn green, rejects in shades of red/orange
REJECT_REASONS = ("speckle", "merged", "ridge", "irregular", "noncircular")


def enhance(gray):
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16)).apply(gray)


def adaptive_threshold(th, valid, min_dist, n=16, flat_frac=0.30):
    """Sweep threshold vs. peak-count; return the threshold where the count first
    flattens relative to the initial steep drop (end of the noise cliff)."""
    v = th[valid > 0]
    lo, hi = np.percentile(v, 70), np.percentile(v, 99)
    ts = np.linspace(lo, hi, n)
    base = th.astype(float) * (valid > 0)
    counts = np.array([peak_local_max(base, min_distance=min_dist,
                                      threshold_abs=float(t)).shape[0] for t in ts], float)
    drops = np.maximum(-np.diff(counts), 0.0)      # per-step decrease
    if drops.max() <= 0:
        return float(lo)
    ref = drops[:2].max()                          # initial steepness
    thr_drop = flat_frac * ref
    idx = next((i for i in range(1, len(drops)) if drops[i] < thr_drop), int(np.argmin(drops)))
    return float(ts[idx])


def _valid_oct(gray, dark=25, erode=9):
    m = (gray > dark).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    return cv2.erode(m, np.ones((erode, erode), np.uint8))


def _valid_print(chan, blur_sigma=25, pct=85, close=41, erode=6):
    blur = cv2.GaussianBlur(chan, (0, 0), blur_sigma)
    m = (blur > np.percentile(blur, pct)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return m
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    v = (lab == big).astype(np.uint8)
    v = cv2.morphologyEx(v, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    # fill holes
    ff = v.copy(); h, w = ff.shape
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 1)
    v = (v | (1 - ff)).astype(np.uint8)
    return cv2.erode(v, np.ones((erode, erode), np.uint8))


def detect(image_bgr, mode="oct", channel="red", tophat=9, min_dist=14, thr=None):
    if mode == "oct":
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
        valid = _valid_oct(gray)
    elif mode == "imm":
        gray = image_bgr[:, :, CHANNELS[channel]] if image_bgr.ndim == 3 else image_bgr
        valid = _valid_print(gray)
    else:
        raise ValueError(f"unknown mode {mode}")

    g = cv2.GaussianBlur(gray, (0, 0), 1.1)
    th = white_tophat(g, disk(tophat))
    if thr is None:
        thr = adaptive_threshold(th, valid, min_dist)
    pts = peak_local_max(th.astype(float) * (valid > 0), min_distance=min_dist,
                         threshold_abs=float(thr))                # (y,x)
    return dict(points=pts, valid=valid, gray=gray, tophat=th, thr=float(thr))


def draw(gray, pts, color=(0, 0, 255), r=6):
    vis = cv2.cvtColor(enhance(gray), cv2.COLOR_GRAY2BGR)
    for (y, x) in pts:
        cv2.circle(vis, (int(x), int(y)), r, color, 2, cv2.LINE_AA)
    return vis


def optimize_imm(image_bgr, channel="red", bg_sigma=None, pore_diam=None,
                 clip=(1.0, 99.5), clahe=False):
    """WI-A — reproducible immuno image optimisation (white/black balance).

    Provisional stand-in for the user's manual BW step; built modular so the exact MATLAB
    white/black-balance can replace the body later without touching detection (A–F).
    Steps, all logged: (1) large-scale background subtraction (Gaussian, ~2× pore diameter)
    to flatten ridge/illumination; (2) percentile-clip contrast stretch (black/white balance);
    (3) optional CLAHE. Detection runs on THIS image; CLAHE-for-display stays separate.
    Returns (optimized_uint8, params)."""
    gray = image_bgr[:, :, CHANNELS[channel]] if image_bgr.ndim == 3 else image_bgr
    if bg_sigma is None:
        d = pore_diam if pore_diam else 8.0
        bg_sigma = float(max(6.0, 2.0 * d))
    f = gray.astype(np.float32)
    bg = cv2.GaussianBlur(f, (0, 0), bg_sigma)
    fg = np.clip(f - bg, 0, None)
    lo, hi = np.percentile(fg, clip[0]), np.percentile(fg, clip[1])
    out = np.clip((fg - lo) / (hi - lo + 1e-6) * 255.0, 0, 255).astype(np.uint8)
    if clahe:
        out = enhance(out)
    params = {"method": "gaussian-bg-subtract+percentile-stretch",
              "bg_sigma": round(bg_sigma, 1), "clip_pct": list(clip), "clahe": bool(clahe),
              "note": "provisional default; replace with MATLAB white/black balance"}
    return out, params


def estimate_pore_diameter(gray, valid, min_area=4):
    """WI-B — estimate typical pore diameter (px) from a rough Otsu segmentation, so all
    thresholds can be expressed relative to the data rather than as absolute pixels."""
    vals = gray[valid > 0]
    if vals.size == 0:
        return 8.0
    t = threshold_otsu(vals)
    bw = (gray > t) & (valid > 0)
    ar = np.array([p.area for p in regionprops(label(bw)) if p.area >= min_area])
    if ar.size == 0:
        return 8.0
    return float(2.0 * np.sqrt(np.median(ar) / np.pi))


def _circularity(p):
    try:
        per = p.perimeter_crofton
    except Exception:
        per = p.perimeter
    return (4.0 * np.pi * p.area / (per * per)) if per > 0 else 0.0


def _classify(p, min_area, max_area, circ_thr, sol_thr, ecc_max):
    """Return a rejection reason (WI-C) or None to keep. Size first, then shape."""
    if p.area < min_area:
        return "speckle"
    if p.area > max_area:
        return "merged"                      # too large / fused smear
    if p.eccentricity > ecc_max:
        return "ridge"                       # elongated ridge fragment
    if p.solidity < sol_thr:
        return "irregular"                   # not compact
    if _circularity(p) < circ_thr:
        return "noncircular"
    return None


def _split_merged(submask, min_dist):
    """distance-transform + watershed to recover fused pores; returns list of (cy,cx,area)."""
    dist = ndi.distance_transform_edt(submask)
    peaks = peak_local_max(dist, min_distance=max(3, int(min_dist)), labels=submask)
    if len(peaks) < 2:
        return []
    seeds = np.zeros(dist.shape, np.int32)
    for i, (y, x) in enumerate(peaks, 1):
        seeds[y, x] = i
    ws = watershed(-dist, seeds, mask=submask)
    return [(p.centroid[0], p.centroid[1], p.area) for p in regionprops(ws)]


def detect_regions_imm(image_bgr, channel="red", region_mask=None, optimize=True,
                       pore_diam=None, min_area_frac=0.15, max_area_frac=6.0,
                       circularity_thresh=0.15, solidity_thresh=0.40, max_eccentricity=0.97,
                       merged_blobs="split"):
    """Region/centroid immuno pore detection (WI-1 refined by annotation_improvement_plan).

    Pipeline: optimise (WI-A) → estimate pore size (WI-B) → Otsu → connected components →
    scale-aware size band + shape filters with logged rejection reasons (WI-C). Merged blobs
    are either split (watershed) or rejected. `region_mask` (WI-G) restricts everything to a
    user-selected area; if None the print body is used. Returns kept centroids + per-region
    shape metrics AND a `rejections` list (reason per discarded blob) for auditing.
    """
    gray = image_bgr[:, :, CHANNELS[channel]] if image_bgr.ndim == 3 else image_bgr
    valid = (region_mask.astype(np.uint8) if region_mask is not None else _valid_print(gray))

    if optimize:
        d0 = pore_diam or estimate_pore_diameter(gray, valid)
        opt, opt_params = optimize_imm(gray, channel=channel, pore_diam=d0)
    else:
        opt, opt_params = gray, {"method": "none"}

    diam = pore_diam or estimate_pore_diameter(opt, valid)
    med_area = np.pi * (diam / 2.0) ** 2
    min_area = max(3.0, min_area_frac * med_area)
    max_area = max_area_frac * med_area
    split_min_dist = max(3.0, 0.7 * diam)

    vals = opt[valid > 0]
    thr = float(threshold_otsu(vals)) if vals.size else 0.0
    bw = (opt > thr) & (valid > 0)
    lab = label(bw)

    kept, rej = [], []

    def _keep(cy, cx, area, ecc=0.0, sol=1.0, circ=1.0):
        kept.append({"y": cy, "x": cx, "area": float(area),
                     "equiv_radius": float(np.sqrt(area / np.pi)),
                     "eccentricity": float(ecc), "solidity": float(sol),
                     "circularity": float(min(circ, 1.0))})

    for p in regionprops(lab):
        reason = _classify(p, min_area, max_area, circularity_thresh, solidity_thresh, max_eccentricity)
        if reason is None:
            _keep(p.centroid[0], p.centroid[1], p.area, p.eccentricity, p.solidity, _circularity(p))
        elif reason == "merged" and merged_blobs == "split":
            y0, x0, _, _ = p.bbox
            subs = [(sy, sx, sa) for (sy, sx, sa) in _split_merged(p.image, split_min_dist)
                    if min_area <= sa <= max_area]
            if len(subs) >= 2:                       # genuinely fused -> recover parts
                for (sy, sx, sa) in subs:
                    _keep(sy + y0, sx + x0, sa)
            else:                                    # not separable -> a single large pore
                _keep(p.centroid[0], p.centroid[1], p.area, p.eccentricity, p.solidity, _circularity(p))
        else:
            rej.append({"y": p.centroid[0], "x": p.centroid[1], "area": float(p.area), "reason": reason})

    pts = np.array([[k["y"], k["x"]] for k in kept], float).reshape(-1, 2)
    return dict(points=pts, valid=valid, gray=gray, optimized=opt, labels=lab, thr=thr,
                area=np.array([k["area"] for k in kept], float),
                equiv_radius=np.array([k["equiv_radius"] for k in kept], float),
                circularity=np.array([k["circularity"] for k in kept], float),
                eccentricity=np.array([k["eccentricity"] for k in kept], float),
                solidity=np.array([k["solidity"] for k in kept], float),
                kept=kept, rejections=rej,
                params={"pore_diam_px": round(diam, 2), "min_area": round(min_area, 1),
                        "max_area": round(max_area, 1), "circularity_thresh": circularity_thresh,
                        "solidity_thresh": solidity_thresh, "max_eccentricity": max_eccentricity,
                        "merged_blobs": merged_blobs, "otsu_thr": round(thr, 1),
                        "optimize": opt_params})


def draw_regions(gray, det, color=(0, 0, 255), number=False, on_optimized=False):
    """Blob outlines + red-cross centroids (+ optional numbering)."""
    base = det.get("optimized") if (on_optimized and "optimized" in det) else enhance(gray)
    vis = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    if "labels" in det:
        keep = np.zeros(det["labels"].shape, np.uint8)
        lab = det["labels"]
        for (y, x) in det["points"]:
            lb = lab[int(round(y)), int(round(x))]
            if lb > 0:
                keep[lab == lb] = 255
        cnts, _ = cv2.findContours(keep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, cnts, -1, (0, 200, 255), 1, cv2.LINE_AA)
    for i, (y, x) in enumerate(det["points"], 1):
        xi, yi = int(round(x)), int(round(y))
        cv2.drawMarker(vis, (xi, yi), color, cv2.MARKER_CROSS, 9, 1, cv2.LINE_AA)
        if number:
            cv2.putText(vis, str(i), (xi + 4, yi - 4), cv2.FONT_HERSHEY_SIMPLEX,
                        0.35, (0, 255, 0), 1, cv2.LINE_AA)
    return vis


_REASON_COLOR = {"speckle": (0, 140, 255), "merged": (0, 0, 255), "ridge": (0, 0, 200),
                 "irregular": (60, 60, 255), "noncircular": (0, 90, 200)}


def draw_rejections(det):
    """WI-C/D overlay: kept pores green, rejected artefacts coloured by reason, on the
    optimised image so it matches what detection actually saw."""
    base = det.get("optimized")
    base = base if base is not None else enhance(det["gray"])
    vis = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    for (y, x) in det["points"]:
        cv2.drawMarker(vis, (int(round(x)), int(round(y))), (0, 220, 0), cv2.MARKER_CROSS, 9, 1, cv2.LINE_AA)
    for r in det.get("rejections", []):
        cv2.circle(vis, (int(round(r["x"])), int(round(r["y"]))), 5,
                   _REASON_COLOR.get(r["reason"], (0, 0, 255)), 1, cv2.LINE_AA)
    return vis
