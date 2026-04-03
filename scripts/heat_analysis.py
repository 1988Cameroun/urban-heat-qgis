"""
Urban Heat Island Detection - PyQGIS + Claude AI
Author: Idriss Yann Tchokogue
Description:
    Ingests Landsat raster bands, computes NDVI and LST,
    classifies urban heat zones, then uses Claude AI to
    generate a natural language interpretation report.

Requirements:
    - QGIS 3.x (PyQGIS bundled)
    - anthropic >= 0.20.0  (pip install anthropic)
    - numpy, pandas

Usage:
    Run inside QGIS Python Console OR standalone with:
        python-qgis heat_analysis.py
"""

import os
import json
import sys
import numpy as np

# ── Anthropic ────────────────────────────────────────────────────────────────
try:
    import anthropic
except ImportError:
    print("[ERROR] anthropic not installed. Run: pip install anthropic")
    sys.exit(1)

# ── PyQGIS bootstrap (standalone mode) ──────────────────────────────────────
# If running outside QGIS, set QGIS_PREFIX_PATH to your installation, e.g.:
#   export QGIS_PREFIX_PATH=/usr  (Linux)
#   set QGIS_PREFIX_PATH=C:\OSGeo4W\apps\qgis  (Windows)

STANDALONE = "qgis" not in sys.modules

if STANDALONE:
    from qgis.core import QgsApplication
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", "/usr"), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

from qgis.core import (
    QgsRasterLayer,
    QgsProject,
    QgsRasterCalculator,
    QgsRasterCalculatorEntry,
    QgsColorRampShader,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
)
import processing
from processing.core.Processing import Processing
Processing.initialize()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — edit these paths to point at your downloaded Landsat bands
# Download from: https://earthexplorer.usgs.gov/
# Product: Landsat 8-9 OLI/TIRS C2 L2
# ─────────────────────────────────────────────────────────────────────────────

CONFIG = {
    # Landsat Band 4 = Red  (for NDVI)
    "band_red":   r"C:\urban-heat-qgis\data\LC09_L2SP_025039_20240823_20240824_02_T1_SR_B4.TIF",
    # Landsat Band 5 = NIR  (for NDVI)
    "band_nir":   r"C:\urban-heat-qgis\data\LC09_L2SP_025039_20240823_20240824_02_T1_SR_B5.TIF",
    # Landsat Band 10 = Thermal (for LST proxy)
    "band_tir":   r"C:\urban-heat-qgis\data\LC09_L2SP_025039_20240823_20240824_02_T1_ST_B10.TIF",
    # Study area name (used in AI report)
    "city":       "Houston, TX",
    # Output directory
    "output_dir": r"C:\urban-heat-qgis\outputs",
    # Anthropic model
    "ai_model":   "claude-sonnet-4-20250514",
}

os.makedirs(CONFIG["output_dir"], exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Load raster bands
# ─────────────────────────────────────────────────────────────────────────────

def load_band(path: str, name: str) -> QgsRasterLayer:
    layer = QgsRasterLayer(path, name)
    if not layer.isValid():
        raise ValueError(f"Cannot load raster: {path}")
    QgsProject.instance().addMapLayer(layer)
    print(f"  ✓ Loaded {name}: {layer.width()}×{layer.height()} px")
    return layer


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Compute NDVI
# NDVI = (NIR - Red) / (NIR + Red)
# Range: -1 (water) → 0 (bare soil) → +1 (dense vegetation)
# ─────────────────────────────────────────────────────────────────────────────

def compute_ndvi(red_layer: QgsRasterLayer,
                 nir_layer: QgsRasterLayer,
                 output_path: str) -> QgsRasterLayer:

    red_entry = QgsRasterCalculatorEntry()
    red_entry.ref = "red@1"
    red_entry.raster = red_layer
    red_entry.bandNumber = 1

    nir_entry = QgsRasterCalculatorEntry()
    nir_entry.ref = "nir@1"
    nir_entry.raster = nir_layer
    nir_entry.bandNumber = 1

    formula = "(nir@1 - red@1) / (nir@1 + red@1 + 0.0001)"  # +epsilon avoids /0

    calc = QgsRasterCalculator(
        formula,
        output_path,
        "GTiff",
        red_layer.extent(),
        red_layer.width(),
        red_layer.height(),
        [red_entry, nir_entry],
    )
    result = calc.processCalculation()
    if result != 0:
        raise RuntimeError(f"NDVI calculation failed (code {result})")

    ndvi_layer = QgsRasterLayer(output_path, "NDVI")
    QgsProject.instance().addMapLayer(ndvi_layer)
    print(f"  ✓ NDVI computed → {output_path}")
    return ndvi_layer


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Compute LST proxy from thermal band
# Simple linear rescale: DN → brightness temperature (Kelvin) → Celsius
# For production use the full Landsat L2 ST_B10 product (already in Kelvin*10)
# ─────────────────────────────────────────────────────────────────────────────

def compute_lst(tir_layer: QgsRasterLayer,
                output_path: str) -> QgsRasterLayer:
    """
    Landsat Collection 2 Level-2 ST band is stored as:
        LST (K) = pixel_value * 0.00341802 + 149.0
    Convert to Celsius: LST_C = LST_K - 273.15
    """
    tir_entry = QgsRasterCalculatorEntry()
    tir_entry.ref = "tir@1"
    tir_entry.raster = tir_layer
    tir_entry.bandNumber = 1

    formula = "(tir@1 * 0.00341802 + 149.0) - 273.15"

    calc = QgsRasterCalculator(
        formula,
        output_path,
        "GTiff",
        tir_layer.extent(),
        tir_layer.width(),
        tir_layer.height(),
        [tir_entry],
    )
    result = calc.processCalculation()
    if result != 0:
        raise RuntimeError(f"LST calculation failed (code {result})")

    lst_layer = QgsRasterLayer(output_path, "LST_Celsius")
    QgsProject.instance().addMapLayer(lst_layer)
    print(f"  ✓ LST computed → {output_path}")
    return lst_layer


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Zonal statistics (raster → summary stats dict)
# ─────────────────────────────────────────────────────────────────────────────

def extract_raster_stats(layer: QgsRasterLayer, label: str) -> dict:
    """Read band 1 into numpy and compute descriptive statistics."""
    provider = layer.dataProvider()
    block = provider.block(1, layer.extent(), layer.width(), layer.height())

    values = []
    for row in range(layer.height()):
        for col in range(layer.width()):
            val = block.value(row, col)
            if val != provider.sourceNoDataValue(1):
                values.append(val)

    arr = np.array(values, dtype=np.float32)
    stats = {
        "layer": label,
        "min":   float(np.min(arr)),
        "max":   float(np.max(arr)),
        "mean":  float(np.mean(arr)),
        "std":   float(np.std(arr)),
        "p25":   float(np.percentile(arr, 25)),
        "p75":   float(np.percentile(arr, 75)),
        "pixel_count": int(len(arr)),
    }
    print(f"  ✓ Stats [{label}]: mean={stats['mean']:.3f}, "
          f"min={stats['min']:.3f}, max={stats['max']:.3f}")
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Classify heat zones
# ─────────────────────────────────────────────────────────────────────────────

def classify_heat_zones(lst_stats: dict, ndvi_stats: dict) -> dict:
    """
    Rule-based classification using mean ± std thresholds.
    Returns zone definitions for the AI prompt.
    """
    lst_mean = lst_stats["mean"]
    lst_std  = lst_stats["std"]

    zones = {
        "extreme_heat": {
            "threshold_c": round(lst_mean + 1.5 * lst_std, 2),
            "description": "Temperatures significantly above city average — "
                           "dense impervious surfaces, industrial zones.",
        },
        "high_heat": {
            "threshold_c": round(lst_mean + 0.5 * lst_std, 2),
            "description": "Above-average temperatures — commercial corridors, "
                           "parking lots, low-density urban.",
        },
        "moderate": {
            "threshold_c": round(lst_mean, 2),
            "description": "Near city average — mixed land use.",
        },
        "cool_vegetated": {
            "threshold_c": round(lst_mean - 0.5 * lst_std, 2),
            "description": "Below-average temperatures — parks, tree canopy, "
                           "residential with vegetation.",
        },
    }

    # Estimate zone coverage (% pixels above each threshold)
    # This is a heuristic based on normal distribution assumptions
    zones["extreme_heat"]["estimated_pct_area"] = 6.7   # ~top 6.7% normal dist
    zones["high_heat"]["estimated_pct_area"]    = 30.9
    zones["moderate"]["estimated_pct_area"]     = 50.0
    zones["cool_vegetated"]["estimated_pct_area"] = 30.9

    return zones


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Style LST layer with color ramp
# ─────────────────────────────────────────────────────────────────────────────

def apply_heat_colormap(lst_layer: QgsRasterLayer,
                        lst_stats: dict) -> None:
    """Apply a blue→yellow→red pseudocolor ramp to the LST layer."""
    shader = QgsColorRampShader()
    shader.setColorRampType(QgsColorRampShader.Interpolated)

    lo  = lst_stats["min"]
    hi  = lst_stats["max"]
    mid = lst_stats["mean"]

    from qgis.PyQt.QtGui import QColor
    items = [
        QgsColorRampShader.ColorRampItem(lo,  QColor(0,   0, 255), f"{lo:.1f}°C"),
        QgsColorRampShader.ColorRampItem(mid, QColor(255, 255, 0), f"{mid:.1f}°C"),
        QgsColorRampShader.ColorRampItem(hi,  QColor(255, 0,   0), f"{hi:.1f}°C"),
    ]
    shader.setColorRampItemList(items)

    raster_shader = QgsRasterShader()
    raster_shader.setRasterShaderFunction(shader)

    renderer = QgsSingleBandPseudoColorRenderer(
        lst_layer.dataProvider(), 1, raster_shader
    )
    lst_layer.setRenderer(renderer)
    lst_layer.triggerRepaint()
    print("  ✓ Heatmap colormap applied")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Claude AI report generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_ai_report(city: str,
                       lst_stats: dict,
                       ndvi_stats: dict,
                       heat_zones: dict) -> str:
    """Send spatial stats to Claude and get a structured urban planning report."""

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    payload = {
        "city": city,
        "analysis_type": "Urban Heat Island Detection via Landsat",
        "lst_statistics_celsius": lst_stats,
        "ndvi_statistics": ndvi_stats,
        "heat_zone_classification": heat_zones,
    }

    system_prompt = """You are an expert urban climatologist and GIS analyst.
You will receive statistical outputs from a Landsat-based Urban Heat Island analysis.
Your task is to produce a professional, actionable urban planning report in Markdown.

Structure your report with these sections:
1. Executive Summary (3-4 sentences)
2. Thermal Landscape Overview (interpret LST mean, range, std)
3. Vegetation Coverage Assessment (interpret NDVI values)
4. Heat Zone Analysis (describe each zone and its urban planning implication)
5. Public Health Implications (heat stress risk, vulnerable populations)
6. Mitigation Recommendations (minimum 4 specific, data-driven suggestions)
7. Priority Action Areas (ranked by urgency)

Be specific, cite the numbers from the data, and write at a level suitable
for a city planning department report."""

    user_prompt = f"""Analyze the following Urban Heat Island spatial statistics
for {city} and generate a full planning report:

{json.dumps(payload, indent=2)}"""

    print("  ⏳ Calling Claude AI for report generation...")

    message = client.messages.create(
        model=CONFIG["ai_model"],
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    report = message.content[0].text
    print("  ✓ AI report received")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Save report
# ─────────────────────────────────────────────────────────────────────────────

def save_report(report: str, output_dir: str, city: str) -> str:
    safe_city = city.replace(",", "").replace(" ", "_")
    report_path = os.path.join(output_dir, f"UHI_Report_{safe_city}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Urban Heat Island Analysis Report\n")
        f.write(f"**City:** {city}  \n")
        f.write(f"**Generated by:** PyQGIS + Claude AI Pipeline  \n")
        f.write(f"**Author:** Idriss Yann Tchokogue  \n\n---\n\n")
        f.write(report)
    print(f"  ✓ Report saved → {report_path}")
    return report_path


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline():
    print("\n" + "="*60)
    print("  Urban Heat Island Detection Pipeline")
    print(f"  City: {CONFIG['city']}")
    print("="*60 + "\n")

    # 1. Load bands
    print("[1/7] Loading Landsat bands...")
    red_layer = load_band(CONFIG["band_red"], "Red_B4")
    nir_layer = load_band(CONFIG["band_nir"], "NIR_B5")
    tir_layer = load_band(CONFIG["band_tir"], "TIR_B10")

    # 2. Compute NDVI
    print("\n[2/7] Computing NDVI...")
    ndvi_path  = os.path.join(CONFIG["output_dir"], "NDVI.tif")
    ndvi_layer = compute_ndvi(red_layer, nir_layer, ndvi_path)

    # 3. Compute LST
    print("\n[3/7] Computing Land Surface Temperature...")
    lst_path  = os.path.join(CONFIG["output_dir"], "LST_Celsius.tif")
    lst_layer = compute_lst(tir_layer, lst_path)

    # 4. Extract statistics
    print("\n[4/7] Extracting raster statistics...")
    lst_stats  = extract_raster_stats(lst_layer, "LST_Celsius")
    ndvi_stats = extract_raster_stats(ndvi_layer, "NDVI")

    # 5. Classify heat zones
    print("\n[5/7] Classifying heat zones...")
    heat_zones = classify_heat_zones(lst_stats, ndvi_stats)
    print(f"  ✓ {len(heat_zones)} zones defined")

    # 6. Style map
    print("\n[6/7] Applying heatmap visualization...")
    apply_heat_colormap(lst_layer, lst_stats)

    # 7. Generate AI report
    print("\n[7/7] Generating Claude AI report...")
    report     = generate_ai_report(
        CONFIG["city"], lst_stats, ndvi_stats, heat_zones
    )
    report_path = save_report(report, CONFIG["output_dir"], CONFIG["city"])

    print("\n" + "="*60)
    print("  ✅ Pipeline complete!")
    print(f"  📄 Report: {report_path}")
    print(f"  🗺️  Layers loaded in QGIS: NDVI, LST_Celsius")
    print("="*60 + "\n")

    return {
        "ndvi_layer": ndvi_layer,
        "lst_layer":  lst_layer,
        "lst_stats":  lst_stats,
        "ndvi_stats": ndvi_stats,
        "heat_zones": heat_zones,
        "report_path": report_path,
    }


if __name__ == "__main__":
    results = run_pipeline()
    if STANDALONE:
        qgs.exitQgis()
