# QUICKSTART — porepair

Poriën-analyse van een **OCT**- en een **immunolabel**-vingerafdruk: registreren, poriën tellen,
matchen en de interporie-afstand meten. Zie ook `porepair/README.md` en `wiki/`.

## 0. Eenmalige setup
Vereist: **Git**, **Python 3.10+** (tkinter zit standaard bij Python op Windows).
```bash
git clone https://github.com/hansvt/miek.git
cd miek
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell; daarna volstaat `python ...`
pip install -r requirements.txt
```
Zet je eigen beelden in een map `images\` (de vingerafdrukbeelden zitten **niet** in de repo).

---

## 1. Aanbevolen: de desktop-app
```bash
python -m porepair.app
```
Stappen in het venster:

1. **1. Open OCT…** — kies het OCT-beeld (poriën = witte puntjes; worden meteen gedetecteerd).
2. **2. Open immunolabel…** — kies het immuno-beeld (poriën = rode kralen).
3. **Regio afbakenen** — klik **▭ regio tekenen** en sleep een rechthoek op het immuno-beeld
   (of **regio-masker…** om een maskerbeeld te laden). Detectie draait alléén binnen die regio —
   aanbevolen, want op het volledige ruwe beeld overdetecteert het (ridges). **✕ regio wissen** reset.
   De immuno-optimalisatie (wit/zwart-balans) is de MATLAB `imadjust`/`stretchlim`-stretch.
4. **Immuno-detectie tunen** — pas **circ / min-frac / max-frac** aan, kies **merged = split/reject**,
   klik **↻ her-detecteer immuno**. Herhaal tot de poriën goed gemarkeerd staan (verschilt per beeld).
5. **Ankerpunten klikken** — klik een herkenbaar punt in **OCT** (links), dan hetzelfde in
   **immuno** (rechts). Herhaal **4–8 paren**, goed verspreid.
   Per beeld: slepen = pannen · wiel = zoomen · ⟲/⟳ + schuif = roteren · "passend" = terug.
6. **Instellen** (bovenin): **OCT-grootte** in mm, **transform** (affine), evt. **match k**
   en **poriën-verfijning**.
7. **3. Analyse + opslaan** — kies een map; het rapport opent automatisch.

### Handmatig bijwerken (vangnet)
Is de auto-detectie niet perfect? Open **`imm_curator.html`** uit de outputmap → klik poriën
weg / voeg toe (de knop wisselt de modus) → **exporteer** → `curated_points.json`. Draai dan:
```bash
python -m porepair analyze --out OUT --points OUT\points.json --imm-points OUT\curated_points.json --oct-mm 10x10
```

---

## 2. Alternatief: de command-line (zonder GUI)
```bash
python -m porepair detect  --oct images\oct.jpg --imm images\immuno.jpg --out out [--imm-region masker.png]
# open out\point_picker.html, klik de paren, exporteer points.json
python -m porepair analyze --out out --points points.json --oct-mm 10x10
```
Handige extra commando's: `python -m porepair view --out out` (overlay-viewer herbouwen),
`python -m porepair curate --out out` (curator herbouwen).

Belangrijkste opties — `detect`: `--imm-detect region|tophat`, `--imm-region`, `--merged-blobs split|reject`,
`--imm-circularity/--imm-min-area-frac/--imm-max-area-frac`. `analyze`: `--transform affine|similarity|tps`,
`--match-margin-k`, `--refine-pores`, `--imm-points`.

---

## 3. Wat je krijgt (in de outputmap)
- **`report.html`** — het nette rapport (open/print naar PDF): telling, matching, interporie-afstand,
  registratie, immuno-annotatie.
- **`overlay_viewer.html`** — interactieve overlay (zoom/roteren, cross-fade OCT↔immuno).
- **`imm_curator.html`** — handmatige poriën-curatie.
- **`results.xlsx`** — alle cijfers per blad · **`protocol.docx`** — methodenbeschrijving.
- Controlebeelden: `imm_optimized.png`, `imm_rejected.png` (behouden vs. verworpen),
  `analysis.png`, `overlay.png` / `overlay_aoi.png`, genummerde kaarten, NN-tabellen (`*_nn.csv`).

## Let op
- Fysieke maten komen uit de **OCT-kalibratie** (`--oct-mm`, standaard 10×10 mm) — controleer per dataset.
- Immuno-detectie is een **ondergrens** (dimmer signaal); vergelijk in het eerlijke gebied (AOI).
- "316 poriën" uit de referentie is een **indicatie**, geen doel — de visuele controle is leidend.
