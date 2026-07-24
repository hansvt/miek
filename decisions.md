# Decisions (newest first)

## 2026-07-24 — App herbouwd als 3-staps wizard: overlay vóór poriën-detectie
**Besluit:** `porepair/app.py` is herstructureerd van "open beelden → detecteer meteen → klik
punten → analyseer" naar een expliciete **3-staps wizard**:
1. **Beelden selecteren** — geen enkele detectie.
2. **Overlay maken** — ankerpunten klikken → transform fitten → **AOI** (overeenkomend gebied)
   berekenen en tonen als preview (magenta OCT op groen immuno, AOI oranje omlijnd) vóórdat
   er één porie gedetecteerd is.
3. **Enhancen + poriën berekenen** — detectie (incl. de MATLAB wit/zwart-balans voor immuno)
   draait nu **binnen de AOI uit stap 2**, niet blind over het hele beeld.

**Waarom:** poriën-detectie tunen op het volledige beeld is zinloos als een groot deel ervan
buiten het gebied valt dat met de andere modaliteit overeenkomt — je ziet dan ruis/artefacten
die toch worden weggegooid. Door de AOI eerst vast te leggen (via registratie) en dáárna pas te
detecteren, tunet de gebruiker direct op de relevante data, en is de vroegere handmatige
rechthoek/polygoon (nog beschikbaar als **optionele extra verfijning bovenop** de AOI) niet meer
de primaire manier om het gebied te bepalen.

**Implementatie:** `analyze.compute_aoi()` uitgefactored (was inline in `run()`) zodat zowel de
CLI/GUI-analysestap als de nieuwe stap-2-preview in de app dezelfde AOI-berekening gebruiken —
wat je in stap 2 ziet is exact het gebied dat in stap 3 wordt gebruikt. Getest met een headless
smoke-test (`work/test_wizard.py`) die de volledige flow simuleert zonder file-dialogs.

## 2026-07-24 — Betere immuno-annotatie / artefact-reductie (annotation_improvement_plan.md)
Immuno-detectie herzien: **optimaliseren → Otsu → regionprops → rijk vormfilter met verwerp-reden**
i.p.v. tophat-puntmaxima. Kern-inzichten: (1) de referentie "316 poriën" = Otsu op het handmatig
**BW-geoptimaliseerde** gebied → `optimize_imm()` maakt die stap reproduceerbaar (voorlopig; MATLAB
wit/zwart-balans vervangt later, modulair opgebouwd); (2) parameters **schaal-relatief** (afgeleid
uit geschatte poriediameter), niet absoluut; (3) artefacten (speckle/smeer/ridge/onregelmatig)
apart geklasseerd en gelogd (`imm_rejected.csv/.png`); (4) detectie draait op een **geselecteerde
regio** (`--imm-region` / GUI-masker). Validatie op de BW-referentie: **333 ≈ 316**. Samengesmolten
blobs: `--merged-blobs split|reject` (default split, niet-splitsbaar = één grote porie). Handmatige
**curatie** als vangnet via `imm_curator.html` + `analyze --imm-points`. Doorgetrokken naar
rapport/protocol/Excel. **316 blijft indicatie, geen tuning-doel** (visuele controle leidend).
Nog open: interactief regio-**tekenen** (nu vooraf-masker), en de echte MATLAB-optimalisatie.

## 2026-07-24 — MATLAB wit/zwart-balans + interactief regio tekenen (uit OCT_FM2.txt / OCT_FM.txt)
`optimize_imm()` is nu de **echte MATLAB wit/zwart-balans** (`imadjust`/`stretchlim`, percentiel-stretch
[0.01,0.99] binnen de geselecteerde regio; uit `OCT_FM2.txt`), i.p.v. de voorlopige bg-subtract.
Validatie BW-referentie: **321 ≈ 316**. Binarisatie default **otsu** (robuust); MATLAB-getrouwe
`fixed`-drempel + `imclose` als optie (`--imm-bin fixed`), maar absoluut-drempel transfereert slecht.
**WI-G**: naast vooraf-masker nu ook **interactief rechthoek tekenen** in de app ("▭ regio tekenen").
Nog open: MATLAB-matching (OCT_FM.txt: positie+oppervlakte gecombineerd, genormaliseerd, drempel 0.1)
als alternatief voor de huidige mutual-NN; en polygoon-regio.

## 2026-07-24 — WI-2/3/4/6/7/8 afgerond (rest van implementation_plan.md)
- **WI-4** matchmarge: straal = `match_frac·NN + k·mediaan(regio-straal)` (k default 0,5); mutual-NN ongemoeid.
- **WI-2** registratie-verfijning met poriën-correspondenties (ankerpunten ×3 gewogen): **default UIT**.
  Op deze dataset verhoogde het juist het ankerpunt-residu (4,8→6,2 px), dus niet standaard aan; rapport toont beide residuen.
- **WI-3** tweede overlay `overlay_aoi.png` (alleen AOI, daarbuiten gedimd); AOI = eerlijk gebied.
- **WI-8** interactieve `overlay_viewer.html` (pan/zoom/rotate + cross-fade OCT↔immuno).
- **WI-6** `results.xlsx` (Summary/Transform/Config/Matched_Pairs/OCT_Pores/Immuno_Pores/Matched_NN).
- **WI-7** `protocol.docx` (methoden-sectie, gevuld uit de run) — voor publicatie herschrijfbaar.
Extra deps: matplotlib, pandas, openpyxl, python-docx (zie `requirements.txt`).

## 2026-07-24 — WI-1 immuno region-detectie + WI-5 NN-tabel/kaarten (uit implementation_plan.md)
**WI-1:** immuno-poriën nu via **region/centroid** i.p.v. top-hat puntmaxima. Aanpak:
white-tophat (radius 11) op het ruwe rode kanaal verwijdert de continue ridge → de kralen
(poriën) blijven als losse bobbels → Otsu → circulariteit ≥ 0,40, min-area 15 px → centroïden
+ equiv_radius. Dit gaf losse ronde poriën waar de MATLAB-route (Otsu op ruw + watershed) juist
ridge-segmenten opleverde. Beide detectoren draaien, **beide beelden opgeslagen**
(`imm_pores_regions.png` + `imm_pores.png`); region is primair (`--imm-detect`, default region).
**WI-5:** per-porie nearest-neighbour tabel (`*_nn.csv`: Porie_ID, Coordinates, Nearest_neighbour_ID,
Distance_neighbour µm, Angle_neighbour °) + genummerde kaarten voor OCT/immuno/gematcht.
Hoek-conventie: atan2(dy,dx), x-rechts/y-omlaag, 0°=rechts, +=met de klok mee — **te bevestigen**
tegen de voorbeeldtabel in de bron-docx (docx staat niet in de repo).
Checkpoint: WI-2/3/4/6/7/8 nog te doen (zie `implementation_plan.md`).

## 2026-07-23 — Rapport gestructureerd naar de drie doelstellingen
De analyse-uitvoer is een net, zelfstandig **`report.html`** (`porepair/report.py`): ingebedde
figuren + tabellen, printbaar naar PDF. Secties = de projectdoelstellingen: (1) poriëntelling in
de AOI (volledige OCT-area, zelfde area in immuno), (2) matching (gedeeld / alleen-OCT /
alleen-immuno), (3) interporie-afstand van de **gematchte** poriën (headline; all-pore als context).
CLI en GUI openen het rapport na afloop.

## 2026-07-23 — Herbruikbare tool `porepair/`
De pijplijn is geconsolideerd tot een CLI-tool `porepair` (detect → pick → analyze) zodat
andere beeldparen dezelfde analyse kunnen ondergaan. De verkennende scripts in `work/`
blijven als historie staan maar zijn niet canoniek. Zie `wiki/porepair-tool.md`.

## 2026-07-23 — Registratie via handmatige ankerpunten + affiene transform
**Besluit:** OCT→immuno registratie gebeurt met een **handjevol handmatig aangewezen
corresponderende punten** (via `point_picker.html`), waarna een **affiene** transform wordt
gefit. Voor deze dataset: 6 punten, residu 4,8 px gemiddeld (~80–130 µm), schaal 0,58,
rotatie ~117°, verwaarloosbare shear.

**Waarom / verworpen alternatieven:** vijf volautomatische methodes faalden — poriën-RANSAC,
oriëntatie-gestuurde zoek, FFT-fasecorrelatie op het oriëntatieveld, core-verankering
(Poincaré), en ICP. Ze convergeerden telkens naar *plausibele-maar-foute* uitlijningen.
Oorzaak: (1) poriën liggen in een **quasi-regelmatig rooster** → veel verschuivingen
"passen" (ambigu); (2) **ridge-oriëntatie varieert traag** → zwak onderscheidend, twee
verschillende gebieden halen al ~70% oriëntatie-overeenkomst. De onderscheidende kenmerken
(minutiae, core/delta) zijn cross-modaal lastig automatisch te matchen. Handmatige punten
zijn de professionele standaard voor multimodale registratie en gaven direct een goede fit.

**Vervorming:** de door de gebruiker verwachte niet-lineaire vervorming bleek **klein**
(affiene residu ~5 px, nauwelijks shear); affiene volstaat. TPS op dezelfde punten blijft
optioneel voor lokale aanscherping (maar extrapoleert slecht buiten de punten-hull).

## 2026-07-23 — Poriëndetectie
White-tophat (schijf ~9–11 px) + lokale-maxima. Drempel bij de **knik** van de curve
"aantal pieken vs. drempel" (adaptief, generaliseert beter dan een vaste waarde).
Immuno: **rood-kanaal**, en een **afdruk-mask** = grootste samenhangende component na
zware blur+drempel, om achtergrondruis/liniaal buiten te sluiten.
Resultaat deze dataset: OCT 525, immuno 533 poriën.

## 2026-07-23 — Fysieke schaal uit OCT-kalibratie
OCT-beeld = 10×10 mm over 1044×1154 px → 9,58 µm/px (x), 8,67 µm/px (y), licht anisotroop.
Immuno-schaal wordt via de registratie-transform afgeleid (niet los geraden). Ridge-periode
bevestigt: OCT ~64 px, immuno ~34 px → OCT is ~0,58× ingezoomd (immuno ~16,6 µm/px).

## 2026-07-23 — Rapportagekeuzes analyse
Poriëntelling zowel voor de **volledige OCT-ROI** (zoals gevraagd) als voor het **eerlijke
gebied** (ROI ∩ immuno-afdruk), omdat een deel van de ROI buiten de gelabelde afdruk valt.
Matching via **mutual nearest-neighbour**; match-straal-gevoeligheid expliciet gerapporteerd.
Interporie-afstand als nearest-neighbour, zowel over alle poriën (beste schatting) als over
de gematchte subset.
