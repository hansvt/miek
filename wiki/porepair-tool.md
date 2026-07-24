# porepair — de herbruikbare tool

CLI-pakket in `porepair/` dat de hele pijplijn ([[pipeline-overview]]) uitvoert voor
willekeurige OCT+immuno-beeldparen. Volledige handleiding: `porepair/README.md`.

## Desktop-app (aanbevolen) — 3-staps wizard
`python -m porepair.app` (of `python -m porepair gui`). Code: `porepair/app.py` (Tkinter, geen
extra installatie). Drie stappen, met een stepper bovenin:
1. **Beelden** — alleen selecteren, geen detectie.
2. **Overlay** — ankerpunten klikken → transform fitten → preview van het **overeenkomende
   gebied (AOI)** vóórdat er iets gedetecteerd wordt (`analyze.compute_aoi()`, gedeeld met de
   analysestap zodat preview = werkelijkheid).
3. **Poriën** — detectie (incl. immuno-enhancement, [[pore-detection]]) draait **binnen die AOI**;
   tunen + optionele extra rechthoek/polygoon-beperking; dan "Analyse + opslaan".

Waarom deze volgorde: detectie tunen op het hele beeld is zinloos buiten het gebied dat toch met
de andere modaliteit overeenkomt. Zie `decisions.md` (2026-07-24).

## Drie stappen (CLI)
```bash
python -m porepair detect  --oct OCT.jpg --imm IMMUNO.jpg --out out
# open out/point_picker.html, klik 4-8 paren, exporteer points.json
python -m porepair analyze --out out --points points.json --oct-mm 10x10
```
- **detect** — poriëndetectie ([[pore-detection]]) in beide beelden; schrijft punten, maskers,
  controlebeelden én `point_picker.html` ([[landmark-picker]]). Drempel adaptief (knik van de
  count-curve), overschrijfbaar met `--oct-thr/--imm-thr`.
- **pick** — (her)genereert alleen de picker (handig na parametertweaks).
- **analyze** — fit transform ([[registration]], `--transform affine|similarity|tps`) en draait
  de analyse ([[analysis-metrics]]); schrijft `RESULTS.md`, `results.json`, `analysis.png`,
  `overlay.png`, `matched_pairs.csv`.

## Modules
- `detect.py` — top-hat + lokale maxima + adaptieve drempel; OCT- vs afdruk-mask.
- `orient.py` — oriëntatieveld ([[ridge-orientation-and-singular-points]]).
- `transform.py` — `Transform`-klasse (affine/similarity/tps), forward + inverse.
- `analyze.py` — telling, mutual-NN matching, interporie-afstand in µm, visualisatie, rapport.
- `picker.py` — bouwt de zelfstandige HTML-picker (beelden ingebed).
- `cli.py` / `__main__.py` — de CLI.

## Getest
Reproduceert de eerste run ([[run-2lindex-L2]]): affien residu 4,8 px, schaal 0,58,
rotatie 117°, interporie-afstand ~300 µm. similarity/affine/tps alle drie werkend
(tps = exacte fit op de ankerpunten).

## Verschil met `work/`
`work/` bevat de verkennende scripts (incl. de verworpen automatische registraties);
`porepair/` is de opgeschoonde, geparametriseerde, canonieke tool.
