# Landmark picker

Zelfstandige browser-tool om corresponderende punten te klikken. Bestand:
`point_picker.html` (beelden **ingebed** als base64 → dubbelklikken werkt, geen server nodig).
Gegenereerd door `porepair pick` / `work/build_picker.py`.

## Gebruik
- Klik een herkenbaar punt in **OCT** (links), dan hetzelfde in **immunolabel** (rechts). Herhaal 4–8×.
- **Slepen** = pannen · **scroll-wiel** = zoomen (naar cursor) · **⟲/⟳ + schuif** = roteren · **passend** = fit.
- Roteren/zoomen is puur weergave; **geëxporteerde coördinaten blijven in originele beeldpixels**
  (klik→native mapping via matrix-inversie, geverifieerd exact onder rotatie).
- **⤓ Exporteer JSON** → `points.json` (download + klembord + tekstvak).

## Formaat `points.json`
```json
{ "oct_image": "...", "imm_image": "...",
  "pairs": [ { "o": [x,y], "i": [x,y] }, ... ] }
```
Coördinaten in **native full-image pixels** van elk beeld.

## Tips
- **Bifurcaties/ridge endings** zijn het scherpst; **core**/**delta** helpen; duidelijke poriën ook.
- **Spreid** de punten over het overlap-gebied (belangrijk voor stabiele fit en TPS).
- 4–5 punten → affien/similarity; ≥6 goed verspreid → ook TPS mogelijk.

Voedt [[registration]]. Zie [[porepair-tool]] voor de generatie.
