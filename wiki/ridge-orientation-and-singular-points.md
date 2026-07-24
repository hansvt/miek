# Ridge orientation & singular points

## Oriëntatieveld
Lokale ridge-richting via de **structuurtensor**: gradiënten (Sobel) → tensor-componenten
Gaussisch gladstrijken → θ = ½·atan2(2·Jxy, Jxx−Jyy) (mod π), plus **coherentie** (hoe
uitgesproken de richting is). Modaliteit-onafhankelijk (werkt op OCT én immuno).
Code: `porepair/orient.py` (en `work/orient.py`).

Gebruik: schaal-sanity-check (ridge-periode), visualisatie (quiver), en singulier-detectie.
**Niet** geschikt als hoofd-signaal voor registratie — varieert te traag ([[registration]]).

## Singuliere punten
- **Core** (loop-centrum): Poincaré-index **+½**.
- **Delta** (drie systemen samen): Poincaré-index **−½**.
- **Poincaré-index**: som van oriëntatieverschillen (mod π) langs een kleine lus.

## Ervaring in dit project
De **immuno-core** werd betrouwbaar gevonden (~(1596, 780)). De **OCT-singulier-detectie**
was rumoerig (rand-/scan-artefacten domineerden), en core-verankering gaf geen goede globale
fit → bevestigt de keuze voor handmatige ankerpunten. Zie `out/oct_singular.png`,
`out/imm_singular.png` en `decisions.md`.
