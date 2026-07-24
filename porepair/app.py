"""Desktop GUI (Tkinter) for the full porepair flow:
  open OCT + immuno images -> auto-detect pores -> click corresponding points
  (pan/zoom/rotate) -> run registration + analysis -> save overlay & results.

Run:  python -m porepair.app     (or:  python -m porepair gui)
Needs only the standard library's tkinter plus opencv/numpy/scipy/scikit-image.
"""
import os
import json
import base64
import numpy as np
import cv2
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import detect as D
from . import analyze as A

CW, CH = 620, 700          # canvas size per panel


def _png_photo(bgr):
    ok, buf = cv2.imencode(".png", bgr)
    return tk.PhotoImage(data=base64.b64encode(buf.tobytes()).decode("ascii"))


class Panel:
    """One image with its own pan/zoom/rotate view on a Tk canvas."""

    def __init__(self, parent, title, side, app):
        self.app = app
        self.side = side
        self.frame = tk.Frame(parent, bg="#1b1b1b")
        bar = tk.Frame(self.frame, bg="#1b1b1b")
        bar.pack(fill="x")
        tk.Label(bar, text=title, fg="#eee", bg="#1b1b1b", font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)
        tk.Button(bar, text="+", command=lambda: self.zoom_center(1.25)).pack(side="left")
        tk.Button(bar, text="-", command=lambda: self.zoom_center(0.8)).pack(side="left")
        tk.Button(bar, text="passend", command=self.fit).pack(side="left", padx=2)
        tk.Button(bar, text="⟲90", command=lambda: self.rotate_center(-90)).pack(side="left")
        tk.Button(bar, text="⟳90", command=lambda: self.rotate_center(90)).pack(side="left")
        self.rot_var = tk.DoubleVar(value=0)
        tk.Scale(bar, from_=-180, to=180, orient="horizontal", variable=self.rot_var,
                 length=150, command=self._on_slider, bg="#1b1b1b", fg="#9cf",
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
        self._down = (ev.x, ev.y)
        self._moved = False

    def _motion(self, ev):
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
        was_click = self._down is not None and not self._moved
        self._down = None
        if was_click and self.img is not None:
            ix, iy = self.canvas_to_img(ev.x, ev.y)
            h, w = self.img.shape[:2]
            if 0 <= ix <= w and 0 <= iy <= h:
                self.app.on_click(self.side, ix, iy)

    # ---- draw ----
    def render(self):
        if self.img is None:
            return
        view = cv2.warpAffine(self.img, self._M(), (CW, CH))
        self._photo = _png_photo(view)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.app.draw_markers(self)


class App:
    def __init__(self, root):
        self.root = root
        root.title("porepair — poriën-analyse OCT ↔ immunolabel")
        root.configure(bg="#111")

        top = tk.Frame(root, bg="#111")
        top.pack(fill="x", padx=6, pady=4)
        tk.Button(top, text="1. Open OCT…", command=self.open_oct).pack(side="left")
        tk.Button(top, text="2. Open immunolabel…", command=self.open_imm).pack(side="left", padx=4)
        tk.Label(top, text="OCT-grootte (mm):", fg="#ccc", bg="#111").pack(side="left", padx=(12, 2))
        self.mm_var = tk.StringVar(value="10x10")
        tk.Entry(top, textvariable=self.mm_var, width=7).pack(side="left")
        tk.Label(top, text="transform:", fg="#ccc", bg="#111").pack(side="left", padx=(10, 2))
        self.tf_var = tk.StringVar(value="affine")
        ttk.Combobox(top, textvariable=self.tf_var, values=["affine", "similarity", "tps"],
                     width=10, state="readonly").pack(side="left")
        tk.Label(top, text="match k:", fg="#ccc", bg="#111").pack(side="left", padx=(10, 2))
        self.margin_k = tk.StringVar(value="0.5")
        tk.Entry(top, textvariable=self.margin_k, width=4).pack(side="left")
        self.refine_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="poriën-verfijning", variable=self.refine_var, fg="#ccc",
                       bg="#111", selectcolor="#333", activebackground="#111",
                       activeforeground="#fff").pack(side="left", padx=8)
        tk.Button(top, text="3. Analyse + opslaan", command=self.run_analysis,
                  bg="#0a3d62", fg="white").pack(side="left", padx=12)

        # immuno detection controls (tunable per image — defaults are only a starting point)
        dc = tk.Frame(root, bg="#111"); dc.pack(fill="x", padx=6, pady=2)
        tk.Label(dc, text="Immuno-detectie:", fg="#ccc", bg="#111").pack(side="left")
        self.imm_method = tk.StringVar(value="region")
        ttk.Combobox(dc, textvariable=self.imm_method, values=["region", "tophat"], width=8,
                     state="readonly").pack(side="left", padx=2)
        self.imm_circ = tk.StringVar(value="0.40")
        self.imm_minarea = tk.StringVar(value="15")
        self.imm_tophat = tk.StringVar(value="11")
        for lbl, var, w in [("circ", self.imm_circ, 5), ("min-area", self.imm_minarea, 5),
                            ("tophat R", self.imm_tophat, 4)]:
            tk.Label(dc, text=lbl, fg="#ccc", bg="#111").pack(side="left", padx=(8, 1))
            tk.Entry(dc, textvariable=var, width=w).pack(side="left")
        tk.Button(dc, text="↻ her-detecteer immuno", command=self.redetect_imm).pack(side="left", padx=10)
        self.det_info = tk.Label(dc, text="", fg="#9cf", bg="#111")
        self.det_info.pack(side="left")

        self.status = tk.Label(root, text="Open eerst de OCT- en immunolabel-beelden.",
                               fg="#9cf", bg="#111", anchor="w", font=("Segoe UI", 10))
        self.status.pack(fill="x", padx=8)

        mid = tk.Frame(root, bg="#111")
        mid.pack(fill="both", expand=True, padx=6, pady=4)
        self.pO = Panel(mid, "OCT (witte puntjes)", "o", self)
        self.pI = Panel(mid, "immunolabel (rode kralen)", "i", self)
        self.pO.frame.pack(side="left", padx=4)
        self.pI.frame.pack(side="left", padx=4)

        bottom = tk.Frame(root, bg="#111")
        bottom.pack(fill="x", padx=8, pady=4)
        tk.Button(bottom, text="↶ punt terug", command=self.undo).pack(side="left")
        tk.Button(bottom, text="wis punten", command=self.clear).pack(side="left", padx=4)
        self.info = tk.Label(bottom, text="0 puntenparen", fg="#ccc", bg="#111")
        self.info.pack(side="left", padx=12)

        self.oct_path = self.imm_path = None
        self.oct_bgr = self.imm_bgr = None
        self.det_o = self.det_i = None
        self.det_i_reg = self.det_i_top = None
        self.imm_primary = "region"
        self.pairs = []          # list of {"o":[x,y], "i":[x,y]}
        self.pending = None
        self.expect = "o"

    # ---------- image loading + detection ----------
    def open_oct(self):
        p = filedialog.askopenfilename(title="Kies OCT-beeld",
                                       filetypes=[("Beelden", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"), ("Alle", "*.*")])
        if not p:
            return
        self.oct_path = p
        self.oct_bgr = cv2.imread(p)
        self.status.config(text="OCT geladen — poriën detecteren…")
        self.root.update()
        self.det_o = D.detect(self.oct_bgr, mode="oct")
        self.pO.set_image(self._display(self.det_o))
        self._status()

    def open_imm(self):
        p = filedialog.askopenfilename(title="Kies immunolabel-beeld",
                                       filetypes=[("Beelden", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"), ("Alle", "*.*")])
        if not p:
            return
        self.imm_path = p
        self.imm_bgr = cv2.imread(p)
        self._detect_imm(reset_view=True)

    def _imm_params(self):
        try:
            return float(self.imm_circ.get()), int(self.imm_minarea.get()), int(self.imm_tophat.get())
        except ValueError:
            messagebox.showerror("porepair", "circ / min-area / tophat R moeten getallen zijn.")
            return None

    def _detect_imm(self, reset_view=False):
        if self.imm_bgr is None:
            return
        pr = self._imm_params()
        if pr is None:
            return
        circ, ma, thr = pr
        self.status.config(text="immuno detecteren (region + top-hat)…"); self.root.update()
        self.det_i_top = D.detect(self.imm_bgr, mode="imm", tophat=thr)
        self.det_i_reg = D.detect_regions_imm(self.imm_bgr, tophat_radius=thr,
                                              min_area=ma, circularity_thresh=circ)
        self.imm_primary = self.imm_method.get()
        self.det_i = self.det_i_reg if self.imm_primary == "region" else self.det_i_top
        disp = self._display(self.det_i)
        self.pI.set_image(disp) if reset_view else self.pI.update_image(disp)
        self.det_info.config(text=f"region {len(self.det_i_reg['points'])} · "
                                  f"top-hat {len(self.det_i_top['points'])} · primair: {self.imm_primary}")
        self._status()

    def redetect_imm(self):
        self._detect_imm(reset_view=False)

    def _display(self, det):
        vis = cv2.cvtColor(D.enhance(det["gray"]), cv2.COLOR_GRAY2BGR)
        for (y, x) in det["points"]:
            cv2.circle(vis, (int(x), int(y)), 3, (0, 220, 255), 1, cv2.LINE_AA)
        return vis

    # ---------- point picking ----------
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
        self._status()
        self.pO.render()
        self.pI.render()

    def undo(self):
        if self.pending:
            self.pending = None
            self.expect = "o"
        elif self.pairs:
            self.pairs.pop()
        self._status(); self.pO.render(); self.pI.render()

    def clear(self):
        self.pairs.clear(); self.pending = None; self.expect = "o"
        self._status(); self.pO.render(); self.pI.render()

    def draw_markers(self, panel):
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

    def _status(self):
        self.info.config(text=f"{len(self.pairs)} puntenparen")
        if self.oct_bgr is None or self.imm_bgr is None:
            return
        no = len(self.det_o["points"]) if self.det_o else 0
        ni = len(self.det_i["points"]) if self.det_i else 0
        nxt = "OCT (links)" if self.expect == "o" else "HETZELFDE punt in immuno (rechts)"
        self.status.config(text=f"OCT {no} poriën · immuno {ni} poriën · {len(self.pairs)} paren · "
                                f"klik nu punt #{len(self.pairs)+1} in {nxt}")

    # ---------- analysis ----------
    def run_analysis(self):
        if self.oct_bgr is None or self.imm_bgr is None:
            messagebox.showwarning("porepair", "Open eerst beide beelden."); return
        if len(self.pairs) < 3:
            messagebox.showwarning("porepair", "Kies minstens 3 puntenparen (4–8 aanbevolen)."); return
        try:
            a, b = self.mm_var.get().lower().split("x"); oct_mm = (float(a), float(b))
        except Exception:
            messagebox.showerror("porepair", "OCT-grootte moet zijn als '10x10'."); return
        out = filedialog.askdirectory(title="Kies map om resultaten op te slaan")
        if not out:
            return
        os.makedirs(out, exist_ok=True)
        # save detection artefacts + meta + points.json, then reuse analyze.run
        reg, top = self.det_i_reg, self.det_i_top
        primary = reg if self.imm_primary == "region" else top
        np.save(os.path.join(out, "oct_pts.npy"), self.det_o["points"])
        np.save(os.path.join(out, "imm_pts.npy"), primary["points"])
        np.save(os.path.join(out, "imm_pts_region.npy"), reg["points"])
        np.save(os.path.join(out, "imm_pts_tophat.npy"), top["points"])
        np.save(os.path.join(out, "imm_equiv_radius.npy"), reg["equiv_radius"])
        np.save(os.path.join(out, "oct_valid.npy"), self.det_o["valid"])
        np.save(os.path.join(out, "imm_valid.npy"), primary["valid"])
        cv2.imwrite(os.path.join(out, "oct_pores.png"), D.draw(self.det_o["gray"], self.det_o["points"]))
        cv2.imwrite(os.path.join(out, "imm_pores.png"), D.draw(top["gray"], top["points"], (0, 255, 0)))
        cv2.imwrite(os.path.join(out, "imm_pores_regions.png"), D.draw_regions(reg["gray"], reg))
        json.dump({"oct": os.path.abspath(self.oct_path), "imm": os.path.abspath(self.imm_path),
                   "imm_detect": self.imm_primary, "imm_circularity": float(self.imm_circ.get()),
                   "imm_min_area": int(self.imm_minarea.get()), "imm_tophat": int(self.imm_tophat.get()),
                   "imm_region_n": len(reg["points"]), "imm_tophat_n": len(top["points"])},
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
            res = A.run(out, pts_path, oct_mm=oct_mm, transform_kind=self.tf_var.get(),
                        match_margin_k=k, refine_with_pores=self.refine_var.get())
        except Exception as e:
            messagebox.showerror("porepair", f"Analyse mislukt:\n{e}"); raise
        t = res["transform"]; fm = res["matching_fair_region"]; mo = res["interpore_distance_um"]["matched_oct"]
        msg = (f"Opgeslagen in:\n{out}\n\n"
               f"Transform {t['kind']}: residu {t['residual_mean_px']:.1f} px (schaal {t['scale']:.2f}, "
               f"rot {t['rotation_deg']:.0f}°)\n"
               f"1. Telling AOI (eerlijk gebied): OCT {fm and res['counts_fair_region']['oct']} · "
               f"immuno {res['counts_fair_region']['imm']}\n"
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
    root = tk.Tk()
    try:
        root.state("zoomed")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
