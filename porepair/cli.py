"""Command-line interface for porepair.

  python -m porepair detect  --oct OCT.jpg --imm IMM.jpg --out DIR [detection opts]
  python -m porepair pick    --out DIR                      # writes DIR/point_picker.html
  python -m porepair analyze --out DIR --points points.json --oct-mm 10x10 [--transform affine]

Typical session: detect -> open DIR/point_picker.html, click pairs, export points.json
-> analyze. Results land in DIR (RESULTS.md, results.json, analysis.png, overlay.png, csv).
"""
import argparse
import csv
import json
import os
import cv2
import numpy as np

from . import detect as D
from . import analyze as A
from .picker import build_picker


def _parse_mm(s):
    a, b = s.lower().split("x")
    return float(a), float(b)


def cmd_detect(args):
    os.makedirs(args.out, exist_ok=True)
    oct_bgr = cv2.imread(args.oct)
    imm_bgr = cv2.imread(args.imm)
    if oct_bgr is None or imm_bgr is None:
        raise SystemExit("could not read one of the images")

    o = D.detect(oct_bgr, mode="oct", tophat=args.oct_tophat, min_dist=args.min_dist,
                 thr=args.oct_thr)
    # WI-G: optional user-selected region mask (nonzero = detect here). Else print body.
    region_mask = None
    if args.imm_region:
        rm = cv2.imread(args.imm_region, cv2.IMREAD_GRAYSCALE)
        if rm is None:
            raise SystemExit(f"could not read region mask {args.imm_region}")
        if rm.shape != imm_bgr.shape[:2]:
            rm = cv2.resize(rm, (imm_bgr.shape[1], imm_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
        region_mask = (rm > 0).astype(np.uint8)
        cv2.imwrite(os.path.join(args.out, "imm_region_mask.png"), region_mask * 255)

    # immuno: run BOTH detectors, save both images; primary (feeds analysis) = --imm-detect
    i_top = D.detect(imm_bgr, mode="imm", channel=args.imm_channel, tophat=args.imm_tophat,
                     min_dist=args.min_dist, thr=args.imm_thr)
    i_reg = D.detect_regions_imm(imm_bgr, channel=args.imm_channel, region_mask=region_mask,
                                 min_area_frac=args.imm_min_area_frac, max_area_frac=args.imm_max_area_frac,
                                 circularity_thresh=args.imm_circularity, solidity_thresh=args.imm_solidity,
                                 max_eccentricity=args.imm_eccentricity, merged_blobs=args.merged_blobs,
                                 bin_method=args.imm_bin, bin_thresh=args.imm_bin_thresh,
                                 close_radius=args.imm_close)
    primary = i_reg if args.imm_detect == "region" else i_top
    reasons = {}
    for r in i_reg["rejections"]:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    print(f"OCT: {len(o['points'])} pores (thr={o['thr']:.1f})")
    print(f"IMM region: {len(i_reg['points'])} pores (rejected {len(i_reg['rejections'])}: {reasons}) "
          f"· IMM top-hat: {len(i_top['points'])} · primary = {args.imm_detect}")

    np.save(os.path.join(args.out, "oct_pts.npy"), o["points"])
    np.save(os.path.join(args.out, "oct_area.npy"), o.get("area", np.zeros(len(o["points"]))))
    np.save(os.path.join(args.out, "imm_pts.npy"), primary["points"])
    np.save(os.path.join(args.out, "imm_pts_region.npy"), i_reg["points"])
    np.save(os.path.join(args.out, "imm_pts_tophat.npy"), i_top["points"])
    np.save(os.path.join(args.out, "imm_equiv_radius.npy"), i_reg["equiv_radius"])
    np.save(os.path.join(args.out, "oct_valid.npy"), o["valid"])
    np.save(os.path.join(args.out, "imm_valid.npy"), primary["valid"])
    cv2.imwrite(os.path.join(args.out, "oct_enh.png"), D.enhance(o["gray"]))
    cv2.imwrite(os.path.join(args.out, "imm_enh.png"), D.enhance(i_top["gray"]))
    cv2.imwrite(os.path.join(args.out, "imm_optimized.png"), i_reg["optimized"])
    cv2.imwrite(os.path.join(args.out, "oct_pores.png"), D.draw(o["gray"], o["points"]))
    cv2.imwrite(os.path.join(args.out, "imm_pores.png"), D.draw(i_top["gray"], i_top["points"], (0, 255, 0)))
    cv2.imwrite(os.path.join(args.out, "imm_pores_regions.png"), D.draw_regions(i_reg["gray"], i_reg, on_optimized=True))
    cv2.imwrite(os.path.join(args.out, "imm_rejected.png"), D.draw_rejections(i_reg))
    with open(os.path.join(args.out, "imm_rejected.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["x_px", "y_px", "area_px", "reason"])
        for r in i_reg["rejections"]:
            w.writerow([f"{r['x']:.1f}", f"{r['y']:.1f}", f"{r['area']:.0f}", r["reason"]])
    json.dump({"oct": os.path.abspath(args.oct), "imm": os.path.abspath(args.imm),
               "imm_channel": args.imm_channel, "imm_detect": args.imm_detect,
               "oct_thr": o["thr"], "imm_region_n": len(i_reg["points"]),
               "imm_tophat_n": len(i_top["points"]), "imm_rejected": reasons,
               "imm_region_mask": bool(args.imm_region), "imm_params": i_reg["params"]},
              open(os.path.join(args.out, "meta.json"), "w"), indent=2)
    # also (re)build the landmark picker and the immuno curator (WI-E) so they are ready
    build_picker(D.enhance(o["gray"]), D.enhance(i_top["gray"]),
                 os.path.join(args.out, "point_picker.html"),
                 os.path.basename(args.oct), os.path.basename(args.imm))
    from . import imm_curator
    imm_curator.build(args.out, os.path.basename(args.imm))
    print(f"wrote pores/masks/meta, point_picker.html and imm_curator.html to {args.out}")


def cmd_pick(args):
    oe = cv2.imread(os.path.join(args.out, "oct_enh.png"), cv2.IMREAD_GRAYSCALE)
    ie = cv2.imread(os.path.join(args.out, "imm_enh.png"), cv2.IMREAD_GRAYSCALE)
    if oe is None or ie is None:
        raise SystemExit("run 'detect' first (need oct_enh.png / imm_enh.png)")
    meta = json.load(open(os.path.join(args.out, "meta.json")))
    p = build_picker(oe, ie, os.path.join(args.out, "point_picker.html"),
                     os.path.basename(meta["oct"]), os.path.basename(meta["imm"]))
    print(f"wrote {p} — open it, click 4-8 pairs, export points.json")


def cmd_analyze(args):
    res = A.run(args.out, args.points, oct_mm=_parse_mm(args.oct_mm),
                transform_kind=args.transform, match_frac=args.match_frac,
                match_margin_k=args.match_margin_k, refine_with_pores=args.refine_pores,
                imm_points_path=args.imm_points, match_method=args.match_method,
                match_thresh=args.match_thresh)
    t = res["transform"]
    print(f"transform {t['kind']}: residual {t['residual_mean_px']:.1f}px mean "
          f"(max {t['residual_max_px']:.1f}), scale {t['scale']:.3f}, rot {t['rotation_deg']:.1f}")
    print(f"counts full ROI  OCT={res['counts_full_roi']['oct']} IMM={res['counts_full_roi']['imm']}")
    fm = res["matching_fair_region"]
    print(f"fair region: shared={fm['shared']} oct-only={fm['oct_only']} imm-only={fm['imm_only']}")
    mo = res["interpore_distance_um"]["matched_oct"]
    print(f"inter-pore distance matched pores (OCT): median={mo['median']:.0f} um")
    print(f"wrote report.html + RESULTS.md, results.json, analysis.png, overlay.png, matched_pairs.csv in {args.out}")
    print(f"open the report:  {res.get('report_html')}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="porepair", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="detect pores in both images")
    d.add_argument("--oct", required=True); d.add_argument("--imm", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--imm-channel", default="red", choices=["red", "green", "blue"])
    d.add_argument("--imm-detect", default="region", choices=["region", "tophat"],
                   help="which immuno detector feeds the analysis (both are saved)")
    d.add_argument("--imm-region", default=None,
                   help="WI-G: mask image (nonzero=detect here) restricting immuno detection to a selected area")
    d.add_argument("--merged-blobs", default="split", choices=["split", "reject"],
                   help="WI-C: fused blobs -> split (watershed) or reject")
    d.add_argument("--oct-tophat", type=int, default=9)
    d.add_argument("--imm-tophat", type=int, default=11, help="top-hat detector radius (comparison detector)")
    d.add_argument("--imm-min-area-frac", type=float, default=0.15, help="region: min blob area / median")
    d.add_argument("--imm-max-area-frac", type=float, default=6.0, help="region: max blob area / median")
    d.add_argument("--imm-circularity", type=float, default=0.15, help="region: min circularity")
    d.add_argument("--imm-solidity", type=float, default=0.40, help="region: min solidity")
    d.add_argument("--imm-eccentricity", type=float, default=0.97, help="region: max eccentricity")
    d.add_argument("--imm-bin", default="otsu", choices=["otsu", "fixed"],
                   help="binarisation: otsu (robust) or fixed threshold (MATLAB, after stretch)")
    d.add_argument("--imm-bin-thresh", type=int, default=200, help="fixed binarisation threshold (0-255)")
    d.add_argument("--imm-close", type=int, default=0, help="morphological close radius (MATLAB used 2)")
    d.add_argument("--min-dist", type=int, default=14)
    d.add_argument("--oct-thr", type=float, default=None, help="fixed threshold (default: adaptive)")
    d.add_argument("--imm-thr", type=float, default=None)
    d.set_defaults(func=cmd_detect)

    k = sub.add_parser("pick", help="(re)generate the HTML landmark picker")
    k.add_argument("--out", required=True)
    k.set_defaults(func=cmd_pick)

    a = sub.add_parser("analyze", help="register from landmarks and run the analysis")
    a.add_argument("--out", required=True)
    a.add_argument("--points", required=True, help="points.json exported by the picker")
    a.add_argument("--oct-mm", default="10x10", help="physical size of the OCT image, e.g. 10x10")
    a.add_argument("--transform", default="affine", choices=["affine", "similarity", "tps"])
    a.add_argument("--match-frac", type=float, default=0.45, help="match radius as fraction of pore spacing")
    a.add_argument("--match-margin-k", type=float, default=0.5,
                   help="extra match radius = k x median immuno pore-region radius (WI-4 halo margin)")
    a.add_argument("--refine-pores", action="store_true",
                   help="refine the transform using matched pore correspondences (WI-2)")
    a.add_argument("--imm-points", default=None,
                   help="WI-E: curated immuno points JSON (from imm_curator.html) to use instead of auto-detection")
    a.add_argument("--match-method", default="mutual-nn", choices=["mutual-nn", "matlab"],
                   help="mutual-nn (position + halo margin) or matlab (normalised position+area, OCT_FM)")
    a.add_argument("--match-thresh", type=float, default=0.1,
                   help="matlab matching: combined normalised-distance threshold (OCT_FM default 0.1)")
    a.set_defaults(func=cmd_analyze)

    g = sub.add_parser("gui", help="launch the desktop app (select images, pick points, save)")
    g.set_defaults(func=lambda _a: __import__("porepair.app", fromlist=["main"]).main())

    v = sub.add_parser("view", help="(re)build the interactive overlay viewer HTML for a run")
    v.add_argument("--out", required=True)
    v.set_defaults(func=lambda a: print("wrote",
                   __import__("porepair.overlay_viewer", fromlist=["build"]).build(a.out)))

    c = sub.add_parser("curate", help="(re)build the immuno curation HTML (WI-E) for a run")
    c.add_argument("--out", required=True)
    c.set_defaults(func=lambda a: print("wrote",
                   __import__("porepair.imm_curator", fromlist=["build"]).build(a.out)))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
