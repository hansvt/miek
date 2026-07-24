# Pipeline overview

Doel: OCT- en immunolabel-beeld van dezelfde vingerafdruk op elkaar leggen en poriën
tellen, matchen en de interporie-afstand meten in een gedeelde ROI.

## Stappen
1. **Detectie** ([[pore-detection]]) — poriën als puntenwolk in elk beeld.
2. **Ankerpunten kiezen** ([[landmark-picker]]) — mens klikt 4–8 corresponderende punten.
3. **Registratie** ([[registration]]) — fit affiene (of similarity/TPS) transform OCT→immuno.
4. **Analyse** ([[analysis-metrics]]) — ROI = OCT-area; tel poriën in beide beelden,
   match ze (mutual nearest-neighbour), meet interporie-afstand in µm.

## Waarom deze volgorde
Detectie en registratie zijn losgekoppeld: de registratie steunt op **handmatige punten**
(niet op de poriën zelf), want het poriën-rooster is quasi-regelmatig en dus ambigu
([[registration]]). De poriën worden pas ná registratie gebruikt, voor de meting.

## Herbruikbaar
De hele keten zit in [[porepair-tool]] (`porepair detect | pick | analyze`).
De verkennende scripts in `work/` zijn historie (o.a. de verworpen automatische registraties).

## Kernaannames
- Fysieke schaal komt uit de **OCT-kalibratie** (per dataset opgeven, standaard 10×10 mm).
- De ROI is de **geldige OCT-area**; voor eerlijke vergelijking ook ROI ∩ immuno-afdruk.
