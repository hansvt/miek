# Plan — betere poriën-annotatie in de immunolabeling image (artefact-reductie)

> **STATUS: geïmplementeerd (2026-07-24).**
> - **A** `optimize_imm()` = **MATLAB wit/zwart-balans** (imadjust/stretchlim percentiel-stretch
>   [0.01,0.99] binnen de regio; uit `OCT_FM2.txt`). Optioneel bg-subtract/CLAHE. Params gelogd.
> - **B** `estimate_pore_diameter()` → schaal-relatieve size-band / min-dist.
> - **C** `detect_regions_imm()` herschreven: Otsu op geoptimaliseerd beeld → regionprops →
>   size-band + eccentriciteit + solidity + circulariteit, met **verwerp-reden per blob**
>   (`imm_rejected.csv` + `imm_rejected.png`). Samengesmolten: `--merged-blobs split|reject`
>   (split houdt niet-splitsbare grote blob als één porie).
> - **D** `work/validate_imm_detection.py`: BW-referentie → **333 poriën** (ref ~316), alleen
>   speckle/ridge verworpen; overlays kept/rejected.
> - **G** regio-selectie in de app: **rechthoek** én **polygoon** tekenen (knoppen ▭/⬠, ✓ sluit,
>   ✕ wissen) plus vooraf-masker (CLI `--imm-region`, GUI "masker…"). Detectie draait binnen de regio.
> - MATLAB-getrouwe binarisatie-optie `--imm-bin fixed --imm-bin-thresh --imm-close` (default otsu).
> - **MATLAB-matching** (OCT_FM.txt) toegevoegd als optie: genormaliseerde **positie+oppervlakte**,
>   bidirectioneel, drempel (default 0,1) — `--match-method matlab` / GUI-dropdown. Vereist OCT-porie-
>   oppervlakte (nu meegemeten). Default blijft mutual-NN + halo-marge.
> - **E** `imm_curator.html` (klik-toevoegen/verwijderen, pan/zoom/rotate, export) +
>   `analyze --imm-points curated.json`. CLI `curate`; GUI bouwt hem mee.
> - **F** doorgetrokken naar `report.html` (sectie "Immuno-annotatie"), `protocol.docx`,
>   `results.xlsx` (blad `Immuno_Rejected`), `meta.json`.
> Kanttekening: op het **ruwe volledige** beeld overdetecteert de voorlopige `optimize_imm`
> (ridges); daarom draait detectie op een geselecteerde regio, en vervangt de MATLAB
> wit/zwart-balans later `optimize_imm` (WI-A).


Refereert aan en verfijnt **WI-1** uit `implementation_plan.md`. Doel: de poriën in de
immuno-image correct annoteren; nu worden ook **artefacten** als porie geteld.

Referentie-materiaal van de gebruiker (in `images/`):
- `geselecteerd_gebied_bw.jpg` — het handmatig **BW-geoptimaliseerde** geselecteerde gebied.
- `IML_counted pores.jpg` — "Analyse van 316 poriën": de correcte annotatie (blobs +
  centroïden + nummering + NN-verbindingen) op datzelfde gebied.

---

## Wat het onderzoek uitwees (waarom het nu misgaat)

1. **De 'correcte' referentie is Otsu op het BW-geoptimaliseerde gebied.** Otsu-drempel →
   connected components → centroïde op `geselecteerd_gebied_bw.jpg` geeft **exact 316** —
   gelijk aan de titel van de referentie. De gebruiker heeft dus vóór detectie een
   **beeldoptimalisatie-stap** (contrast + wit/zwart-balans) op een uitsnede gedaan die de
   tool niet repliceert.

2. **De tool detecteert op een andere input.** `detect_regions_imm()` draait white-tophat op
   het **ruwe/CLAHE rode kanaal** van de **volledige** image. Zonder de BW-optimalisatie
   overleven ridge-fragmenten en achtergrond-speckle de drempel → false positives.

3. **Parameters zijn schaal-afhankelijk (absolute pixels).** `tophat_radius=11`, `min_area=15`
   zijn getuned op de volledige 2816×1880 image. Op de 746-px referentie-uitsnede vindt
   dezelfde code maar **24** poriën (tophat-straal te groot t.o.v. de blob-grootte daar).
   De params transfereren dus niet tussen beelden/uitsneden.

4. **Vormfilter te dun.** Nu alleen area + circulariteit. De overlevende artefacten zijn
   vooral: **langwerpige ridge-fragmenten**, **samengesmolten smeren** (te groot) en
   **speckle** (te klein). Die vragen om rijkere vorm-criteria (solidity, eccentriciteit,
   size-band t.o.v. de mediaan).

---

## Aanpak (werkitems)

### A · Formaliseer de immuno-beeldoptimalisatie als expliciete, gedocumenteerde stap
Nu ontbreekt de stap die de referentie zo schoon maakt. Voeg een functie
`optimize_imm(image_bgr, channel="red")` toe (in `detect.py`) die de gebruikers-BW-stap
reproduceerbaar maakt: achtergrond-egalisatie (rolling-ball / grote-schaal Gaussische
achtergrond aftrekken), contrast-stretch met percentiel-clip (wit/zwart-balans), optioneel
CLAHE met **gedocumenteerde** parameters. Schrijf het resultaat weg als `imm_optimized.png`
zodat het te vergelijken is met `geselecteerd_gebied_bw.jpg`.
- Belangrijk onderscheid handhaven: de **detectie** draait op deze geoptimaliseerde image;
  CLAHE-visualisatie is alleen voor weergave.
- Alle parameters loggen (voedt WI-7 protocol.docx: "hoe is het beeld geoptimaliseerd").
- **Vervangbaar bouwen:** de gebruikers-MATLAB wit/zwart-balans komt later. Maak `optimize_imm`
  daarom modulair (één functie, duidelijke params) zodat de exacte MATLAB-stappen er 1-op-1
  in passen zonder A–F te raken. De default-optimalisatie is een *voorlopige* invulling.

**Bestanden:** `porepair/detect.py` (nieuw), `porepair/protocol.py` (params opnemen).

### B · Schaal-bewuste parameters (afgeleid uit de data, niet absoluut)
Schat de typische poriegrootte uit de image zelf (bv. mediane blob-diameter na een eerste
ruwe drempel, of via de ridge-periode die het project al kent). Druk daarna alle drempels
**relatief** uit:
- `tophat_radius ≈ k · pore_diameter`
- `min_area`, `max_area` als band rond de **mediane** blob-area (bv. 0,15×–6× mediaan)
- `min_dist` relatief aan de poriën-afstand.
Zo werkt dezelfde config op de volledige image én op een uitsnede.

**Bestanden:** `porepair/detect.py` (grootte-schatter + relatieve params).

### C · Rijkere artefact-verwerping + expliciete artefact-klassen
Filter elke kandidaat-blob op meerdere `regionprops`-maten en **log waarom** hij wordt
verworpen (zodat het controleerbaar en tunebaar is):
- **te klein** (area < ondergrens) → speckle
- **te groot / samengesmolten** (area > bovengrens) → smeer. **Twee instelbare opties**
  (`--merged-blobs split|reject`): *split* = distance-transform + watershed om de
  samengesmolten poriën terug te winnen; *reject* = weggooien. Beide implementeren; default
  bepalen tijdens validatie (WI-D).
- **te langwerpig** (eccentriciteit hoog / `major/minor` groot) → ridge-fragment
- **niet compact** (solidity laag, area/convex_area) → onregelmatig artefact
- **circulariteit** < drempel (bestaand)
Bewaar per verworpen blob de reden → `imm_rejected.csv` + een overlay
`imm_rejected.png` (verworpen artefacten in rood, behouden poriën in groen).

**Bestanden:** `porepair/detect.py` (`detect_regions_imm` uitbreiden met de extra criteria
en een `rejections`-uitvoer).

### D · Validatie-harnas tegen de referentie
Maak het meetbaar of de annotatie klopt:
- Reproduceer de referentie als **sanity-check** (geen hard doel): draai de pijplijn op
  `geselecteerd_gebied_bw.jpg` en rapporteer de telling naast de referentie **~316**. Een
  afwijking is toegestaan zolang de overlays (kept vs. rejected) er visueel goed uitzien —
  de visuele controle is leidend, het getal is indicatief.
- Twee overlays voor visuele controle: (1) behouden poriën op de geoptimaliseerde image,
  (2) verworpen artefacten apart — zodat de gebruiker in één blik ziet wat er wordt
  weggegooid en of dat terecht is.
- Print een korte telling per verwerp-reden (hoeveel speckle / smeer / ridge / onregelmatig).

**Bestanden:** klein validatiescript `work/validate_imm_detection.py` (niet-canoniek),
plus de overlays uit C.

### E · Handmatige correctie (curatie) als vangnet
Volautomatische detectie zal zelden 100% zijn. Geef de gebruiker de mogelijkheid om na de
auto-detectie **poriën toe te voegen/verwijderen** (klik-om-te-verwijderen, klik-om-toe-te-
voegen), analoog aan de bestaande `point_picker.html` / de Tkinter-app. Sla de gecureerde
puntenset op zodat telling/matching/afstand daarop draaien.
- Hergebruik de pan/zoom/rotate-interactie die al in `picker.py` / `app.py` bestaat.

**Bestanden:** `porepair/app.py` (of een nieuwe `imm_curator.html` naar model van
`picker.py`).

### F · Doorwerken in de rest van de pijplijn
Zorg dat de verbeterde annotatie overal landt: `analyze.py` (telling/matching/afstand op de
gecureerde set), `report.py` (toon geoptimaliseerde image + behouden vs. verworpen overlay),
WI-6 `results.xlsx` (blad met per-porie vorm-maten + verwerp-redenen), WI-7 `protocol.docx`
(optimalisatie- en filterparameters beschrijven).

---

## Volgorde
G (gebiedsselectie) → A (optimalisatie) → B (schaal-params) → C (artefact-filter) →
D (validatie tegen ~316 als sanity-check) → F (doorwerken) → E (handmatige curatie als
laatste vangnet). Later, zodra de MATLAB wit/zwart-balans binnen is: `optimize_imm` (WI-A)
vervangen door de exacte stappen en D opnieuw draaien.

## Beslissingen (bevestigd door gebruiker 2026-07-24)
- **316 = indicatie, geen waarheid.** Gebruik het als sanity-check / regressie-anker, niet
  als tuning-doel. Detectie mag ervan afwijken zolang de annotatie visueel klopt.
- **Gebruiker selecteert eerst een gebied.** Detectie draait **altijd op een door de
  gebruiker geselecteerde uitsnede**, niet automatisch over de hele afdruk → zie WI-G.
  Dit gebied sluit aan op de AOI-gedachte.
- **Samengesmolten blobs: bied BEIDE opties** — splitsen (watershed) én verwerpen — als een
  instelbare keuze (`--merged-blobs split|reject`, default nader te bepalen tijdens
  validatie). Zie WI-C.
- **MATLAB wit/zwart-balans komt later.** Tot die tijd: gedocumenteerde default-optimalisatie
  (WI-A), maar **volledig vervangbaar** — bouw `optimize_imm` zo dat de exacte MATLAB-stappen
  er later 1-op-1 in passen zonder de rest te raken.

---

## WI-G · Gebiedsselectie vóór detectie (nieuw, volgt uit beslissing 2)
De gebruiker bakent eerst een gebied af; detectie + telling gebeuren alléén daarbinnen.
- Interactieve rechthoek/polygoon-selectie op de immuno-image (hergebruik de pan/zoom/rotate
  uit `picker.py` / `app.py`), of accepteer een vooraf gemaakte masker-image zoals
  `geselecteerd_gebied_bw.jpg`.
- Sla de selectie op (`imm_region.json` / `imm_region_mask.png`) zodat de run reproduceerbaar
  is en het gebied gelijk kan worden gehouden met de AOI uit de registratie.
- Alle downstream-stappen (A–F) opereren binnen dit masker.

**Bestanden:** `porepair/app.py` (selectie-UI) of nieuwe `region_select.html` naar model van
`picker.py`; `porepair/detect.py` (masker respecteren); `porepair/analyze.py` (AOI ↔ selectie
consistent houden).
