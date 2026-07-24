"""WI-D — validate immuno pore detection against the reference (geselecteerd_gebied_bw.jpg,
"Analyse van 316 poriën"). 316 is a sanity-check anchor, not a hard target: the visual
kept/rejected overlays lead. Prints count + per-reason rejection tally and writes overlays."""
import os
import sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from porepair import detect as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

ref = cv2.imread(os.path.join(ROOT, "images", "geselecteerd_gebied_bw.jpg"))
mask = np.ones(ref.shape[:2], np.uint8)     # the reference IS the selected region

# reference is already BW-optimised -> optimize=True is ~idempotent, but test both
for optimize in (True, False):
    det = D.detect_regions_imm(ref, channel="red", region_mask=mask, optimize=optimize,
                               merged_blobs="split")
    reasons = {}
    for r in det["rejections"]:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    print(f"optimize={optimize}: kept={len(det['points'])} (ref ~316)  rejected={len(det['rejections'])}  "
          f"{reasons}  pore_diam={det['params']['pore_diam_px']}px")
    tag = "opt" if optimize else "raw"
    cv2.imwrite(os.path.join(OUT, f"val_kept_{tag}.png"), D.draw_regions(det["gray"], det, on_optimized=True))
    cv2.imwrite(os.path.join(OUT, f"val_rejected_{tag}.png"), D.draw_rejections(det))
print("wrote val_kept_*.png / val_rejected_*.png")
