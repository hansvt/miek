"""Sanity-check ridge orientation fields; produce enhanced + orientation-colored views."""
import cv2, numpy as np, os
from orient import orientation_field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")


def enhance(gray, mask=None):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
    e = clahe.apply(gray)
    return e


def orient_rgb(gray, mask):
    th, coh = orientation_field(gray, 1.5, 10.0)
    hue = ((th % np.pi) / np.pi * 179).astype(np.uint8)
    sat = np.full_like(hue, 255)
    val = cv2.normalize(np.clip(coh, 0, 1), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    hsv = cv2.merge([hue, sat, val])
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    rgb[mask == 0] = 0
    return rgb


def quiver(gray, mask, step=28):
    th, coh = orientation_field(gray, 1.5, 10.0)
    vis = cv2.cvtColor(enhance(gray), cv2.COLOR_GRAY2BGR)
    H, W = gray.shape
    for y in range(step, H - step, step):
        for x in range(step, W - step, step):
            if mask[y, x] == 0 or coh[y, x] < 0.1:
                continue
            a = th[y, x]
            dx, dy = np.cos(a) * step * 0.45, np.sin(a) * step * 0.45
            # ridge direction is perpendicular to gradient-orientation theta? theta here is
            # tensor orientation = ridge-normal; ridge tangent = theta + pi/2
            tx, ty = -np.sin(a) * step * 0.45, np.cos(a) * step * 0.45
            cv2.line(vis, (int(x - tx), int(y - ty)), (int(x + tx), int(y + ty)), (0, 255, 255), 1, cv2.LINE_AA)
    return vis


octg = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
octm = (octg > 25).astype(np.uint8); octm = cv2.erode(octm, np.ones((25, 25), np.uint8))
immr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
blur = cv2.GaussianBlur(immr, (0, 0), 25); m = (blur > np.percentile(blur, 85)).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(m); big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
immm = (lab == big).astype(np.uint8); immm = cv2.morphologyEx(immm, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))

cv2.imwrite(os.path.join(OUT, "oct_enh.png"), enhance(octg))
cv2.imwrite(os.path.join(OUT, "imm_enh.png"), enhance(immr))
cv2.imwrite(os.path.join(OUT, "oct_quiver.png"), quiver(octg, octm))
cv2.imwrite(os.path.join(OUT, "imm_quiver.png"), quiver(immr, immm))
# crop immuno enhanced to print bbox for visibility
ys, xs = np.where(immm > 0)
cv2.imwrite(os.path.join(OUT, "imm_enh_crop.png"), enhance(immr)[ys.min():ys.max(), xs.min():xs.max()])
cv2.imwrite(os.path.join(OUT, "imm_quiver_crop.png"), quiver(immr, immm)[ys.min():ys.max(), xs.min():xs.max()])
print("done", "imm bbox", xs.min(), ys.min(), xs.max(), ys.max())
