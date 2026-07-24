"""Produce coordinate-gridded enhanced reference images so corresponding landmark
points can be read off in native full-image pixel coordinates."""
import cv2, numpy as np, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
clahe = cv2.createCLAHE(3.0, (16, 16))


def label(vis, txt, org):
    cv2.putText(vis, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(vis, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)


def grid(img_gray, step=100, label_step=200, origin=(0, 0)):
    vis = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    H, W = img_gray.shape
    ox, oy = origin
    for x in range(0, W, step):
        big = (x + ox) % label_step == 0
        cv2.line(vis, (x, 0), (x, H), (0, 130, 255) if big else (60, 90, 110), 2 if big else 1, cv2.LINE_AA)
        if big:
            label(vis, str(x + ox), (x + 3, 26))
            label(vis, str(x + ox), (x + 3, H - 8))
    for y in range(0, H, step):
        big = (y + oy) % label_step == 0
        cv2.line(vis, (0, y), (W, y), (0, 130, 255) if big else (60, 90, 110), 2 if big else 1, cv2.LINE_AA)
        if big:
            label(vis, str(y + oy), (4, y - 5))
            label(vis, str(y + oy), (W - 60, y - 5))
    return vis


# OCT (full frame, native coords)
octg = cv2.cvtColor(cv2.imread(os.path.join(ROOT, "images", "2lindex_.jpg")), cv2.COLOR_BGR2GRAY)
cv2.imwrite(os.path.join(OUT, "oct_grid.png"), grid(clahe.apply(octg)))

# IMM enhanced, cropped to print bbox (labels in FULL-image coords via origin offset)
immr = cv2.imread(os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))[:, :, 2]
imm_e = clahe.apply(immr)
x0, y0, x1, y1 = 1060, 350, 2450, 1160
crop = imm_e[y0:y1, x0:x1]
vis = grid(crop, origin=(x0, y0))
# mark detected immuno core
cv2.circle(vis, (1596 - x0, 780 - y0), 16, (0, 0, 255), 3)
cv2.putText(vis, "CORE(1596,780)", (1596 - x0 + 12, 780 - y0), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
cv2.imwrite(os.path.join(OUT, "imm_grid.png"), vis)
print("wrote oct_grid.png", octg.shape, "and imm_grid.png (crop origin", (x0, y0), ")")
