# Data

Twee beelden van (naar verwachting) dezelfde vingerafdruk, met verschillende methodes.

## `images/2lindex_.jpg` — OCT
- 1044×1154 px, grijswaarden (als BGR opgeslagen).
- Fysiek: **10 × 10 mm** voor het hele beeld → **9,58 µm/px (x), 8,67 µm/px (y)** (licht anisotroop).
- Poriën = **witte puntjes** op de ridges; ridges zijn donkere lijnen.
- Eigenaardigheden: verticale **scan-lijn-artefacten** bovenaan; **zwarte band** links en
  zwarte hoek linksonder (buiten geldig weefsel → uitgesloten via validity-mask).
- Bevat een loop-**core** en een **delta** (zichtbaar in het oriëntatieveld).

## `images/L2_index_mag_20sec_500.CR2.JPG` — immunolabel
- 2816×1880 px; signaal in het **rode kanaal** (rest bijna zwart).
- De afdruk zelf ≈ **1 × 2 cm**; afgeleide schaal via registratie ≈ **16,6 µm/px**
  (OCT is ~0,58× ingezoomd t.o.v. immuno).
- Poriën = **rode kralen** langs de ridges. Signaal is **dim/onvolledig** buiten de kern —
  daardoor detecteert immuno minder poriën dan OCT.
- Eigenaardigheden: **liniaal/schaalbalk** bovenaan het frame, los rechthoekig object
  linksboven, verspreide stof-/ruisstippen — allemaal buiten de **afdruk-mask** gehouden
  (grootste samenhangende component).

## Naamgeving (van de gebruiker)
`2lindex` = OCT · `L2_index_mag_20sec_500` = immunolabel (mag 20 = 20× objectief).
