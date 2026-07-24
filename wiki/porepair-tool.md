# porepair — de herbruikbare tool

CLI-pakket in `porepair/` dat de hele pijplijn ([[pipeline-overview]]) uitvoert voor
willekeurige OCT+immuno-beeldparen. Volledige handleiding: `porepair/README.md`.

## Desktop-app (aanbevolen)
`python -m porepair.app` (of `python -m porepair gui`) opent één venster: beelden kiezen →
auto-detectie → punten klikken (pan/zoom/roteren) → "Analyse + opslaan". Code: `porepair/app.py`
(Tkinter, geen extra installatie). Hergebruikt dezelfde modules als de CLI.

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
