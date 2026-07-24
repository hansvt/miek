"""Headless smoke test for the 3-step wizard app: simulate the full flow without file dialogs."""
import os
import sys
import json
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2
from porepair.app import App

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out_wizard_test")
os.makedirs(OUT, exist_ok=True)

root = tk.Tk()
root.withdraw()
app = App(root)
print("step after init:", app.step)

# ---- Step 1: load images through the REAL open_oct/open_imm (mock the file dialog) ----
import tkinter.filedialog as fd
OCTP = os.path.join(ROOT, "images", "2lindex_.jpg")
IMMP = os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG")
fd.askopenfilename = lambda **kw: OCTP
app.open_oct()
fd.askopenfilename = lambda **kw: IMMP
app.open_imm()
print("step1 next button state:", app.b1_next["state"])
assert app.b1_next["state"] == "normal"
assert app.p1_oct.img is not None and app.p1_imm.img is not None

app.goto_step(2)
print("step after goto(2):", app.step)
# the step-2 pick panels must actually show the images (regression guard)
print("p2_oct has image:", app.p2_oct.img is not None, "· p2_imm has image:", app.p2_imm.img is not None)
assert app.p2_oct.img is not None and app.p2_imm.img is not None, "step-2 pick panels are empty!"

# ---- Step 2: click landmark pairs from work/points.json ----
pairs = json.load(open(os.path.join(ROOT, "work", "points.json")))["pairs"]
for p in pairs:
    ox, oy = p["o"]; ix, iy = p["i"]
    app.on_click("o", ox, oy)
    app.on_click("i", ix, iy)
print("pairs collected:", len(app.pairs))
assert len(app.pairs) == len(pairs)
print("compute-overlay button state:", app.b2_compute["state"])
assert app.b2_compute["state"] == "normal"

app.compute_overlay()
print("transform fitted:", app.transform is not None)
print("aoi_mask sum:", int(app.aoi_mask.sum()) if app.aoi_mask is not None else None)
assert app.transform is not None and app.aoi_mask is not None and app.aoi_mask.sum() > 0
print("stats label:", app.l2_stats["text"][:120])

app.goto_step(3)
print("step after goto(3):", app.step)
print("det_o:", None if app.det_o is None else len(app.det_o["points"]))
print("det_i (primary):", None if app.det_i is None else len(app.det_i["points"]))
assert app.det_o is not None and app.det_i is not None and len(app.det_i["points"]) > 0
print("p3_oct has image:", app.p3_oct.img is not None, "· p3_imm has image:", app.p3_imm.img is not None)
assert app.p3_oct.img is not None and app.p3_imm.img is not None, "step-3 panels are empty!"
# navigating back to step 2 and forward must keep everything intact
app.goto_step(2)
assert app.p2_oct.img is not None and app.p2_imm.img is not None
app.goto_step(3)
assert app.det_i is not None and app.p3_imm.img is not None
print("round-trip step2<->step3 OK")

# ---- redetect with tuned params ----
app.imm_circ.set("0.2")
app.redetect_imm()
print("after redetect, det_i:", len(app.det_i["points"]))

# ---- manual rectangle restriction on top of AOI ----
h, w = app.imm_bgr.shape[:2]
ys, xs = (app.aoi_mask > 0).nonzero()
app._rect = [float(xs.min()), float(ys.min()), float(xs.min() + (xs.max()-xs.min())//2), float(ys.max())]
app.finish_region_rect()
print("with manual rect, det_i:", len(app.det_i["points"]), "manual_mask set:", app.manual_mask is not None)
app.clear_manual_mask()
print("after clear, manual_mask:", app.manual_mask)

# ---- run_analysis, but bypass askdirectory ----
import tkinter.filedialog as fd
fd.askdirectory = lambda **kw: OUT
import tkinter.messagebox as mb
mb.showinfo = lambda *a, **kw: None
mb.showwarning = lambda *a, **kw: None
mb.showerror = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError(a[1] if len(a) > 1 else "error"))
import os as _os
_os.startfile = lambda *a, **kw: None

app.run_analysis()
print("analysis wrote report:", os.path.exists(os.path.join(OUT, "report.html")))
assert os.path.exists(os.path.join(OUT, "report.html"))
assert os.path.exists(os.path.join(OUT, "results.json"))
print("ALL OK")
