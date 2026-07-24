# Run: 2lindex (OCT) + L2_index (immuno)

Eerste volledige analyse (2026-07-23). Volledige uitvoer: `out/RESULTS.md`, `out/analysis.png`,
`out/overlay_lm_crop.png`, `out/matched_pairs.csv`.

## Invoer
- OCT `2lindex_.jpg` (10×10 mm), immuno `L2_index_mag_20sec_500.CR2.JPG`. Zie `data/README.md`.

## Registratie
6 handmatige ankerpunten (`work/points.json`) → affien. Residu 4,8 px gem. (max 8,1),
schaal 0,58, rotatie ~117°, ≈ geen shear.

## Resultaten
- **Telling (ROI 95,2 mm²):** OCT 524 · immuno 243 · eerlijk gebied (80% van ROI) OCT 428.
  Dichtheid OCT 5,5 /mm², immuno 2,6 /mm². OCT ~1,8× meer.
- **Matching (eerlijk gebied):** gedeeld 159 · alleen-OCT 269 · alleen-immuno 84.
  65% van immuno-poriën heeft een OCT-match. Straal-gevoeligheid: gedeeld 116/159/196 bij 9/12/15 px.
- **Interporie-afstand:** ~312 µm (OCT, alle poriën, mediaan); immuno 413 µm; gematchte subset ~425 µm.
  Positie-overeenkomst gematchte paren: mediaan 112 µm.

## Kanttekeningen
Zie [[analysis-metrics]]: het 1,8×-verschil is deels detectiegevoeligheid (immuno dimmer);
immuno-telling is een ondergrens. Match-aantallen zijn straal-afhankelijk.
