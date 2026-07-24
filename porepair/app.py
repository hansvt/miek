"""Desktop GUI (Tkinter) for the porepair flow, as a 3-step wizard:

  Stap 1: beelden selecteren (geen poriën-detectie)
  Stap 2: overlay maken — ankerpunten klikken -> transform + AOI (het overeenkomende gebied)
  Stap 3: in dat gebied enhancen (MATLAB wit/zwart-balans) en poriën berekenen -> analyseren

Run:  python -m porepair.app     (or:  python -m porepair gui)
Needs only the standard library's tkinter plus opencv/numpy/scipy/scikit-image.
"""
import os
import json
import base64
import csv
import numpy as np
import cv2
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import detect as D
from . import analyze as A
from .transform import Transform

CW, CH = 620, 660          # canvas size per panel


def _png_photo(bgr):
    ok, buf = cv2.imencode(".png", bgr)
    return tk.PhotoImage(data=base64.b64encode(buf.tobytes()).decode("ascii"))


class Panel:
    """One image with its own pan/zoom/rotate view on a Tk canvas.

    `mode` controls click behaviour: 'view' (pan/zoom only), 'pick' (click places a
    landmark point, step 2), 'region' (click/drag draws a rectangle or polygon ROI, step 3).
    """

    def __init__(self, parent, title, side, app):
        self.app = app
        self.side = side
        self.mode = "view"
        self.frame = tk.Frame(parent, bg="#1b1b1b")
        bar = tk.Frame(self.frame, bg="#1b1b1b")
        bar.pack(fill="x")
        self.title_lbl = tk.Label(bar, text=title, fg="#eee", bg="#1b1b1b", font=("Segoe UI", 10, "bold"))
        self.title_lbl.pack(side="left", padx=4)
        tk.Button(bar, text="+", command=lambda: self.zoom_center(1.25)).pack(side="left")
        tk.Button(bar, text="-", command=lambda: self.zoom_center(0.8)).pack(side="left")
        tk.Button(bar, text="passend", command=self.fit).pack(side="left", padx=2)
        tk.Button(bar, text="⟲90", command=lambda: self.rotate_center(-90)).pack(side="left")
        tk.Button(bar, text="⟳90", command=lambda: self.rotate_center(90)).pack(side="left")
        self.rot_var = tk.DoubleVar(value=0)
        tk.Scale(bar, from_=-180, to=180, orient="horizontal", variable=self.rot_var,
                 length=130, command=self._on_slider, bg="#1b1b1b", fg="#9cf",
                 highlightthickness=0, showvalue=True).pack(side="left", padx=4)
        self.canvas = tk.Canvas(self.frame, width=CW, height=CH, bg="black", highlightthickness=0)
        self.canvas.pack()

        self.img = None            # display base (BGR)
        self.z = 1.0
        self.a = 0.0               # degrees
        self.tx = self.ty = 0.0
        self._photo = None
        self._down = None
        self._moved = False

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<MouseWheel>", self._wheel)

    def set_title(self, text):
        self.title_lbl.config(text=text)

    # ---- geometry ----
    def _M(self):
        r = np.deg2rad(self.a)
        c, s = self.z * np.cos(r), self.z * np.sin(r)
        return np.array([[c, -s, self.tx], [s, c, self.ty]], float)

    def img_to_canvas(self, pt):
        M = self._M()
        return M @ np.array([pt[0], pt[1], 1.0])

    def canvas_to_img(self, cx, cy):
        Minv = cv2.invertAffineTransform(self._M())
        return Minv @ np.array([cx, cy, 1.0])

    def set_image(self, bgr):
        self.img = bgr
        self.a = 0.0
        self.rot_var.set(0)
        self.fit()

    def update_image(self, bgr):
        """Replace the displayed image WITHOUT resetting zoom/rotation/pan (for re-detect)."""
        self.img = bgr
        self.render()

    def fit(self):
        if self.img is None:
            return
        h, w = self.img.shape[:2]
        self.z = min(CW / w, CH / h) * 0.96
        self.a = 0.0
        L = self.z * np.eye(2)
        cx, cy = np.array([CW / 2, CH / 2]) - L @ np.array([w / 2, h / 2])
        self.tx, self.ty = cx, cy
        self.render()

    def _apply_pivot(self, new_z, new_a, pivot):
        """keep image-point under `pivot` (canvas coords) fixed after z/a change."""
        p = self.canvas_to_img(*pivot)
        self.z, self.a = new_z, new_a
        r = np.deg2rad(self.a)
        c, s = self.z * np.cos(r), self.z * np.sin(r)
        L = np.array([[c, -s], [s, c]])
        t = np.array(pivot) - L @ p
        self.tx, self.ty = t
        self.render()

    def zoom_center(self, f):
        self._apply_pivot(min(12, max(0.03, self.z * f)), self.a, (CW / 2, CH / 2))

    def _wheel(self, ev):
        f = 1.15 if ev.delta > 0 else 1 / 1.15
        self._apply_pivot(min(12, max(0.03, self.z * f)), self.a, (ev.x, ev.y))

    def rotate_center(self, d):
        self.rot_var.set(((self.a + d + 180) % 360) - 180)
        self._apply_pivot(self.z, self.a + d, (CW / 2, CH / 2))

    def _on_slider(self, _):
        self._apply_pivot(self.z, float(self.rot_var.get()), (CW / 2, CH / 2))

    # ---- mouse ----
    def _press(self, ev):
        if self.mode == "region" and self.app.region_mode == "rect":
            ix, iy = self.canvas_to_img(ev.x, ev.y)
            self.app._rect = [ix, iy, ix, iy]
            self._down = None
            self.render()
            return
        self._down = (ev.x, ev.y)
        self._moved = False

    def _motion(self, ev):
        if self.mode == "region" and self.app.region_mode == "rect" and self.app._rect is not None:
            ix, iy = self.canvas_to_img(ev.x, ev.y)
            self.app._rect[2], self.app._rect[3] = ix, iy
            self.render()
            return
        if not self._down:
            return
        dx, dy = ev.x - self._down[0], ev.y - self._down[1]
        if abs(dx) + abs(dy) > 4:
            self._moved = True
        self.tx += dx
        self.ty += dy
        self._down = (ev.x, ev.y)
        self.render()

    def _release(self, ev):
        if self.mode == "region" and self.app.region_mode == "rect" and self.app._rect is not None:
            self.app.finish_region_rect()
            return
        was_click = self._down is not None and not self._moved
        self._down = None
        if not (was_click and self.img is not None):
            return
        ix, iy = self.canvas_to_img(ev.x, ev.y)
        h, w = self.img.shape[:2]
        if not (0 <= ix <= w and 0 <= iy <= h):
            return
        if self.mode == "pick":
            self.app.on_click(self.side, ix, iy)
        elif self.mode == "region" and self.app.region_mode == "poly":
            self.app._poly.append([ix, iy])
            self.render()

    # ---- draw ----
    def render(self):
        if self.img is None:
            self.canvas.delete("all")
            return
        view = cv2.warpAffine(self.img, self._M(), (CW, CH))
        self._photo = _png_photo(view)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        if self.mode == "pick":
            self.app.draw_landmark_markers(self)
        elif self.mode == "region":
            self.app.draw_region(self)
            self.app.draw_pore_markers(self)
        elif self.side in ("o", "i") and self.app.step == 3:
            self.app.draw_pore_markers(self)


class Stepper:
    """Top step indicator: 1 Beelden -> 2 Overlay -> 3 Poriën."""

    def __init__(self, parent, labels):
        self.frame = tk.Frame(parent, bg="#1b1b1b")
        self.lbls = []
        for i, txt in enumerate(labels, 1):
            l = tk.Label(self.frame, text=f"  {i}. {txt}  ", fg="#888", bg="#1b1b1b",
                        font=("Segoe UI", 11, "bold"))
            l.pack(side="left")
            self.lbls.append(l)
            if i < len(labels):
                tk.Label(self.frame, text="→", fg="#555", bg="#1b1b1b").pack(side="left")

    def set_active(self, n):
        for i, l in enumerate(self.lbls, 1):
            if i == n:
                l.config(fg="#fff", bg="#0a3d62")
            elif i < n:
                l.config(fg="#7c7", bg="#1b1b1b")
            else:
                l.config(fg="#888", bg="#1b1b1b")


class App:
    def __init__(self, root):
        self.root = root
        root.title("porepair — poriën-analyse OCT ↔ immunolabel")
        root.configure(bg="#111")

        # ---- state ----
        self.oct_path = self.imm_path = None
        self.oct_bgr = self.imm_bgr = None
        self.oct_disp = self.imm_disp = None      # enhanced BGR for display in every step
        self.step = 1

        self.pairs = []              # landmark pairs [{"o":[x,y], "i":[x,y]}, ...]
        self.pending = None
        self.expect = "o"

        self.transform = None        # Transform, fitted in step 2
        self.oct_valid = None        # OCT valid-tissue mask (oct frame)
        self.imm_print = None        # immuno print-body mask (imm frame)
        self.roi_mask = None         # full mapped ROI (imm frame) — objective 1's full ROI
        self.aoi_mask = None         # roi ∩ imm_print — the corresponding/"eerlijk" area

        self.manual_mask = None      # optional extra manual restriction within the AOI
        self.region_mode = None      # None | 'rect' | 'poly' (step-3 immuno panel drawing)
        self._rect = None
        self._poly = []

        self.det_o = None
        self.det_i_reg = self.det_i_top = self.det_i = None
        self.imm_primary = "region"

        # ---- chrome ----
        self.stepper = Stepper(root, ["Beelden", "Overlay", "Poriën"])
        self.stepper.frame.pack(fill="x", padx=6, pady=(6, 2))
        self.status = tk.Label(root, text="", fg="#9cf", bg="#111", anchor="w", font=("Segoe UI", 10))
        self.status.pack(fill="x", padx=8)

        self.container = tk.Frame(root, bg="#111")
        self.container.pack(fill="both", expand=True)

        self._build_step1()
        self._build_step2()
        self._build_step3()
        self.goto_step(1)

    # =================================================================== STEP 1
    def _build_step1(self):
        f = tk.Frame(self.container, bg="#111")
        self.f1 = f
        bar = tk.Frame(f, bg="#111"); bar.pack(side="top", fill="x", padx=6, pady=4)
        tk.Button(bar, text="Open OCT…", command=self.open_oct).pack(side="left")
        self.l1_oct = tk.Label(bar, text="(geen bestand)", fg="#ccc", bg="#111"); self.l1_oct.pack(side="left", padx=(6, 20))
        tk.Button(bar, text="Open immunolabel…", command=self.open_imm).pack(side="left")
        self.l1_imm = tk.Label(bar, text="(geen bestand)", fg="#ccc", bg="#111"); self.l1_imm.pack(side="left", padx=6)

        # nav bar anchored at the bottom BEFORE the (expanding) image area, so it can never
        # be pushed off-screen when the canvases are large (e.g. HiDPI displays)
        bot = tk.Frame(f, bg="#111"); bot.pack(side="bottom", fill="x", padx=8, pady=6)
        self.b1_next = tk.Button(bot, text="Volgende: overlay maken →", command=lambda: self.goto_step(2),
                                 bg="#0a3d62", fg="white", state="disabled")
        self.b1_next.pack(side="right")

        mid = tk.Frame(f, bg="#111"); mid.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        self.p1_oct = Panel(mid, "OCT", "o", self)
        self.p1_imm = Panel(mid, "immunolabel", "i", self)
        self.p1_oct.frame.pack(side="left", padx=4)
        self.p1_imm.frame.pack(side="left", padx=4)

    def open_oct(self):
        p = filedialog.askopenfilename(title="Kies OCT-beeld",
                                       filetypes=[("Beelden", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"), ("Alle", "*.*")])
        if not p:
            return
        self.oct_path = p
        self.oct_bgr = cv2.imread(p)
        self.l1_oct.config(text=os.path.basename(p))
        self.oct_disp = cv2.cvtColor(D.enhance(cv2.cvtColor(self.oct_bgr, cv2.COLOR_BGR2GRAY)), cv2.COLOR_GRAY2BGR)
        self.p1_oct.set_image(self.oct_disp)
        self._invalidate_from_images()
        self._check_step1()

    def open_imm(self):
        p = filedialog.askopenfilename(title="Kies immunolabel-beeld",
                                       filetypes=[("Beelden", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"), ("Alle", "*.*")])
        if not p:
            return
        self.imm_path = p
        self.imm_bgr = cv2.imread(p)
        self.l1_imm.config(text=os.path.basename(p))
        self.imm_disp = cv2.cvtColor(D.enhance(self.imm_bgr[:, :, 2]), cv2.COLOR_GRAY2BGR)
        self.p1_imm.set_image(self.imm_disp)
        self._invalidate_from_images()
        self._check_step1()

    def _invalidate_from_images(self):
        """A (re)loaded image invalidates everything downstream: overlay + detections."""
        self.transform = None
        self.roi_mask = self.aoi_mask = None
        self.pairs.clear(); self.pending = None; self.expect = "o"
        self.det_o = self.det_i_reg = self.det_i_top = self.det_i = None

    def _check_step1(self):
        ok = self.oct_bgr is not None and self.imm_bgr is not None
        self.b1_next.config(state="normal" if ok else "disabled")

    # =================================================================== STEP 2
    def _build_step2(self):
        f = tk.Frame(self.container, bg="#111")
        self.f2 = f

        # -- picking sub-view --
        self.f2_pick = tk.Frame(f, bg="#111")
        hint = tk.Label(self.f2_pick,
                        text="Klik een herkenbaar punt in OCT, dan hetzelfde punt in immunolabel. 4-8 paren, goed verspreid.",
                        fg="#bbb", bg="#111", wraplength=1100, justify="left")
        hint.pack(side="top", fill="x", padx=8, pady=(4, 0))

        bot1 = tk.Frame(self.f2_pick, bg="#111"); bot1.pack(side="bottom", fill="x", padx=8, pady=6)
        tk.Button(bot1, text="← Terug naar beelden", command=lambda: self.goto_step(1)).pack(side="left")
        self.b2_compute = tk.Button(bot1, text="Bereken overlay →", command=self.compute_overlay,
                                    bg="#0a3d62", fg="white", state="disabled")
        self.b2_compute.pack(side="right")

        ctr = tk.Frame(self.f2_pick, bg="#111"); ctr.pack(side="bottom", fill="x", padx=8, pady=2)
        tk.Button(ctr, text="↶ punt terug", command=self.undo_pair).pack(side="left")
        tk.Button(ctr, text="wis punten", command=self.clear_pairs).pack(side="left", padx=4)
        self.l2_pairs = tk.Label(ctr, text="0 puntenparen", fg="#ccc", bg="#111"); self.l2_pairs.pack(side="left", padx=12)
        tk.Label(ctr, text="OCT-grootte (mm):", fg="#ccc", bg="#111").pack(side="left", padx=(16, 2))
        self.mm_var = tk.StringVar(value="10x10")
        tk.Entry(ctr, textvariable=self.mm_var, width=7).pack(side="left")
        tk.Label(ctr, text="transform:", fg="#ccc", bg="#111").pack(side="left", padx=(10, 2))
        self.tf_var = tk.StringVar(value="affine")
        ttk.Combobox(ctr, textvariable=self.tf_var, values=["affine", "similarity", "tps"],
                     width=10, state="readonly").pack(side="left")

        mid = tk.Frame(self.f2_pick, bg="#111"); mid.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        self.p2_oct = Panel(mid, "OCT — klik ankerpunten", "o", self)
        self.p2_imm = Panel(mid, "immunolabel — klik hetzelfde punt", "i", self)
        self.p2_oct.mode = self.p2_imm.mode = "pick"
        self.p2_oct.frame.pack(side="left", padx=4)
        self.p2_imm.frame.pack(side="left", padx=4)

        # -- review sub-view --
        self.f2_review = tk.Frame(f, bg="#111")
        bot2 = tk.Frame(self.f2_review, bg="#111"); bot2.pack(side="bottom", fill="x", padx=8, pady=6)
        tk.Button(bot2, text="← Punten aanpassen", command=self._show_step2_pick).pack(side="left")
        tk.Button(bot2, text="Volgende: poriën detecteren →", command=lambda: self.goto_step(3),
                 bg="#0a3d62", fg="white").pack(side="right")
        self.l2_stats = tk.Label(self.f2_review, text="", fg="#ccc", bg="#111", justify="left", anchor="w")
        self.l2_stats.pack(side="bottom", fill="x", padx=10)
        rmid = tk.Frame(self.f2_review, bg="#111"); rmid.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        self.p2_overlay = Panel(rmid, "Overlay (OCT magenta op immuno groen; oranje = overeenkomend gebied)", "o", self)
        self.p2_overlay.frame.pack(padx=4)

        self.f2_pick.pack(fill="both", expand=True)   # default sub-view

    def _show_step2_pick(self):
        self.f2_review.pack_forget()
        self.f2_pick.pack(fill="both", expand=True)
        self._status_step2()

    def _show_step2_review(self):
        self.f2_pick.pack_forget()
        self.f2_review.pack(fill="both", expand=True)

    def on_click(self, side, x, y):
        if side != self.expect:
            self.status.config(text=f"Klik eerst in het {'OCT' if self.expect=='o' else 'immuno'}-beeld.")
            return
        if side == "o":
            self.pending = [round(x, 1), round(y, 1)]
            self.expect = "i"
        else:
            self.pairs.append({"o": self.pending, "i": [round(x, 1), round(y, 1)]})
            self.pending = None
            self.expect = "o"
        self._status_step2()
        self.p2_oct.render(); self.p2_imm.render()
        self.b2_compute.config(state="normal" if len(self.pairs) >= 3 else "disabled")

    def undo_pair(self):
        if self.pending:
            self.pending = None; self.expect = "o"
        elif self.pairs:
            self.pairs.pop()
        self._status_step2(); self.p2_oct.render(); self.p2_imm.render()
        self.b2_compute.config(state="normal" if len(self.pairs) >= 3 else "disabled")

    def clear_pairs(self):
        self.pairs.clear(); self.pending = None; self.expect = "o"
        self._status_step2(); self.p2_oct.render(); self.p2_imm.render()
        self.b2_compute.config(state="disabled")

    def draw_landmark_markers(self, panel):
        for idx, pr in enumerate(self.pairs, 1):
            self._marker(panel, pr[panel.side], idx, "#3cf" if panel.side == "o" else "#f66")
        if panel.side == "o" and self.pending:
            self._marker(panel, self.pending, len(self.pairs) + 1, "#ff0", dash=True)

    def _marker(self, panel, pt, n, color, dash=False):
        cx, cy = panel.img_to_canvas(pt)
        if -20 < cx < CW + 20 and -20 < cy < CH + 20:
            panel.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=color,
                                     width=2, dash=(3, 2) if dash else None)
            panel.canvas.create_text(cx + 12, cy - 8, text=str(n), fill=color, anchor="w")

    def _status_step2(self):
        self.l2_pairs.config(text=f"{len(self.pairs)} puntenparen")
        nxt = "OCT (links)" if self.expect == "o" else "HETZELFDE punt in immuno (rechts)"
        self.status.config(text=f"{len(self.pairs)} paren · klik nu punt #{len(self.pairs)+1} in {nxt}")

    def compute_overlay(self):
        if len(self.pairs) < 3:
            messagebox.showwarning("porepair", "Kies minstens 3 puntenparen (4-8 aanbevolen)."); return
        O_lm = np.array([p["o"] for p in self.pairs], float)
        I_lm = np.array([p["i"] for p in self.pairs], float)
        try:
            T = Transform(self.tf_var.get(), O_lm, I_lm)
        except Exception as e:
            messagebox.showerror("porepair", f"Kon transform niet fitten:\n{e}"); return
        oct_gray = cv2.cvtColor(self.oct_bgr, cv2.COLOR_BGR2GRAY)
        imm_gray = self.imm_bgr[:, :, 2]
        oct_valid = D._valid_oct(oct_gray)
        imm_print = D._valid_print(imm_gray)
        Hh, Ww = imm_gray.shape
        roi, overlap = A.compute_aoi(T, oct_valid, imm_print, Hh, Ww)

        self.transform, self.oct_valid, self.imm_print = T, oct_valid, imm_print
        self.roi_mask, self.aoi_mask = roi, overlap
        # a new overlay invalidates any previously tuned/computed pore detections
        self.det_o = self.det_i_reg = self.det_i_top = self.det_i = None
        self.manual_mask = None; self._rect = None; self._poly = []; self.region_mode = None

        preview = self._build_overlay_preview()
        self.p2_overlay.set_image(preview)
        info = T.describe()
        cov = 100 * overlap.sum() / max(roi.sum(), 1)
        self.l2_stats.config(text=(
            f"Transform {info['kind']}: residu {info['residual_mean_px']:.1f} px gem "
            f"(max {info['residual_max_px']:.1f}), schaal {info['scale']:.3f}, rotatie "
            f"{info['rotation_deg']:.1f}°, {info['n_points']} punten.\n"
            f"Overeenkomend gebied (AOI): {int(overlap.sum())} px² · {cov:.0f}% van het volledig "
            f"gemapte OCT-gebied valt binnen de immuno-afdruk."))
        if info["residual_mean_px"] > 25:
            self.l2_stats.config(fg="#f80")
            messagebox.showwarning("porepair", "Hoog residu — controleer de ankerpunten (meer/beter verspreid).")
        else:
            self.l2_stats.config(fg="#ccc")
        self._show_step2_review()
        self.status.config(text="Overlay berekend — controleer het overeenkomende gebied.")

    def _build_overlay_preview(self):
        T = self.transform
        Hh, Ww = self.imm_bgr.shape[:2]
        M = np.hstack([T.A, T.t.reshape(2, 1)]).astype(np.float32)
        warp = cv2.warpAffine(self.oct_bgr, M, (Ww, Hh))
        wg = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)
        over = self.imm_bgr.copy()
        over[:, :, 1] = np.maximum(over[:, :, 1], self.imm_bgr[:, :, 2])
        over[:, :, 2] = np.maximum(over[:, :, 2], wg)
        over[:, :, 0] = np.maximum(over[:, :, 0], wg)
        for p in self.pairs:
            ox, oy = p["o"]; ix, iy = p["i"]
            px, py = T.apply([[ox, oy]])[0].astype(int)
            cv2.circle(over, (px, py), 9, (255, 255, 0), 2)
            cv2.circle(over, (int(ix), int(iy)), 5, (0, 255, 255), -1)
        cnts, _ = cv2.findContours(self.aoi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(over, cnts, -1, (255, 120, 0), 2)
        ys, xs = np.where(self.aoi_mask > 0)
        if len(xs):
            x0, y0 = max(0, xs.min() - 30), max(0, ys.min() - 30)
            x1, y1 = min(Ww, xs.max() + 30), min(Hh, ys.max() + 30)
            over = over[y0:y1, x0:x1]
        return over

    # =================================================================== STEP 3
    def _build_step3(self):
        f = tk.Frame(self.container, bg="#111")
        self.f3 = f

        dc = tk.Frame(f, bg="#111"); dc.pack(fill="x", padx=6, pady=2)
        tk.Label(dc, text="Immuno-detectie (in het overeenkomende gebied):", fg="#ccc", bg="#111").pack(side="left")
        self.imm_method = tk.StringVar(value="region")
        ttk.Combobox(dc, textvariable=self.imm_method, values=["region", "tophat"], width=8,
                     state="readonly").pack(side="left", padx=2)
        self.imm_circ = tk.StringVar(value="0.15")
        self.imm_minfrac = tk.StringVar(value="0.15")
        self.imm_maxfrac = tk.StringVar(value="6.0")
        for lbl, var, w in [("circ", self.imm_circ, 5), ("min-frac", self.imm_minfrac, 5),
                            ("max-frac", self.imm_maxfrac, 5)]:
            tk.Label(dc, text=lbl, fg="#ccc", bg="#111").pack(side="left", padx=(8, 1))
            tk.Entry(dc, textvariable=var, width=w).pack(side="left")
        self.merged_var = tk.StringVar(value="split")
        tk.Label(dc, text="merged", fg="#ccc", bg="#111").pack(side="left", padx=(8, 1))
        ttk.Combobox(dc, textvariable=self.merged_var, values=["split", "reject"], width=7,
                     state="readonly").pack(side="left")
        tk.Button(dc, text="↻ her-detecteer", command=self.redetect_imm).pack(side="left", padx=10)
        self.det_info = tk.Label(dc, text="", fg="#9cf", bg="#111"); self.det_info.pack(side="left")

        dc2 = tk.Frame(f, bg="#111"); dc2.pack(fill="x", padx=6, pady=2)
        tk.Label(dc2, text="Extra beperking binnen het gebied (optioneel):", fg="#ccc", bg="#111").pack(side="left")
        self.bRect = tk.Button(dc2, text="▭ rechthoek", command=lambda: self.toggle_region("rect")); self.bRect.pack(side="left")
        self.bPoly = tk.Button(dc2, text="⬠ polygoon", command=lambda: self.toggle_region("poly")); self.bPoly.pack(side="left")
        tk.Button(dc2, text="✓ sluit", command=self.finish_poly).pack(side="left")
        tk.Button(dc2, text="✕ wissen", command=self.clear_manual_mask).pack(side="left")

        bot = tk.Frame(f, bg="#111"); bot.pack(side="bottom", fill="x", padx=8, pady=6)
        tk.Button(bot, text="← Terug naar overlay", command=lambda: self.goto_step(2)).pack(side="left")
        tk.Button(bot, text="Analyse + opslaan", command=self.run_analysis,
                 bg="#0a3d62", fg="white").pack(side="right")

        settings = tk.Frame(f, bg="#111"); settings.pack(side="bottom", fill="x", padx=8, pady=2)
        tk.Label(settings, text="match k:", fg="#ccc", bg="#111").pack(side="left")
        self.margin_k = tk.StringVar(value="0.5")
        tk.Entry(settings, textvariable=self.margin_k, width=4).pack(side="left", padx=(2, 10))
        self.refine_var = tk.BooleanVar(value=False)
        tk.Checkbutton(settings, text="poriën-verfijning", variable=self.refine_var, fg="#ccc",
                       bg="#111", selectcolor="#333", activebackground="#111",
                       activeforeground="#fff").pack(side="left", padx=8)
        tk.Label(settings, text="match:", fg="#ccc", bg="#111").pack(side="left", padx=(6, 2))
        self.match_method = tk.StringVar(value="mutual-nn")
        ttk.Combobox(settings, textvariable=self.match_method, values=["mutual-nn", "matlab"],
                     width=10, state="readonly").pack(side="left")

        mid = tk.Frame(f, bg="#111"); mid.pack(side="top", fill="both", expand=True, padx=6, pady=4)
        self.p3_oct = Panel(mid, "OCT — gedetecteerde poriën", "o", self)
        self.p3_imm = Panel(mid, "immunolabel — gedetecteerde poriën", "i", self)
        self.p3_imm.mode = "region"
        self.p3_oct.frame.pack(side="left", padx=4)
        self.p3_imm.frame.pack(side="left", padx=4)

    def _effective_mask(self):
        if self.aoi_mask is None:
            return None
        if self.manual_mask is not None:
            return (self.aoi_mask & self.manual_mask).astype(np.uint8)
        return self.aoi_mask

    def _imm_params(self):
        try:
            return (float(self.imm_circ.get()), float(self.imm_minfrac.get()),
                    float(self.imm_maxfrac.get()))
        except ValueError:
            messagebox.showerror("porepair", "circ / min-frac / max-frac moeten getallen zijn.")
            return None

    def _enter_step3(self):
        if self.transform is None:
            return
        if self.det_o is None:                       # detect OCT pores once (this is step 3)
            self.status.config(text="OCT-poriën detecteren…"); self.root.update()
            self.det_o = D.detect(self.oct_bgr, mode="oct")
            self.p3_oct.set_image(self._display(self.det_o))
        elif self.p3_oct.img is None:
            self.p3_oct.set_image(self._display(self.det_o))
        if self.det_i is None:                       # detect immuno within the AOI
            self._detect_imm(reset_view=True)
        elif self.p3_imm.img is None:
            self.p3_imm.set_image(self._display(self.det_i))

    def _detect_imm(self, reset_view=False):
        if self.imm_bgr is None or self.aoi_mask is None:
            return
        pr = self._imm_params()
        if pr is None:
            return
        circ, minf, maxf = pr
        mask = self._effective_mask()
        self.status.config(text="immuno detecteren in het overeenkomende gebied…"); self.root.update()
        self.det_i_top = D.detect(self.imm_bgr, mode="imm")
        self.det_i_reg = D.detect_regions_imm(
            self.imm_bgr, region_mask=mask, circularity_thresh=circ,
            min_area_frac=minf, max_area_frac=maxf, merged_blobs=self.merged_var.get())
        self.imm_primary = self.imm_method.get()
        self.det_i = self.det_i_reg if self.imm_primary == "region" else self.det_i_top
        disp = self._display(self.det_i)
        self.p3_imm.set_image(disp) if reset_view else self.p3_imm.update_image(disp)
        self.det_info.config(text=f"region {len(self.det_i_reg['points'])} · "
                                  f"top-hat {len(self.det_i_top['points'])} · primair: {self.imm_primary}")
        self.status.config(text=f"OCT {len(self.det_o['points'])} poriën · immuno {len(self.det_i['points'])} "
                                f"poriën in het overeenkomende gebied.")

    def redetect_imm(self):
        self._detect_imm(reset_view=False)

    def _display(self, det):
        vis = cv2.cvtColor(D.enhance(det["gray"]), cv2.COLOR_GRAY2BGR)
        for (y, x) in det["points"]:
            cv2.circle(vis, (int(x), int(y)), 3, (0, 220, 255), 1, cv2.LINE_AA)
        return vis

    def draw_pore_markers(self, panel):
        pass  # markers are already baked into the displayed image via _display()

    # -- optional manual rectangle/polygon, intersected with the auto AOI --
    def toggle_region(self, mode):
        if self.aoi_mask is None:
            return
        self.region_mode = None if self.region_mode == mode else mode
        self._rect = None
        if self.region_mode == "poly":
            self._poly = []
        self.bRect.config(relief="sunken" if self.region_mode == "rect" else "raised")
        self.bPoly.config(relief="sunken" if self.region_mode == "poly" else "raised")
        self.status.config(text={"rect": "Sleep een rechthoek op het immuno-beeld.",
                                 "poly": "Klik polygoon-hoekpunten; daarna ✓ sluit.",
                                 None: ""}[self.region_mode])
        self.p3_imm.render()

    def draw_region(self, panel):
        if self._rect is not None:
            (x0, y0), (x1, y1) = panel.img_to_canvas(self._rect[:2]), panel.img_to_canvas(self._rect[2:])
            panel.canvas.create_rectangle(x0, y0, x1, y1, outline="#0ff", width=2)
        elif self.region_mode == "poly" and self._poly:
            cpts = [panel.img_to_canvas(p) for p in self._poly]
            for (px, py) in cpts:
                panel.canvas.create_oval(px - 3, py - 3, px + 3, py + 3, outline="#0ff", width=2)
            if len(cpts) > 1:
                panel.canvas.create_line(*[c for xy in cpts for c in xy], fill="#0ff", width=2)
        if self.aoi_mask is not None:
            cnts, _ = cv2.findContours(self.aoi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                pcs = [panel.img_to_canvas([int(p[0][0]), int(p[0][1])]) for p in c[::max(1, len(c) // 60)]]
                if len(pcs) > 1:
                    panel.canvas.create_line(*[v for xy in pcs for v in xy], fill="#f80", width=1, dash=(4, 3))

    def finish_region_rect(self):
        r, self._rect = self._rect, None
        if r is None:
            return
        h, w = self.imm_bgr.shape[:2]
        x0, x1 = sorted((int(np.clip(r[0], 0, w)), int(np.clip(r[2], 0, w))))
        y0, y1 = sorted((int(np.clip(r[1], 0, h)), int(np.clip(r[3], 0, h))))
        if x1 - x0 < 5 or y1 - y0 < 5:
            self.p3_imm.render(); return
        mask = np.zeros((h, w), np.uint8); mask[y0:y1, x0:x1] = 1
        self._set_manual_mask(mask)

    def finish_poly(self):
        if len(self._poly) < 3:
            messagebox.showwarning("porepair", "Klik minstens 3 polygoon-hoekpunten."); return
        h, w = self.imm_bgr.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [np.array(self._poly, np.int32)], 1)
        self._poly = []
        self._set_manual_mask(mask)

    def _set_manual_mask(self, mask):
        self.region_mode = None
        self.bRect.config(relief="raised"); self.bPoly.config(relief="raised")
        self.manual_mask = mask
        self._detect_imm(reset_view=False)

    def clear_manual_mask(self):
        self.manual_mask = None
        self._rect = None; self._poly = []; self.region_mode = None
        self.bRect.config(relief="raised"); self.bPoly.config(relief="raised")
        if self.aoi_mask is not None:
            self._detect_imm(reset_view=False)

    # =================================================================== navigation
    def goto_step(self, n):
        for w in (self.f1, self.f2, self.f3):
            w.pack_forget()
        self.step = n
        self.stepper.set_active(n)
        if n == 1:
            self.f1.pack(fill="both", expand=True)
            self.status.config(text="Selecteer de OCT- en immunolabel-beelden.")
        elif n == 2:
            self.f2.pack(fill="both", expand=True)
            if self.oct_disp is not None:          # populate the pick panels (fixes empty step-2)
                self.p2_oct.set_image(self.oct_disp)
            if self.imm_disp is not None:
                self.p2_imm.set_image(self.imm_disp)
            self._show_step2_pick()
        elif n == 3:
            self.f3.pack(fill="both", expand=True)
            self._enter_step3()

    # =================================================================== analysis
    def run_analysis(self):
        if self.det_i is None or self.det_o is None:
            messagebox.showwarning("porepair", "Wacht tot de poriën-detectie klaar is."); return
        try:
            a, b = self.mm_var.get().lower().split("x"); oct_mm = (float(a), float(b))
        except Exception:
            messagebox.showerror("porepair", "OCT-grootte moet zijn als '10x10'."); return
        out = filedialog.askdirectory(title="Kies map om resultaten op te slaan")
        if not out:
            return
        os.makedirs(out, exist_ok=True)
        reg, top = self.det_i_reg, self.det_i_top
        primary = reg if self.imm_primary == "region" else top
        mask = self._effective_mask()
        np.save(os.path.join(out, "oct_pts.npy"), self.det_o["points"])
        np.save(os.path.join(out, "oct_area.npy"), self.det_o.get("area", np.zeros(len(self.det_o["points"]))))
        np.save(os.path.join(out, "imm_pts.npy"), primary["points"])
        np.save(os.path.join(out, "imm_pts_region.npy"), reg["points"])
        np.save(os.path.join(out, "imm_pts_tophat.npy"), top["points"])
        np.save(os.path.join(out, "imm_equiv_radius.npy"), reg["equiv_radius"])
        np.save(os.path.join(out, "oct_valid.npy"), self.det_o["valid"])
        np.save(os.path.join(out, "imm_valid.npy"), primary["valid"])
        cv2.imwrite(os.path.join(out, "oct_pores.png"), D.draw(self.det_o["gray"], self.det_o["points"]))
        cv2.imwrite(os.path.join(out, "imm_pores.png"), D.draw(top["gray"], top["points"], (0, 255, 0)))
        cv2.imwrite(os.path.join(out, "imm_pores_regions.png"), D.draw_regions(reg["gray"], reg, on_optimized=True))
        cv2.imwrite(os.path.join(out, "imm_optimized.png"), reg["optimized"])
        cv2.imwrite(os.path.join(out, "imm_rejected.png"), D.draw_rejections(reg))
        if mask is not None:
            cv2.imwrite(os.path.join(out, "imm_region_mask.png"), mask * 255)
        with open(os.path.join(out, "imm_rejected.csv"), "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["x_px", "y_px", "area_px", "reason"])
            for r in reg["rejections"]:
                w.writerow([f"{r['x']:.1f}", f"{r['y']:.1f}", f"{r['area']:.0f}", r["reason"]])
        reasons = {}
        for r in reg["rejections"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        json.dump({"oct": os.path.abspath(self.oct_path), "imm": os.path.abspath(self.imm_path),
                   "imm_detect": self.imm_primary, "imm_region_n": len(reg["points"]),
                   "imm_tophat_n": len(top["points"]), "imm_rejected": reasons,
                   "imm_region_mask": mask is not None, "imm_params": reg["params"]},
                  open(os.path.join(out, "meta.json"), "w"), indent=2)
        pts_path = os.path.join(out, "points.json")
        json.dump({"oct_image": os.path.basename(self.oct_path),
                   "imm_image": os.path.basename(self.imm_path), "pairs": self.pairs},
                  open(pts_path, "w"), indent=2)
        try:
            k = float(self.margin_k.get())
        except ValueError:
            k = 0.5
        try:
            from . import imm_curator
            imm_curator.build(out, os.path.basename(self.imm_path))
        except Exception:
            pass
        try:
            res = A.run(out, pts_path, oct_mm=oct_mm, transform_kind=self.tf_var.get(),
                        match_margin_k=k, refine_with_pores=self.refine_var.get(),
                        match_method=self.match_method.get())
        except Exception as e:
            messagebox.showerror("porepair", f"Analyse mislukt:\n{e}"); raise
        t = res["transform"]; fm = res["matching_fair_region"]; mo = res["interpore_distance_um"]["matched_oct"]
        msg = (f"Opgeslagen in:\n{out}\n\n"
               f"Transform {t['kind']}: residu {t['residual_mean_px']:.1f} px (schaal {t['scale']:.2f}, "
               f"rot {t['rotation_deg']:.0f}°)\n"
               f"1. Telling AOI: OCT {res['counts_fair_region']['oct']} · immuno {res['counts_fair_region']['imm']}\n"
               f"2. Matching: gedeeld {fm['shared']}, alleen-OCT {fm['oct_only']}, alleen-immuno {fm['imm_only']}\n"
               f"3. Interporie-afstand gematchte poriën (OCT): {mo['median']:.0f} µm (mediaan)\n\n"
               f"Rapport: report.html · interactieve viewer: overlay_viewer.html\n"
               f"(+ overlay_aoi.png, results.xlsx, protocol.docx, *_nn.csv, matched_pairs.csv)")
        if t["residual_mean_px"] > 25:
            msg += "\n\n⚠ Hoog residu — controleer de ankerpunten (meer/beter verspreid)."
        messagebox.showinfo("porepair — klaar", msg)
        rep = res.get("report_html")
        try:
            if rep and os.path.exists(rep):
                os.startfile(rep)     # open het rapport (Windows)
            else:
                os.startfile(out)
        except Exception:
            pass


def main():
    global CW, CH
    root = tk.Tk()
    try:
        root.state("zoomed")
    except Exception:
        pass
    # size the two side-by-side canvases to the actual screen so nothing overflows
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    CH = int(max(320, min(680, sh - 320)))       # leave room for stepper/status/toolbars/nav/taskbar
    CW = int(max(340, min(CH * 0.95, sw / 2 - 60)))
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
