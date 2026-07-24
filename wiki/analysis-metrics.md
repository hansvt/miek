# Analysis metrics

Na registratie ([[registration]]) worden poriën ([[pore-detection]]) gemeten in de ROI.

De analyse volgt de drie projectdoelstellingen en wordt samengevat in een net,
zelfstandig **`report.html`** (figuren + tabellen ingebed; printbaar naar PDF).
Gegenereerd door `porepair/report.py`.

## ROI (area of interest)
- **Volledige ROI** = geldige OCT-area (hier 95,2 mm²); via de transform wordt **dezelfde area**
  in het immuno-beeld aangehouden (doelstelling 1).
- **Eerlijk gebied** = ROI ∩ immuno-afdruk (hier 80% van de ROI). Nodig omdat een deel van de
  ROI buiten de gelabelde afdruk valt (immuno heeft daar geen signaal → schijnbaar "alleen-OCT").

## 1 · Telling
Aantal gedetecteerde poriën per beeld binnen de ROI. OCT-poriën worden via de transform naar
het immuno-frame gemapt zodat alles in één stelsel ligt.

## 2 · Matching — mutual nearest-neighbour
Twee poriën matchen alleen als ze **elkaars** dichtstbijzijnde zijn binnen een straal
(standaard ~0,45× de mediane poriën-afstand). Klassen: **gedeeld**, **alleen-OCT**,
**alleen-immuno**. Rapporteer de match-straal-**gevoeligheid** (aantallen bij bv. 9/12/15 px),
want het aantal gedeelde hangt ervan af.

## 3 · Interporie-afstand (µm)
Nearest-neighbour afstand tussen poriën, in µm via de **OCT-kalibratie**.
- **Alle ROI-poriën** = beste schatting van de werkelijke poriën-afstand.
- **Gematchte subset** = hoger (dunnere set); vermeld dit expliciet.
- Aparte maat: **positie-overeenkomst van gematchte paren** (registratie+localisatie-nauwkeurigheid).

## Resultaat run 2lindex+L2 (samenvatting)
Telling ROI: OCT 524 / immuno 243 (eerlijk gebied OCT 428). Gedeeld 159, alleen-OCT 269,
alleen-immuno 84. Interporie-afstand ~312 µm (OCT, alle poriën). Paar-overeenkomst mediaan 112 µm.
Volledige cijfers: [[run-2lindex-L2]] en `out/RESULTS.md`.

## Genummerde kaarten & NN-tabel (WI-5)
Per porie een nearest-neighbour tabel (`oct_nn.csv`, `imm_nn.csv`, `matched_nn.csv`) met
kolommen **Porie_ID, Coordinates, Nearest_neighbour_ID, Distance_neighbour** (µm),
**Angle_neighbour** (°). Hoek-conventie: `atan2(dy,dx)`, x-rechts/y-omlaag, 0°=rechts, positief =
met de klok mee. Bijbehorende genummerde kaarten: `oct_pores_numbered.png`,
`imm_pores_numbered.png`, `matched_numbered.png` (ID + centroïd + lijn naar dichtstbijzijnde buur).

## Kanttekeningen
- OCT ~1,8× meer poriën: deels biologie, deels **detectiegevoeligheid** (immuno dimmer) →
  immuno-telling is een ondergrens.
- "Alleen-immuno" = kralen zonder OCT-tegenhanger: echte poriën óf labelruis (validatie nodig).
