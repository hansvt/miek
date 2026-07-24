# Implementation plan — porepair updates (from "Aanpassingen tool" feedback)

Source: `Aanpassingen tool_Bij registratie in de overlay image.docx` (uploaded 2026-07-24).
Target codebase: `porepair/` (detect.py, transform.py, analyze.py, report.py, picker.py, app.py, cli.py).

This is written as a set of self-contained work items so each can be handed to Claude Code
one at a time (or in the suggested order at the bottom). Each item lists: what was asked,
what exists today, the concrete change, files touched, and acceptance criteria. Open
decisions that need a quick answer before coding are called out — flag these back to the
user rather than guessing.

---

## WI-1 — Immuno pore detection: region/centroid based, not top-hat point maxima
> **STATUS: DONE (2026-07-24).** `detect.detect_regions_imm()`: white-tophat (radius 11) removes
> the continuous ridge so pore beads separate, Otsu binarise, circularity ≥ 0.40, min-area 15 px →
> centroids + equiv_radius. ~510 immuno pores. BOTH detectors run and both images saved
> (`imm_pores_regions.png` + `imm_pores.png`); region is primary via `--imm-detect` (default region).
> Defaults chosen empirically on this dataset (not the MATLAB 0.3/watershed route — tophat-first
> gave individual beads instead of ridge segments). CLI + GUI wired.

**Ask:** "de poriën die zichtbaar zijn in het immunolabeling plaatje laten vooral het
uitgescheiden materiaal rondom de porie zien, niet de porie zelf" → use the **centroid of
the pore region**, not a point-maximum. Also: "na de enhancement is er meer zichtbaar dan
alleen de poriën [het lijnenpatroon]... er moet vanuit de originele image gefocust worden
om alleen de poriën zichtbaar te maken." User supplied a MATLAB sketch (binarize →
`bwareaopen` → morphological close → `regionprops` → filter on circularity) and two example
figures (round blobs with red-cross centroids, numbered 1..211).

**Current state:** `porepair/detect.py::detect(mode="imm")` runs CLAHE `enhance()` implicitly
via the picker/report, and pore points come from `white_tophat` + `peak_local_max` — a single
pixel per pore, no region/size information. CLAHE is what makes the ridge lines pop, causing
false positives when this same channel is reused for blob segmentation.

**Change:**
1. Add a new function `detect_regions_imm(image_bgr, channel="red", ...)` in `detect.py` that:
   - Takes the **raw** channel (mild Gaussian blur only, no CLAHE) — CLAHE is for
     visualization/picking, not for this segmentation.
   - Binarizes (Otsu or adaptive threshold, configurable).
   - Removes small objects (`skimage.morphology.remove_small_objects`, `min_size` flag,
     equivalent to MATLAB `bwareaopen`).
   - Morphological closing (`disk` radius flag).
   - `skimage.measure.regionprops` on the labeled mask → area, perimeter, centroid.
   - Computes circularity as `4*pi*area/perimeter**2` (regionprops has no circularity field).
   - Filters by `circularity_thresh` (default from the MATLAB sketch: 0.3 — confirm with user).
   - Returns centroids **plus** per-region `area`/`equiv_radius`, since the region size is
     the natural "error margin" for matching (see WI-4).
2. Keep the existing top-hat detector as a fallback/comparison mode
   (`--imm-detect tophat|region`, default `region` once validated).
3. New diagnostic image `imm_pores_regions.png`: labeled blobs + red-cross centroids +
   numbering, matching the style of the two reference figures the user attached.

**Files:** `porepair/detect.py` (new function + circularity helper), `porepair/cli.py`
(new `--imm-detect`, `--imm-bin-thresh`, `--imm-min-area`, `--imm-close-radius`,
`--imm-circularity` flags), `porepair/app.py` (surface the same choice in the GUI).

**Acceptance:** running `detect` on the immuno image no longer flags ridge-line segments as
pores (visually check `imm_pores_regions.png` against the raw image); centroid count is in a
plausible range vs. the current 315-533 immuno counts seen in prior runs.

**Open decision:** circularity threshold and min-area default — start from the MATLAB values
(0.3, ~20-30 px) but these were tuned for a different image scale, so expect to re-tune
against this dataset.

---

## WI-2 — Second-stage registration refinement using pore positions
> **STATUS: DONE (2026-07-24).** `analyze.run(refine_with_pores=...)`: after the landmark fit, mutual-NN pore matches refit the transform (landmarks weighted x3 by duplication), up to 3 iters. Default OFF; CLI `--refine-pores`, GUI checkbox. Reports both residuals. On this dataset refinement RAISED the landmark residual (4.8->6.2 px, 181 pairs) so it stays off by default — the report shows the trade-off.

**Ask:** overlay looks good near the centre but drifts in areas with fewer landmark points;
use pore-position correspondences as a second refinement step on top of the landmark fit,
knowing immuno pores are an incomplete subset (not all pores are labeled).

**Current state:** `porepair/transform.py::Transform` fits once from the manual landmarks
only (`points.json`, 6-8 pairs). `analyze.py::_mutual_match` already does mutual-NN matching
of pore points post-transform — that machinery can be reused for refinement, it's just not
fed back into the transform.

**Change (in `analyze.py` / `transform.py`):**
1. Fit the initial transform `T0` from manual landmarks (unchanged).
2. Map OCT pores with `T0`, mutual-NN match against immuno pores within a radius
   (reuse `_mutual_match`, radius from WI-4's error margin).
3. Refit the transform using the **union** of manual landmarks + matched pore pairs
   (landmarks weighted higher, e.g. duplicate them k× in the least-squares fit, or use
   `scipy`'s weighted lstsq) — this is safe here because, unlike the earlier fully-automatic
   attempts documented in `decisions.md`, it's a *local* refinement seeded from an
   already-good manual fit, not a global blind search.
4. Optionally iterate steps 2-3 once more (classic ICP-style tightening), capped at 2-3
   rounds with a convergence check on residual change.
5. Add a `refine_with_pores: bool` flag to `analyze.run(...)` (default `False` until
   validated on this dataset, then flip to `True`).
6. Report **both** residuals (landmarks-only vs. after pore refinement) and the number of
   pore-pairs used for refinement, so the user can judge whether it actually helped.

**Files:** `porepair/transform.py` (weighted refit helper), `porepair/analyze.py`
(orchestration + new fields in `results.json`/`RESULTS.md`/report), `porepair/cli.py` /
`app.py` (new flag).

**Acceptance:** on the current dataset, mean residual after refinement ≤ residual from
landmarks alone, and the overlay visibly tightens in the low-landmark-density region the
user flagged — check this against `overlay.png` / the new AOI overlay (WI-3) before/after.

---

## WI-3 — Two overlay images: full ROI and AOI-only
> **STATUS: DONE (2026-07-24).** `_save_overlay(overlap=...)` also writes `overlay_aoi.png` (outside-AOI dimmed, AOI outline). Report shows full-ROI vs AOI side by side. Glossary notes AOI = eerlijk gebied.

**Ask:** clarify that "eerlijk gebied" = the AOI; produce a second overlay image that shows
**only** the AOI (ROI ∩ immuno-print), alongside the existing full-ROI overlay.

**Current state:** `analyze.py::_save_overlay` produces one `overlay.png` cropped to the
full mapped-ROI bounding box. The AOI/"fair region" mask (`overlap`) is already computed in
`run()` but only used for counts, not visualized as an overlay.

**Change:**
1. Rename "eerlijk gebied" → "AOI" consistently in labels/output (keep as an alias so old
   language in `decisions.md`/`glossary.md` still makes sense — this is a labeling change,
   not a metric change).
2. Add `_save_overlay(..., mask=None)` variant or a second call that masks everything
   outside `overlap` (dim/black outside AOI, or draw the AOI boundary as an outline on a
   copy of the full overlay) → write `overlay_aoi.png`.
3. Report/GUI: show both images side by side under the registration/AOI sections.

**Files:** `porepair/analyze.py` (`_save_overlay`), `porepair/report.py` (embed second
image), `glossary.md` (note the AOI = eerlijk gebied equivalence).

**Acceptance:** `overlay_aoi.png` exists, matches the AOI boundary already drawn in
`analysis.png`, and the report shows full-ROI vs. AOI-only side by side.

---

## WI-4 — Matching error margin (centroid-to-centroid) for immuno's "halo" signal
> **STATUS: DONE (2026-07-24).** `analyze.run(match_margin_k=0.5)`: radius = match_frac·NN +
> k·median(immuno equiv_radius). Mutual-NN unchanged. Radius decomposition reported in
> `results.json` (`match_radius_detail`) and the report. CLI `--match-margin-k`, GUI "match k" field.
> On this dataset: 11.7 px = 9.1 base + 2.6 margin → shared 142→180, imm-only 119→81.

**Ask:** since immuno signal shows excreted material around the pore rather than the pore
itself, allow a pixel error margin when matching; measure inter-pore distance from the
**centroid of the pore/pore-region** on both sides; keep the current "only mutually
corresponding pores" matching logic ("zoals het nu gedaan is").

**Current state:** matching (`_mutual_match`) already uses a radius (`match_frac × median
NN spacing`) and is mutual-NN — this part is confirmed correct and unchanged. What's missing
is: (a) immuno positions are currently point-maxima, not region centroids (fixed by WI-1),
and (b) the match radius should account for the pore-region size, not just a fixed fraction
of spacing.

**Change:**
1. Once WI-1 provides per-immuno-pore `equiv_radius`, add that as an extra additive term to
   the per-point match radius (e.g. `radius = match_frac * nn_imm + k * median(equiv_radius)`)
   so bigger "halo" regions get proportionally more slack — expose `k` as a CLI flag,
   default small (e.g. 0.5-1.0) and validate against `match_radius_sensitivity` (already
   reported).
2. No change to the mutual-NN matching algorithm itself.

**Files:** `porepair/analyze.py` (`run()`, radius computation).

**Acceptance:** `match_radius_sensitivity` in `results.json` still reported; matched count
at the chosen radius is documented against the sensitivity sweep, so the margin choice is
auditable, not implicit.

---

## WI-5 — Numbered pore maps + nearest-neighbour table (ID, coordinates, NN-ID, distance, angle)
> **STATUS: DONE (2026-07-24).** `analyze._nn_rows()` + `_save_numbered_map()`. CSVs
> `oct_nn.csv` / `imm_nn.csv` / `matched_nn.csv` with columns Porie_ID, Coordinates,
> Nearest_neighbour_ID, Distance_neighbour (µm), Angle_neighbour (deg). Numbered maps
> `oct_pores_numbered.png` / `imm_pores_numbered.png` / `matched_numbered.png`. Report has a
> WI-5 section. **Angle convention chosen:** atan2(dy,dx) deg, x-right/y-down, 0°=right,
> +=clockwise — CONFIRM against the docx example table (source docx not in repo).

**Ask:** an image-map with matching pores numbered, and a table with columns
`Porie_ID, Coordinates, Nearest_neighbour_ID, Distance_neighbour, Angle_neighbour` (per the
attached MATLAB-style example table and figures).

**Current state:** `matched_pairs.csv` has px/µm coordinates and pair distance, but no
per-pore nearest-neighbour angle, and no numbered visual map (only the green/magenta/yellow
`analysis.png` classification map).

**Change:**
1. New helper in `analyze.py`: for a point set, compute NN id/distance (reuse `cKDTree`,
   already available) plus NN **angle** in degrees (`np.degrees(np.arctan2(dy, dx))` —
   confirm angle convention against the MATLAB example numbers before finalizing, e.g.
   0°=+x axis, counter-clockwise, or clock-style like the sample table's negative values
   suggest atan2d(dy,dx) with y pointing down).
2. Build this table for OCT pores, immuno pores, and separately for the matched-pair subset
   (which is what "matchende poriën genummerd" asks for specifically).
3. New annotated images `oct_pores_numbered.png`, `imm_pores_numbered.png` (and a matched
   version) — pore ID label + centroid marker + dashed line to nearest neighbour, styled
   like the two reference figures in the docx.

**Files:** `porepair/analyze.py` (new `_nn_table()` + `_save_numbered_map()`), reused by
report.py and the Excel export (WI-6).

**Acceptance:** table columns exactly match the requested names; numbered map is visually
comparable to the two attached example figures.

---

## WI-6 — Excel export of all results
> **STATUS: DONE (2026-07-24).** `export_excel.build()` -> `results.xlsx` with sheets Summary, Transform, Config, Matched_Pairs, OCT_Pores, Immuno_Pores, Matched_NN. Added pandas+openpyxl to requirements.

**Ask:** an Excel table of all results so figures can be rebuilt/adjusted later.

**Current state:** only `matched_pairs.csv` + `results.json` (machine-oriented) + `RESULTS.md`
(prose summary). No single spreadsheet with everything.

**Change:** new `porepair/export_excel.py` (use `openpyxl` via `pandas.ExcelWriter`) writing
`results.xlsx` with one sheet per topic:
- `Summary` — the KPIs currently in `results.json` top level (counts, densities, transform
  params, ROI/AOI %, match radius).
- `Matched_Pairs` — current CSV content + NN angle from WI-5.
- `OCT_Pores` / `Immuno_Pores` — full per-pore tables from WI-5 (ID, coords, NN id/dist/angle,
  region area for immuno).
- `Transform` — landmark residuals, refinement residuals (WI-2), scale/rotation/shear.
- `Config` — every detection/matching/registration parameter actually used for this run
  (pulls from `meta.json` + the new flags), so the spreadsheet alone documents how it was
  produced.

**Files:** new `porepair/export_excel.py`, called from `analyze.run()`; add `openpyxl` to
`requirements.txt`.

**Acceptance:** `results.xlsx` opens in Excel with all five sheets populated and numeric
(not just text) so charts can be rebuilt from it directly.

---

## WI-7 — Reproducibility protocol document
> **STATUS: DONE (2026-07-24).** `protocol.build()` -> `protocol.docx` (python-docx), methods-section prose populated from the run's config/results. Added python-docx to requirements.

**Ask:** a separate, rewritable document (for eventual publication) describing: immuno image
optimization (contrast/enhancement/white-black balance), which transformations were applied
to reach the final overlay, and which calculations were performed — methods-section style,
not a dashboard.

**Current state:** `report.html` documents results but is a results dashboard, not a
methods write-up; `wiki/*.md` documents the pipeline for internal use but isn't meant to be
handed to a co-author for a paper.

**Change:** new `porepair/protocol.py::build_protocol(out_dir, results, meta, config) ->
protocol.docx` (or `.md`, see open decision) that renders a prose methods section, populated
from the actual run's parameters (not hard-coded), covering in order: image sources +
calibration, immuno preprocessing (WI-1's binarization/closing/circularity params, explicitly
noting CLAHE is used only for display, not detection), OCT pore detection, registration
(landmark count + WI-2 refinement step and its residual improvement), matching (radius +
margin logic from WI-4), and inter-pore-distance/NN-angle calculations (WI-5). Since it must
be "easily rewritable by the user for publication," a `.docx` (via the project's `docx`
skill / python-docx) is more useful than HTML — plain paragraphs, no embedded interactivity.

**Files:** new `porepair/protocol.py`, called at the end of `analyze.run()`, writes
`protocol.docx` into `out_dir` alongside `report.html`.

**Acceptance:** protocol reads as a standalone methods section (a colleague unfamiliar with
the code could reproduce the pipeline from it); every numeric claim in it is pulled from the
actual run's config/results, not restated from memory.

**Open decision:** confirm `.docx` vs. `.md` output — `.docx` matches "reworkable for
publication," `.md` is easier to keep in sync with the repo. Recommendation: `.docx`.

---

## WI-8 — Interactive zoom/rotate/pan viewer for the overlay image
> **STATUS: DONE (2026-07-24).** `overlay_viewer.build()` -> self-contained `overlay_viewer.html`: pan/zoom/rotate + cross-fade opacity between warped-OCT and immuno layers (+ layer toggles). CLI `view` subcommand; built at end of analyze.run.

**Ask:** a zoom-and-rotate tool for inspecting the registration overlay in detail (the
current `overlay.png`/`overlay_aoi.png` are static, cropped PNGs).

**Current state:** `porepair/picker.py` already implements exactly this pan/zoom/rotate
interaction (mouse-wheel zoom anchored at cursor, drag-to-pan, rotate slider/±90° buttons)
for the landmark-picking tool — that JS is reusable almost as-is, minus the click-to-place-
point logic.

**Change:** new `porepair/overlay_viewer.py`, structurally a sibling of `picker.py`:
- Single viewport (not two side-by-side like the picker) showing the registered
  composite — ideally as **separate toggleable layers** (OCT-warped, immuno, AOI-only crop
  from WI-3) with an opacity slider, rather than a single flattened PNG, so the user can
  fade between modalities while zoomed in.
- Same pan/zoom/rotate interaction model as `picker.py` (reuse the matrix/anchor-zoom code).
- Self-contained HTML (base64-embedded images), opens by double-click like `point_picker.html`.
- Generated automatically at the end of `analyze.run()` as `overlay_viewer.html`, and openable
  standalone via a new `python -m porepair view --out DIR` CLI command.

**Files:** new `porepair/overlay_viewer.py`, `porepair/cli.py` (new `view` subcommand),
`porepair/analyze.py` (call it at the end of `run()`), `porepair/app.py` (button to open it
after "Analyse + opslaan").

**Acceptance:** opening `overlay_viewer.html` lets the user zoom into any region of the
overlay at full native resolution and rotate, addressing the "details goed bekeken" ask
directly.

---

## Suggested build order

1. **WI-1** (immuno region detection) — everything downstream depends on better immuno
   pore positions.
2. **WI-5** (NN table + numbered maps) — small, self-contained, useful for validating WI-1
   visually before building more on top of it.
3. **WI-4** (match margin using region size) — small follow-on once WI-1 exists.
4. **WI-2** (pore-based registration refinement) — now matching is trustworthy enough to
   feed back into the transform.
5. **WI-3** (AOI-only overlay) — independent, can slot in anywhere, but do it before WI-8
   so the viewer has both layers to show.
6. **WI-8** (zoom/rotate overlay viewer) — needs WI-3's AOI crop as one of its layers.
7. **WI-6** (Excel export) — pulls together outputs from WI-1/2/4/5.
8. **WI-7** (protocol document) — last, since it describes the finished pipeline including
   all of the above.

## Open decisions to confirm before/while implementing

- WI-1: circularity threshold / min-area defaults (start from MATLAB's 0.3 / ~20-30 px,
  expect to re-tune).
- WI-2: default `refine_with_pores` on or off once validated; how many refinement iterations.
- WI-5: exact angle convention (match the sign convention implied by the example table).
- WI-7: `.docx` vs `.md` for the protocol document (recommendation: `.docx`).
- Whether WI-1's region-based immuno detection **replaces** the top-hat method outright or
  stays selectable — recommendation: make it default, keep top-hat as a `--imm-detect`
  fallback for comparison during validation.
