"""WI-6 — Excel export of all results to results.xlsx (one sheet per topic), so figures
can be rebuilt/adjusted later. Numeric where possible."""
import os
import pandas as pd


def _read_csv(path):
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def build(out_dir, results, meta):
    r = results
    ipd = r["interpore_distance_um"]
    mrd = r.get("match_radius_detail", {})
    t = r["transform"]

    def st(d, k):
        return d[k] if d else None

    summary = pd.DataFrame([
        ("OCT image", os.path.basename(r["images"]["oct"])),
        ("immuno image", os.path.basename(r["images"]["imm"])),
        ("ROI area (mm^2)", r["roi_mm2"]),
        ("ROI within immuno print (%)", r["roi_covered_by_print_pct"]),
        ("OCT pores (full ROI)", r["counts_full_roi"]["oct"]),
        ("immuno pores (full ROI)", r["counts_full_roi"]["imm"]),
        ("OCT pores (AOI)", r["counts_fair_region"]["oct"]),
        ("immuno pores (AOI)", r["counts_fair_region"]["imm"]),
        ("density OCT (/mm^2)", r["density_per_mm2"]["oct"]),
        ("density immuno (/mm^2)", r["density_per_mm2"]["imm"]),
        ("shared pores (AOI)", r["matching_fair_region"]["shared"]),
        ("OCT-only pores (AOI)", r["matching_fair_region"]["oct_only"]),
        ("immuno-only pores (AOI)", r["matching_fair_region"]["imm_only"]),
        ("match radius (px)", r["match_radius_px"]),
        ("inter-pore dist matched OCT (µm, median)", st(ipd.get("matched_oct"), "median")),
        ("inter-pore dist matched immuno (µm, median)", st(ipd.get("matched_imm"), "median")),
        ("inter-pore dist all OCT (µm, median)", st(ipd.get("all_oct"), "median")),
        ("inter-pore dist all immuno (µm, median)", st(ipd.get("all_imm"), "median")),
        ("matched-pair agreement (µm, median)", st(r.get("matched_pair_agreement_um"), "median")),
    ], columns=["Metric", "Value"])

    transform = pd.DataFrame([
        ("kind", t["kind"]),
        ("residual mean (px)", t["residual_mean_px"]),
        ("residual max (px)", t["residual_max_px"]),
        ("scale", t["scale"]),
        ("rotation (deg)", t["rotation_deg"]),
        ("axis angle (deg, 90=no shear)", t["axis_angle_deg"]),
        ("n landmarks", t["n_points"]),
        ("refined with pores", t.get("refined_with_pores")),
        ("residual landmarks-only (px)", t.get("residual_landmarks_only_px")),
        ("residual after refine (px)", t.get("residual_after_refine_px")),
        ("n pore pairs used", t.get("n_pore_pairs_used")),
    ], columns=["Parameter", "Value"])

    cal = r["calibration_um_per_px"]
    config = pd.DataFrame([
        ("oct_um_per_px_x", cal["x"]), ("oct_um_per_px_y", cal["y"]),
        ("oct_mm", "x".join(str(v) for v in cal["oct_mm"])),
        ("imm_detect", meta.get("imm_detect")),
        ("imm_circularity", meta.get("imm_circularity")),
        ("imm_min_area", meta.get("imm_min_area")),
        ("imm_tophat", meta.get("imm_tophat")),
        ("imm_channel", meta.get("imm_channel")),
        ("match_frac", mrd.get("match_frac")),
        ("match_margin_k", mrd.get("margin_k")),
        ("median_region_radius_px", mrd.get("median_region_radius_px")),
        ("nn_angle_convention", r.get("nn_angle_convention")),
    ], columns=["Parameter", "Value"])

    sheets = {
        "Summary": summary,
        "Transform": transform,
        "Config": config,
        "Matched_Pairs": _read_csv(os.path.join(out_dir, "matched_pairs.csv")),
        "OCT_Pores": _read_csv(os.path.join(out_dir, "oct_nn.csv")),
        "Immuno_Pores": _read_csv(os.path.join(out_dir, "imm_nn.csv")),
        "Matched_NN": _read_csv(os.path.join(out_dir, "matched_nn.csv")),
    }
    path = os.path.join(out_dir, "results.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in sheets.items():
            (df if not df.empty else pd.DataFrame({"(leeg)": []})).to_excel(xl, sheet_name=name, index=False)
    return path
