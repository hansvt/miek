"""Build a clean, self-contained HTML report structured by the three objectives:
 1) pore counts in the AOI (whole OCT area, same area in immuno),
 2) pore matching (shared / OCT-only / immuno-only),
 3) inter-pore distance of the matched pores.
Figures are generated with matplotlib and embedded (base64) so the report is one file.
"""
import os
import base64
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OCT_C, IMM_C, SH_C = "#e0218a", "#f0b400", "#1f9d55"   # magenta / amber / green


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _b64_scaled(path, maxdim=1200, quality=82):
    """Downscale (long side <= maxdim) + JPEG-encode before embedding, to keep report.html
    small. Falls back to raw bytes if the image can't be read."""
    import cv2 as _cv2
    im = _cv2.imread(path)
    if im is None:
        return "data:image/png;base64," + _b64(path)
    h, w = im.shape[:2]
    s = maxdim / max(h, w)
    if s < 1.0:
        im = _cv2.resize(im, (int(w * s), int(h * s)), interpolation=_cv2.INTER_AREA)
    ok, buf = _cv2.imencode(".jpg", im, [_cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _fig(path, w=6, h=3.4):
    fig = plt.figure(figsize=(w, h), dpi=130)
    return fig, path


def _finish(fig, path):
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def _fig_counts(out_dir, r):
    fig, path = _fig(os.path.join(out_dir, "fig_counts.png"), 5.2, 3.2)
    ax = fig.add_subplot(111)
    fair = r["counts_fair_region"]
    full = r["counts_full_roi"]
    x = np.arange(2)
    ax.bar(x - 0.2, [full["oct"], fair["oct"]], 0.38, label="OCT", color=OCT_C)
    ax.bar(x + 0.2, [full["imm"], fair["imm"]], 0.38, label="immunolabel", color=IMM_C)
    ax.set_xticks(x); ax.set_xticklabels(["volledige ROI", "eerlijk gebied\n(ROI ∩ afdruk)"])
    ax.set_ylabel("aantal poriën"); ax.legend(frameon=False)
    for i, v in enumerate([full["oct"], fair["oct"]]):
        ax.text(i - 0.2, v + 3, str(v), ha="center", fontsize=9)
    for i, v in enumerate([full["imm"], fair["imm"]]):
        ax.text(i + 0.2, v + 3, str(v), ha="center", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    _finish(fig, path); return path


def _fig_match(out_dir, r):
    fig, path = _fig(os.path.join(out_dir, "fig_match.png"), 5.2, 3.2)
    ax = fig.add_subplot(111)
    m = r["matching_fair_region"]
    vals = [m["shared"], m["oct_only"], m["imm_only"]]
    labels = ["gedeeld", "alleen OCT", "alleen immuno"]
    ax.bar(labels, vals, color=[SH_C, OCT_C, IMM_C])
    for i, v in enumerate(vals):
        ax.text(i, v + max(vals) * 0.02, str(v), ha="center", fontsize=10)
    ax.set_ylabel("aantal poriën"); ax.spines[["top", "right"]].set_visible(False)
    _finish(fig, path); return path


def _fig_ipd(out_dir, r, csv_path):
    """histogram of inter-pore distances of matched pores (from csv we have pair dist;
    for spacing we use the summary stats + reconstruct from results if present)."""
    fig, path = _fig(os.path.join(out_dir, "fig_ipd.png"), 6.2, 3.2)
    ax = fig.add_subplot(111)
    ipd = r["interpore_distance_um"]
    # draw as summary bars with error (median +/- IQR-ish via sd) for the four sets
    sets = [("gematcht OCT", ipd["matched_oct"], SH_C),
            ("gematcht immuno", ipd["matched_imm"], IMM_C),
            ("alle OCT", ipd["all_oct"], OCT_C)]
    names = [s[0] for s in sets if s[1]]
    meds = [s[1]["median"] for s in sets if s[1]]
    sds = [s[1]["sd"] for s in sets if s[1]]
    cols = [s[2] for s in sets if s[1]]
    y = np.arange(len(names))
    ax.barh(y, meds, xerr=sds, color=cols, capsize=4, height=0.6)
    ax.set_yticks(y); ax.set_yticklabels(names)
    ax.set_xlabel("interporie-afstand (µm, mediaan ± sd)")
    for i, v in enumerate(meds):
        ax.text(v + 6, i, f"{v:.0f}", va="center", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    _finish(fig, path); return path


_CSS = """
 body{font-family:'Segoe UI',system-ui,Arial,sans-serif;color:#1a1a1a;max-width:900px;
      margin:24px auto;padding:0 20px;line-height:1.5}
 h1{font-size:24px;margin:0 0 2px} h2{font-size:18px;margin:26px 0 8px;
    border-bottom:2px solid #eee;padding-bottom:4px}
 .sub{color:#666;font-size:13px;margin-bottom:14px}
 .summary{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
 .kpi{flex:1;min-width:150px;background:#f6f8fa;border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px}
 .kpi .n{font-size:22px;font-weight:700} .kpi .l{font-size:12px;color:#555}
 table{border-collapse:collapse;width:100%;margin:8px 0;font-size:14px}
 th,td{border:1px solid #e2e2e2;padding:6px 10px;text-align:center} th{background:#f3f4f6}
 td.l,th.l{text-align:left}
 img{max-width:100%;border:1px solid #ddd;border-radius:6px}
 .fig{margin:10px 0} .cap{font-size:12px;color:#666;margin-top:3px}
 .note{background:#fff7e6;border:1px solid #ffe1a8;border-radius:8px;padding:10px 12px;font-size:13px}
 .cols{display:flex;gap:14px;flex-wrap:wrap} .cols>div{flex:1;min-width:280px}
 footer{color:#888;font-size:12px;margin-top:30px;border-top:1px solid #eee;padding-top:8px}
 @media print{body{margin:0} h2{page-break-after:avoid} .fig,table{page-break-inside:avoid}}
"""


def _match_method_text(r):
    if r.get("match_method") == "matlab":
        return ("Poriën worden gematcht met de <b>MATLAB-methode</b> (OCT_FM): genormaliseerde "
                "<b>positie + oppervlakte</b> gecombineerd, bidirectionele nearest-neighbour met "
                "gecombineerde-afstand drempel.")
    d = r["match_radius_detail"]
    return (f"Poriën worden gematcht met <b>mutual nearest-neighbour</b> (straal "
            f"<b>{r['match_radius_px']} px</b> = {d['base_frac_x_NN']} basis [{d['match_frac']}×NN] "
            f"+ {d['margin_k_x_region']} marge [{d['margin_k']}× regio-straal "
            f"{d['median_region_radius_px']} px], voor immuno's halo-signaal).")


def _imm_detection_section(out_dir, r, img):
    d = r.get("imm_detection") or {}
    if not d.get("params"):
        return ""
    p = d["params"]
    rej = d.get("rejected") or {}
    opt = p.get("optimize", {})
    figs = ""
    for fn, cap in [("imm_optimized.png", "Geoptimaliseerde immuno-image (detectie draait hierop)."),
                    ("imm_rejected.png", "Behouden poriën (groen) vs. verworpen artefacten (rood/oranje).")]:
        fp = os.path.join(out_dir, fn)
        if os.path.exists(fp):
            figs += f'<div>{img(fp, cap)}</div>'
    rej_txt = ", ".join(f"{k}: {v}" for k, v in rej.items()) if rej else "geen"
    return f"""<h2>Immuno-annotatie (artefact-reductie)</h2>
<p>Immuno-poriën gedetecteerd als <b>regio's</b> (centroïde), niet als puntmaxima. Beeld eerst
geoptimaliseerd ({opt.get('method','?')}, bg-sigma {opt.get('bg_sigma','?')}, clip {opt.get('clip_pct','?')})
— detectie draait op dat beeld; CLAHE is alleen voor weergave. Geschatte poriediameter
{p.get('pore_diam_px','?')} px; grootte-band {p.get('min_area','?')}–{p.get('max_area','?')} px²,
circulariteit ≥ {p.get('circularity_thresh','?')}, solidity ≥ {p.get('solidity_thresh','?')},
eccentriciteit ≤ {p.get('max_eccentricity','?')}, samengesmolten blobs → <b>{p.get('merged_blobs','?')}</b>.
Verworpen artefacten: {rej_txt}. Details: <code>imm_rejected.csv</code>.</p>
<div class="cols">{figs}</div>"""


def _wi5_section(out_dir, r, img):
    nm = r.get("numbered_maps") or {}
    matched = nm.get("matched")
    conv = r.get("nn_angle_convention", "")
    fig = ""
    if matched and os.path.exists(os.path.join(out_dir, matched)):
        fig = img(os.path.join(out_dir, matched),
                  "Gematchte poriën genummerd (immuno-frame); grijze lijn = dichtstbijzijnde buur.")
    return f"""<h2>Genummerde poriën-kaarten &amp; nearest-neighbour tabel</h2>
<p>Per porie is een nearest-neighbour tabel opgeslagen met kolommen
<b>Porie_ID, Coordinates, Nearest_neighbour_ID, Distance_neighbour, Angle_neighbour</b>
(afstand in µm, hoek in graden — {conv}). Bestanden: <code>oct_nn.csv</code>,
<code>imm_nn.csv</code>, <code>matched_nn.csv</code>; genummerde kaarten:
<code>oct_pores_numbered.png</code>, <code>imm_pores_numbered.png</code>, <code>matched_numbered.png</code>.</p>
{fig}"""


def _stat(d, unit="µm"):
    if not d:
        return "n.v.t."
    return f"{d['median']:.0f} {unit} (mediaan) · gem {d['mean']:.0f} · sd {d['sd']:.0f} · n={d['n']}"


def build(out_dir, r, date_str=""):
    csv_path = os.path.join(out_dir, "matched_pairs.csv")
    f_counts = _fig_counts(out_dir, r)
    f_match = _fig_match(out_dir, r)
    f_ipd = _fig_ipd(out_dir, r, csv_path)

    oct_name = os.path.basename(r["images"]["oct"])
    imm_name = os.path.basename(r["images"]["imm"])
    t = r["transform"]
    cf, ff = r["counts_full_roi"], r["counts_fair_region"]
    mf = r["matching_fair_region"]
    ipd = r["interpore_distance_um"]
    cal = r["calibration_um_per_px"]
    sens = r["match_radius_sensitivity"]

    def img(path, cap):
        return f'<div class="fig"><img src="{_b64_scaled(path)}"><div class="cap">{cap}</div></div>'

    sens_rows = "".join(
        f"<tr><td>{k}</td><td>{v['shared']}</td><td>{v['oct_only']}</td><td>{v['imm_only']}</td></tr>"
        for k, v in sens.items())

    html = f"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<title>Poriën-analyse rapport</title><style>{_CSS}</style></head><body>
<h1>Poriën-analyse — OCT ↔ immunolabel</h1>
<div class="sub">OCT: <b>{oct_name}</b> &nbsp;·&nbsp; immunolabel: <b>{imm_name}</b> &nbsp;·&nbsp; {date_str}</div>

<div class="summary">
  <div class="kpi"><div class="n">{ff['oct']} / {ff['imm']}</div><div class="l">poriën in AOI (OCT / immuno, eerlijk gebied)</div></div>
  <div class="kpi"><div class="n">{mf['shared']}</div><div class="l">gedeelde (gematchte) poriën</div></div>
  <div class="kpi"><div class="n">{ipd['matched_oct']['median']:.0f} µm</div><div class="l">interporie-afstand gematchte poriën</div></div>
  <div class="kpi"><div class="n">{t['residual_mean_px']:.1f} px</div><div class="l">registratie-residu (gem.)</div></div>
</div>

<h2>Registratie</h2>
<div class="cols">
 <div>{img(os.path.join(out_dir,'overlay.png'), 'OCT (magenta) over immunolabel (groen). Gele/cyaan stippen = ankerpunten.')}</div>
 <div>
  <table>
   <tr><th class="l">Transform</th><td>{t['kind']}{' + poriën-verfijning' if t.get('refined_with_pores') else ''}</td></tr>
   <tr><td class="l">Residu ankerpunten</td><td>{t['residual_mean_px']:.1f} px gem. (max {t['residual_max_px']:.1f})</td></tr>
   {(f"<tr><td class='l'>Residu vóór→na verfijning</td><td>{t['residual_landmarks_only_px']:.1f} → {t['residual_after_refine_px']:.1f} px ({t['n_pore_pairs_used']} poriën-paren)</td></tr>") if t.get('refined_with_pores') else ""}
   <tr><td class="l">Schaal</td><td>{t['scale']:.3f} (OCT→immuno)</td></tr>
   <tr><td class="l">Rotatie</td><td>{t['rotation_deg']:.1f}°</td></tr>
   <tr><td class="l">As-hoek (90°=geen shear)</td><td>{t['axis_angle_deg']:.1f}°</td></tr>
   <tr><td class="l">Aantal ankerpunten</td><td>{t['n_points']}</td></tr>
   <tr><td class="l">Kalibratie</td><td>{cal['x']:.2f} × {cal['y']:.2f} µm/px (OCT {cal['oct_mm'][0]:.0f}×{cal['oct_mm'][1]:.0f} mm)</td></tr>
  </table>
  <div class="note">De registratie steunt op handmatige ankerpunten. Het <b>residu</b> is de
   kwaliteitsmaat; {t['residual_mean_px']:.0f} px ≈ {t['residual_mean_px']*cal['x']:.0f} µm.</div>
 </div>
</div>

<h2>1 · Poriëntelling in de area of interest</h2>
<p>De AOI is de <b>volledige OCT-beeldarea</b> ({r['roi_mm2']:.1f} mm²); via de registratie wordt
<b>dezelfde area</b> in het immunolabel-beeld aangehouden. {r['roi_covered_by_print_pct']}% van de
AOI valt binnen de gelabelde afdruk (het "eerlijke gebied", waar beide modaliteiten signaal hebben).</p>
<div class="cols">
 <div>
  <table>
   <tr><th class="l">Gebied</th><th>OCT</th><th>immunolabel</th></tr>
   <tr><td class="l">volledige AOI</td><td>{cf['oct']}</td><td>{cf['imm']}</td></tr>
   <tr><td class="l">eerlijk gebied (AOI ∩ afdruk)</td><td>{ff['oct']}</td><td>{ff['imm']}</td></tr>
   <tr><td class="l">dichtheid (/mm²)</td><td>{r['density_per_mm2']['oct']}</td><td>{r['density_per_mm2']['imm']}</td></tr>
  </table>
 </div>
 <div>{img(f_counts, 'Poriëntelling per modaliteit.')}</div>
</div>
{('<div class="cols"><div>' + img(os.path.join(out_dir,'overlay.png'), 'Volledige ROI (OCT-area).') + '</div><div>' + img(os.path.join(out_dir,'overlay_aoi.png'), 'Alleen de AOI (ROI ∩ immuno-afdruk); buiten de AOI gedimd.') + '</div></div>') if os.path.exists(os.path.join(out_dir,'overlay_aoi.png')) else ''}

<h2>2 · Matching van poriën</h2>
<p>{_match_method_text(r)}
Klassen: <b>gedeeld</b> (zelfde positie in beide), <b>alleen OCT</b>, <b>alleen immunolabel</b>.
Cijfers voor het eerlijke gebied.</p>
<div class="cols">
 <div>{img(os.path.join(out_dir,'analysis.png'), 'Ruimtelijke matching-kaart: groen=gedeeld, magenta=alleen-OCT, geel=alleen-immuno. Oranje=AOI, blauw=eerlijk gebied.')}</div>
 <div>
  {img(f_match, 'Verdeling gedeeld / alleen-OCT / alleen-immuno.')}
  <table>
   <tr><th class="l">{'Drempel' if r.get('match_method')=='matlab' else 'Match-straal'}</th><th>gedeeld</th><th>alleen OCT</th><th>alleen immuno</th></tr>
   {sens_rows}
  </table>
  <div class="cap">Gevoeligheid ({'gecombineerde-afstand drempel' if r.get('match_method')=='matlab' else '× mediane poriën-afstand'}).</div>
  <p style="font-size:13px">Positie-overeenkomst van gematchte paren: <b>{_stat(r['matched_pair_agreement_um'])}</b>.</p>
 </div>
</div>

<h2>3 · Interporie-afstand van gematchte poriën</h2>
<p>Nearest-neighbour afstand tussen poriën (in µm, via de OCT-kalibratie), berekend over de
<b>gematchte</b> poriën — de kern van doelstelling 3.</p>
<div class="cols">
 <div>
  <table>
   <tr><th class="l">Set</th><th>mediaan</th><th>gem.</th><th>sd</th><th>n</th></tr>
   <tr><td class="l">gematchte poriën — OCT</td><td>{ipd['matched_oct']['median']:.0f}</td><td>{ipd['matched_oct']['mean']:.0f}</td><td>{ipd['matched_oct']['sd']:.0f}</td><td>{ipd['matched_oct']['n']}</td></tr>
   <tr><td class="l">gematchte poriën — immuno</td><td>{ipd['matched_imm']['median']:.0f}</td><td>{ipd['matched_imm']['mean']:.0f}</td><td>{ipd['matched_imm']['sd']:.0f}</td><td>{ipd['matched_imm']['n']}</td></tr>
   <tr><td class="l">alle AOI-poriën — OCT (context)</td><td>{ipd['all_oct']['median']:.0f}</td><td>{ipd['all_oct']['mean']:.0f}</td><td>{ipd['all_oct']['sd']:.0f}</td><td>{ipd['all_oct']['n']}</td></tr>
   <tr><td class="l">alle AOI-poriën — immuno (context)</td><td>{ipd['all_imm']['median']:.0f}</td><td>{ipd['all_imm']['mean']:.0f}</td><td>{ipd['all_imm']['sd']:.0f}</td><td>{ipd['all_imm']['n']}</td></tr>
  </table>
  <div class="cap">Waarden in µm.</div>
 </div>
 <div>{img(f_ipd, 'Interporie-afstand (mediaan ± sd).')}</div>
</div>

{_wi5_section(out_dir, r, img)}

{_imm_detection_section(out_dir, r, img)}

<h2>Methode &amp; kanttekeningen</h2>
<ul style="font-size:13px">
 <li>Detectie: white-tophat + lokale maxima (OCT grijswaarden; immuno rood kanaal, afdruk-mask).</li>
 <li>Registratie: {t['n_points']} handmatige ankerpunten → {t['kind']} transform (OCT→immuno).</li>
 <li>Fysieke maten uit de OCT-kalibratie ({cal['oct_mm'][0]:.0f}×{cal['oct_mm'][1]:.0f} mm).</li>
 <li>Het OCT/immuno-telverschil is deels detectiegevoeligheid (immuno-signaal is dimmer/onvollediger);
     de immuno-telling is een <b>ondergrens</b>. "Alleen-immuno" kan echte poriën óf labelruis zijn.</li>
 <li>De interporie-afstand van gematchte poriën ligt hoger dan die van álle poriën omdat de gematchte
     set dunner is; beide zijn opgenomen.</li>
</ul>

<footer>Gegenereerd door porepair · bestanden: report.html · RESULTS.md · results.json · matched_pairs.csv · overlay.png · analysis.png</footer>
</body></html>"""
    path = os.path.join(out_dir, "report.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path
