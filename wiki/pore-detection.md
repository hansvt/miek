# Pore detection

Poriën zijn kleine heldere blobs: witte puntjes (OCT) of rode kralen (immuno).

## Methode
1. Kanaal kiezen: OCT = grijswaarden; immuno = **rood kanaal**.
2. Lichte Gaussische blur → **white top-hat** (schijf ~9–11 px) isoleert kleine heldere blobs
   en verwijdert de langzaam variërende achtergrond/ridges.
3. **Lokale maxima** (`peak_local_max`, `min_distance` ~12–16 px) geven één punt per porie.
4. **Drempel** bij de **knik** van de curve *aantal pieken vs. drempel*: onder de knik
   explodeert het aantal (ruis), erboven stabiliseert het. Adaptief → generaliseert.

## Immuno: region/centroid-detectie (WI-1)
Het immuno-signaal toont vooral het **uitgescheiden materiaal rondom de porie**, niet de porie
zelf → we nemen de **centroïde van de porie-regio**, niet een puntmaximum. Werkwijze op het
**ruwe** rode kanaal (geen CLAHE): white-tophat verwijdert de continue ridge zodat de kralen
als losse bobbels overblijven → Otsu → **circulariteitsfilter** (default 0,40) + min-area
(default 15 px) → centroïden + `equiv_radius` (regio-grootte = natuurlijke matchmarge, WI-4).
Beide methodes (region + top-hat) draaien en worden opgeslagen (`imm_pores_regions.png` +
`imm_pores.png`); `--imm-detect` kiest de primaire (default region).

**Parameters verschillen per beeld** en staan daarom niet vast: instelbaar via CLI-flags
(`--imm-circularity`, `--imm-min-area`, `--imm-tophat`) én **live in de GUI** (knop
"her-detecteer immuno"), zodat je per dataset tunt en het resultaat direct ziet.

## Maskers (waar wél tellen)
- **OCT validity**: `grijs > 25`, geërodeerd → sluit zwarte band/scan-artefacten uit.
- **Immuno afdruk-mask**: zware blur → drempel (~p85) → **grootste samenhangende component**
  → sluit liniaal, losse objecten en verspreide ruisstippen buiten.

## Resultaat (run 2lindex + L2)
OCT **525** poriën, immuno **533** poriën (hele afdruk). In de OCT-ROI: OCT 524, immuno 243
— immuno detecteert minder doordat het signaal dimmer/onvollediger is. Zie [[analysis-metrics]].

## Valkuilen
- Te lage drempel → ridge-textuur en ruis worden meegeteld.
- Immuno buiten de kern is dim; de telling daar is een **ondergrens** (detectiegevoeligheid).
- Parameters zitten in [[porepair-tool]] als opties (`--tophat`, `--min-dist`, `--imm-channel`, …).

Zie ook [[registration]] (gebruikt de detecties niet direct) en
[[ridge-orientation-and-singular-points]].
