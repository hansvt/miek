# Project: miek — OCT ↔ immunolabel poriën-analyse

Onderdeel van het CMC/DDS-portfolio (zie portfolio-`CLAUDE.md` één niveau hoger).

## Wat dit project is
Vingerafdrukken worden met twee methodes vastgelegd — **OCT** (en-face, poriën = witte
puntjes) en **immunolabeling** (fluorescentie, poriën = rode kralen). Doel: de twee
beelden **op elkaar leggen** (registratie) en dan poriën **tellen, matchen en de
interporie-afstand meten** in een gedeelde area of interest (de OCT-uitsnede).

## Lees dit eerst
- `decisions.md` — waarom de aanpak is zoals hij is (nieuwste bovenaan)
- `glossary.md` — termen (OCT, immunolabel, core/delta, Poincaré, TPS, …)
- `tasks.md` — status en open punten
- `data/README.md` — de beelden, hun schaal en eigenaardigheden
- `wiki/index.md` — kennisbank (detectie, registratie, metrieken, de tool)

## Hoe te werken
- De herbruikbare pijplijn staat in `porepair/` (CLI). Zie `wiki/porepair-tool.md`.
- Losse verkennende scripts staan in `work/` (historie; niet de canonieke tool).
- Uitvoer/artefacten in `out/`.
- Registratie vereist **handmatige ankerpunten** (via `point_picker.html`); volautomatische
  registratie is bewust verworpen — zie `decisions.md`.

## Belangrijk
- Fysieke maten komen uit de **OCT-kalibratie** (beeld = 10×10 mm). Controleer die per dataset.
- Rapporteer poriëntellingen zowel voor de volledige ROI als voor het eerlijke gebied
  (ROI ∩ immuno-afdruk), en vermeld de match-straal-gevoeligheid.
