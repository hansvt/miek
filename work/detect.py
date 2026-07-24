"""Pore detection in OCT and immunolabel fingerprint images.
Outputs overlays to out/ for visual review before registration.
"""
import cv2, numpy as np, json, os
from skimage.feature import peak_local_max
from skimage.morphology import white_tophat, disk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

OCT_PATH = os.path.join(ROOT, "images", "2lindex_.jpg")
IMM_PATH = os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG")


def save(name, img):
    cv2.imwrite(os.path.join(OUT, name), img)
    print("wrote", name, img.shape)


def draw_points(base_gray, pts, color=(0, 0, 255), r=6):
    vis = cv2.cvtColor(base_gray, cv2.COLOR_GRAY2BGR)
    for (y, x) in pts:
        cv2.circle(vis, (int(x), int(y)), r, color, 2, cv2.LINE_AA)
    return vis


# ---------- OCT ----------
def detect_oct():
    bgr = cv2.imread(OCT_PATH)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape

    # validity mask: exclude near-black artifact regions (left band, bottom-left, black scan lines)
    valid = (gray > 25).astype(np.uint8)
    # erode so pores near black edges/scan-line artifacts aren't spurious
    valid = cv2.erode(valid, disk(5))

    # small bright blobs via white tophat (pore diameter ~ up to ~15px)
    g = cv2.GaussianBlur(gray, (0, 0), 1.0)
    th = white_tophat(g, disk(9))
    save("oct_tophat.png", cv2.normalize(th, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8))

    thr = 35.0  # tuned: knee of peak-count vs threshold curve
    # peak detection to get one point per pore
    pts = peak_local_max(th.astype(float) * (valid > 0), min_distance=14,
                         threshold_abs=float(thr))
    print(f"OCT: {len(pts)} candidate pores (thr={thr:.1f})")

    vis = draw_points(gray, pts)
    save("oct_pores.png", vis)
    np.save(os.path.join(OUT, "oct_pts.npy"), pts)
    cv2.imwrite(os.path.join(OUT, "oct_valid.png"), valid * 255)
    return pts, gray


# ---------- Immunolabel ----------
def detect_imm():
    bgr = cv2.imread(IMM_PATH)
    b, g, r = cv2.split(bgr)
    # signal is in the red channel
    red = r.copy()
    H, W = red.shape

    # isolate the print body: heavy blur -> threshold -> largest connected component
    blur = cv2.GaussianBlur(red, (0, 0), 25)
    m = (blur > np.percentile(blur, 85)).astype(np.uint8)
    nlab, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    valid = (lab == big).astype(np.uint8)
    valid = cv2.morphologyEx(valid, cv2.MORPH_CLOSE, disk(30))
    # fill holes
    ff = valid.copy()
    hh, ww = ff.shape
    fmask = np.zeros((hh + 2, ww + 2), np.uint8)
    cv2.floodFill(ff, fmask, (0, 0), 1)
    valid = (valid | (1 - ff)).astype(np.uint8)
    valid = cv2.erode(valid, disk(6))

    g2 = cv2.GaussianBlur(red, (0, 0), 1.2)
    th = white_tophat(g2, disk(11))
    save("imm_tophat.png", cv2.normalize(th, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8))

    thr = 18.0  # tuned below
    pts = peak_local_max(th.astype(float) * (valid > 0), min_distance=16,
                         threshold_abs=float(thr))
    print(f"IMM: {len(pts)} candidate pores (thr={thr:.1f})")

    vis = draw_points(red, pts, color=(0, 255, 0))
    save("imm_pores.png", vis)
    np.save(os.path.join(OUT, "imm_pts.npy"), pts)
    cv2.imwrite(os.path.join(OUT, "imm_valid.png"), valid * 255)
    cv2.imwrite(os.path.join(OUT, "imm_red.png"), red)
    return pts, red


if __name__ == "__main__":
    op, og = detect_oct()
    ip, ir = detect_imm()
    print("done")
