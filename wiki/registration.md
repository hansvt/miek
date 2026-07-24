# Registration

De twee beelden op elkaar leggen: mapping **OCT → immuno**.

## Gekozen aanpak: handmatige ankerpunten + affien
Mens klikt 4–8 corresponderende punten ([[landmark-picker]]); we fitten een **affiene**
transform (least-squares). Voor run 2lindex+L2: 6 punten, residu **4,8 px gemiddeld**
(max 8,1), schaal 0,58, rotatie ~117°, as-hoek 89,6° (≈ geen shear). Overlay bevestigt:
ridges en loop-core vallen samen.

Opties: **similarity** (4 param, geen shear) als je minder vrijheid wilt; **TPS** (gaat exact
door alle punten) voor lokale aanscherping — maar extrapoleert slecht buiten de punten-hull,
dus spreid de punten goed.

## Waarom niet automatisch
Vijf automatische methodes faalden (poriën-RANSAC, oriëntatie-gestuurd, FFT-fasecorrelatie,
core-verankering, ICP): allemaal *plausibel-maar-fout*. Reden:
- **Poriën liggen quasi-regelmatig** → veel verschuivingen "passen" → ambigu.
- **Ridge-oriëntatie varieert traag** → zwak onderscheidend; twee verschillende gebieden
  halen al ~70% oriëntatie-overeenkomst.
- Onderscheidende kenmerken (minutiae, [[ridge-orientation-and-singular-points|core/delta]])
  zijn cross-modaal lastig automatisch te matchen.

Diagnostiek die dit aantoonde: oriëntatie-match-kaart (`out/diag_matchmap.png`) en de lage
oriëntatie-overeenkomst (~0,4) van de "beste" automatische fits. Details in `decisions.md`.

## Schaal-sanity-check
Ridge-periode (radiaal powerspectrum): OCT ~64 px, immuno ~34 px → schaal ~0,53–0,58.
Dit ontmaskerde een eerdere foute aanname (schaal ~1,0 door een te kleine FFT-patch).

## Kwaliteitsmaat
Het **landmark-residu** (px → µm) is de primaire maat, niet oriëntatie-overeenkomst.
Onder ~½ poriën-afstand is prima voor matching.

Zie ook [[landmark-picker]] en [[analysis-metrics]].
