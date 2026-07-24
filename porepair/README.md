# porepair

Registratie en poriën-analyse van een **OCT**- en een **immunolabel**-opname van dezelfde
vingerafdruk. Drie stappen: `detect` → `pick` (handmatig) → `analyze`.

## Installatie
Python 3.10+ met: `opencv-python numpy scipy scikit-image` (tkinter zit in de standaard-Python).
(In dit project: gebruik de venv — `./.venv/Scripts/python.exe`.)

## Desktop-app (aanbevolen)
Alles in één venster: beelden kiezen → poriën worden automatisch gedetecteerd →
punten klikken (slepen=pannen, wiel=zoomen, knoppen/schuif=roteren) → knop
**"Analyse + opslaan"** schrijft overlay + analyse weg.
```bash
python -m porepair.app        # of:  python -m porepair gui
```

## Gebruik (CLI, voor scripting/batch)
```bash
# 1) Poriën detecteren in beide beelden (schrijft ook out/point_picker.html)
python -m porepair detect --oct OCT.jpg --imm IMMUNO.jpg --out out

# 2) Ankerpunten kiezen: open out/point_picker.html (dubbelklik), klik 4-8
#    corresponderende paren, klik "exporteer JSON" -> points.json
#    (slepen=pannen, wiel=zoomen, knoppen/schuif=roteren)

# 3) Registreren + analyseren
python -m porepair analyze --out out --points points.json --oct-mm 10x10
```

## Belangrijkste opties
`detect`: `--imm-channel red|green|blue` · `--oct-tophat 9` · `--imm-tophat 11`
· `--min-dist 14` · `--oct-thr / --imm-thr` (vaste drempel i.p.v. adaptief).
`analyze`: `--oct-mm 10x10` (fysieke OCT-grootte, voor µm) · `--transform affine|similarity|tps`
· `--match-frac 0.45` (matchstraal als fractie van de poriën-afstand).

## Uitvoer (in `--out`)
- **`report.html`** — net, zelfstandig rapport (drie doelstellingen, figuren + tabellen ingebed);
  open in de browser, print naar PDF om vast te leggen.
- **`overlay_viewer.html`** — interactieve viewer: pan/zoom/roteren + cross-fade OCT↔immuno (WI-8).
- **`results.xlsx`** — alle resultaten in sheets (Summary/Transform/Config/Matched_Pairs/OCT_Pores/
  Immuno_Pores/Matched_NN) om figuren later te herbouwen (WI-6).
- **`protocol.docx`** — methoden-sectie voor publicatie, gevuld uit de run (WI-7).
- `overlay.png` / `overlay_aoi.png` — registratie-overlay: volledige ROI en alleen-AOI (WI-3)
- `analysis.png` — matching-kaart (groen=gedeeld, magenta=alleen-OCT, geel=alleen-immuno)
- `oct_pores_numbered.png` / `imm_pores_numbered.png` / `matched_numbered.png` — genummerde kaarten (WI-5)
- `oct_nn.csv` / `imm_nn.csv` / `matched_nn.csv` — nearest-neighbour tabellen (WI-5)
- `fig_counts.png`, `fig_match.png`, `fig_ipd.png` — grafieken (ook in het rapport)
- `matched_pairs.csv`, `results.json`, `RESULTS.md` — data + korte tekstsamenvatting
- `imm_pores_regions.png` / `imm_pores.png` — immuno-detectie: region + top-hat (WI-1)
- `oct_pts.npy`, `imm_pts*.npy`, `*_valid.npy`, `imm_equiv_radius.npy` — detecties/maskers
- `point_picker.html` — de landmark-tool (bij CLI-flow)

Extra CLI: `python -m porepair view --out DIR` (herbouw viewer). Analyze-flags:
`--refine-pores` (WI-2), `--match-margin-k` (WI-4), `--imm-detect`/`--imm-circularity`/`--imm-min-area` (WI-1).

Het rapport is gestructureerd naar de doelstellingen: **1** telling in de AOI (OCT-area, zelfde
area in immuno), **2** matching (gedeeld / alleen-OCT / alleen-immuno), **3** interporie-afstand
van de gematchte poriën.

## Aannames / let op
- Fysieke maten komen uit de **OCT-kalibratie** (`--oct-mm`); controleer per dataset.
- Registratie steunt op **handmatige ankerpunten** (bewust; zie `../decisions.md`).
- Immuno-detectie is een **ondergrens** (dimmer signaal); vergelijk in het eerlijke gebied
  (ROI ∩ afdruk) en let op de match-straal-gevoeligheid in `results.json`.
- `detect`-drempels zijn adaptief (knik van de count-curve) en per beeld overschrijfbaar.
