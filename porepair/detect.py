"""Pore detection: small bright blobs via white top-hat + local maxima.

Two modes:
  oct : grayscale image; validity = bright tissue (excludes black bands/artefacts).
  imm : one colour channel (default red); validity = print body (largest connected component),
        which drops the ruler, stray objects and background speckle.
Threshold is adaptive by default (knee of the peak-count vs threshold curve).
"""
import cv2
import numpy as np
from skimage.feature import peak_local_max
from skimage.morphology import white_tophat, disk
from skimage.filters import threshold_otsu
from skimage.measure import label, regionprops

CHANNELS = {"blue": 0, "green": 1, "red": 2}


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


def detect_regions_imm(image_bgr, channel="red", blur_sigma=1.2, tophat_radius=11,
                       min_area=15, circularity_thresh=0.40, max_area=None):
    """Region/centroid immuno pore detection (WI-1).

    The immuno signal is excreted material *around* the pore, so each pore is a small
    roundish blob sitting on the (brighter, continuous) ridge. Working from the RAW channel
    (no CLAHE — CLAHE is only for display/picking and would make ridge lines pop as false
    blobs): a white top-hat removes the broad ridge so individual pore beads remain as
    separated bumps, Otsu binarises those, and we keep round-enough blobs and take their
    centroids. Returns centroids + per-region area, equivalent radius and circularity
    (the region size is the natural matching error margin, see WI-4).
    """
    gray = image_bgr[:, :, CHANNELS[channel]] if image_bgr.ndim == 3 else image_bgr
    valid = _valid_print(gray)
    g = cv2.GaussianBlur(gray, (0, 0), blur_sigma)
    th = white_tophat(g, disk(tophat_radius)).astype(np.float32)   # beads minus ridge
    vals = th[valid > 0]
    thr = float(threshold_otsu(vals)) if vals.size else 0.0
    bw = (th > thr) & (valid > 0)
    if max_area is None:
        max_area = int(0.02 * valid.sum())          # drop implausibly large merged blobs
    lab = label(bw)

    pts, area, eqr, circ = [], [], [], []
    for p in regionprops(lab):
        if p.area < min_area or p.area > max_area:
            continue
        try:
            per = p.perimeter_crofton
        except Exception:
            per = p.perimeter
        if per <= 0:
            continue
        c = 4.0 * np.pi * p.area / (per * per)
        if c < circularity_thresh:
            continue
        y, x = p.centroid
        pts.append((y, x)); area.append(p.area)
        eqr.append(np.sqrt(p.area / np.pi)); circ.append(min(c, 1.0))
    pts = np.array(pts, float).reshape(-1, 2)
    return dict(points=pts, valid=valid, gray=gray, labels=lab, thr=thr,
                area=np.array(area, float), equiv_radius=np.array(eqr, float),
                circularity=np.array(circ, float))


def draw_regions(gray, det, color=(0, 0, 255), number=False):
    """Blob outlines + red-cross centroids (+ optional numbering), on the enhanced image."""
    vis = cv2.cvtColor(enhance(gray), cv2.COLOR_GRAY2BGR)
    if "labels" in det:
        keep = np.zeros(det["labels"].shape, np.uint8)
        # rebuild a mask of kept regions from centroids' labels
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
