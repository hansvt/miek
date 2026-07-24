# Tasks

## Status
- [x] Poriëndetectie OCT + immuno (getuned, gevalideerd) — OCT 525, immuno 533
- [x] Registratie via 6 handmatige ankerpunten → affien, residu ~5 px
- [x] Analyse: telling, matching, interporie-afstand (zie `out/RESULTS.md`)
- [x] Landmark-picker `point_picker.html` (pan/zoom/rotate, klik→native-pixel geverifieerd)
- [x] Write-up in projectstructuur (dit + `wiki/`)
- [x] Herbruikbare tool `porepair/` (CLI: detect/pick/analyze) — getest, reproduceert de run.
      Zie `wiki/porepair-tool.md` en `porepair/README.md`.
- [x] Desktop-app `porepair/app.py` (Tkinter): beelden kiezen → punten klikken → analyse+opslaan.
      `python -m porepair.app`. Coördinaat-mapping (zoom/rot/pan) geverifieerd.
- [x] Net rapport `report.html` (`porepair/report.py`), gestructureerd naar de 3 doelstellingen,
      met ingebedde figuren/tabellen; CLI + GUI openen het na afloop.
- [x] Tool-uitbreidingen uit `implementation_plan.md` (WI-1 t/m WI-8):
      WI-1 immuno region-detectie (instelbaar), WI-2 registratie-verfijning (default uit),
      WI-3 AOI-overlay, WI-4 matchmarge, WI-5 NN-tabel + genummerde kaarten,
      WI-6 `results.xlsx`, WI-7 `protocol.docx`, WI-8 `overlay_viewer.html`.

- [x] App herbouwd als 3-staps wizard (beelden → overlay/AOI → enhance+detecteer binnen AOI).
      `analyze.compute_aoi()` uitgefactored zodat stap-2-preview = werkelijke AOI. Getest via
      `work/test_wizard.py` (headless flow-simulatie).
- [x] Betere immuno-annotatie / artefact-reductie (`annotation_improvement_plan.md`):
      optimize_imm (A), schaal-params (B), rijk vormfilter + verwerp-redenen (C), validatie
      333≈316 (D), regio-masker (G), curator + --imm-points (E), doorgetrokken (F).

## Volgende / open punten
- Interactief regio **tekenen** (rechthoek/polygoon) i.p.v. vooraf-masker (WI-G-rest).
- Echte MATLAB wit/zwart-balans in `optimize_imm` plaatsen; daarna WI-D opnieuw draaien.
- Immuno-detectiegevoeligheid: de 1,8× meer poriën in OCT is deels detectie-artefact
  (immuno zwakker). Optie: lagere drempel voor immuno en effect op telling/matching tonen.
- TPS-fit op de 6 punten als optionele lokale aanscherping (nu affien).
- Valideren op meer beeldparen via `porepair`; per dataset OCT-kalibratie (mm) checken.
- Overweeg per-porie kwaliteit/zekerheid i.p.v. binaire detectie.

## Open vragen
- Wat is de exacte fysieke schaal van het immuno-beeld (nu afgeleid via transform)?
- Zijn "alleen-immuno" kralen echte poriën of labelruis? (validatie nodig)
