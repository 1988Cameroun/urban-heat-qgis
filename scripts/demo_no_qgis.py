"""
Urban Heat Island - DEMO MODE (no Landsat data required)
─────────────────────────────────────────────────────────
Generates synthetic raster stats that mimic real Houston Landsat output,
then calls Claude AI to produce a full planning report.

Use this to:
  1. Test the Claude integration immediately
  2. Show Handshake AI reviewers the AI report output
  3. Verify your ANTHROPIC_API_KEY works

Usage:
    pip install anthropic numpy
    export ANTHROPIC_API_KEY=sk-ant-...
    python demo_no_qgis.py
"""

import os
import json
import numpy as np
import anthropic

# ─── Synthetic Houston Landsat stats (realistic values) ──────────────────────
# Based on published Houston UHI studies (summer, July)

LST_STATS = {
    "layer": "LST_Celsius",
    "min":   28.4,
    "max":   58.7,
    "mean":  41.2,
    "std":    5.8,
    "p25":   37.1,
    "p75":   45.6,
    "pixel_count": 2_847_300,
}

NDVI_STATS = {
    "layer": "NDVI",
    "min":  -0.12,
    "max":   0.71,
    "mean":  0.23,
    "std":   0.18,
    "p25":   0.09,
    "p75":   0.38,
    "pixel_count": 2_847_300,
}

HEAT_ZONES = {
    "extreme_heat": {
        "threshold_c": round(LST_STATS["mean"] + 1.5 * LST_STATS["std"], 2),
        "description": "Dense impervious surfaces — refineries, port district, downtown core.",
        "estimated_pct_area": 6.7,
    },
    "high_heat": {
        "threshold_c": round(LST_STATS["mean"] + 0.5 * LST_STATS["std"], 2),
        "description": "Commercial corridors, strip malls, highway interchanges.",
        "estimated_pct_area": 30.9,
    },
    "moderate": {
        "threshold_c": round(LST_STATS["mean"], 2),
        "description": "Mixed residential/commercial land use.",
        "estimated_pct_area": 50.0,
    },
    "cool_vegetated": {
        "threshold_c": round(LST_STATS["mean"] - 0.5 * LST_STATS["std"], 2),
        "description": "Memorial Park, Brays Bayou greenway, tree-canopied suburbs.",
        "estimated_pct_area": 30.9,
    },
}

CITY = "Houston, TX"
AI_MODEL = "claude-sonnet-4-20250514"
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_ai_report() -> str:
    client = anthropic.Anthropic()

    payload = {
        "city": CITY,
        "analysis_type": "Urban Heat Island Detection via Landsat 9 (Demo)",
        "lst_statistics_celsius": LST_STATS,
        "ndvi_statistics": NDVI_STATS,
        "heat_zone_classification": HEAT_ZONES,
    }

    system_prompt = """You are an expert urban climatologist and GIS analyst.
You will receive statistical outputs from a Landsat-based Urban Heat Island analysis.
Produce a professional, actionable urban planning report in Markdown.

Sections required:
1. Executive Summary (3-4 sentences)
2. Thermal Landscape Overview (interpret LST mean, range, std)
3. Vegetation Coverage Assessment (interpret NDVI values)
4. Heat Zone Analysis (each zone with planning implication)
5. Public Health Implications
6. Mitigation Recommendations (4+ specific, data-driven)
7. Priority Action Areas (ranked by urgency)

Cite the actual numbers. Write at city planning department level."""

    user_prompt = (
        f"Analyze this Urban Heat Island data for {CITY} "
        f"and generate a full planning report:\n\n"
        f"{json.dumps(payload, indent=2)}"
    )

    print("⏳  Calling Claude AI...")
    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def save_report(report: str) -> str:
    path = os.path.join(OUTPUT_DIR, "UHI_Report_Houston_TX_DEMO.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Urban Heat Island Analysis Report (Demo)\n")
        f.write(f"**City:** {CITY}  \n")
        f.write("**Pipeline:** PyQGIS + Claude AI  \n")
        f.write("**Author:** Idriss Yann Tchokogue  \n\n---\n\n")
        f.write(report)
    return path


def print_stats_summary():
    print("\n📊  Synthetic Raster Statistics (Houston July baseline)")
    print(f"   LST  → mean {LST_STATS['mean']}°C  "
          f"| range [{LST_STATS['min']}–{LST_STATS['max']}°C]  "
          f"| σ {LST_STATS['std']}")
    print(f"   NDVI → mean {NDVI_STATS['mean']}  "
          f"| range [{NDVI_STATS['min']}–{NDVI_STATS['max']}]  "
          f"| σ {NDVI_STATS['std']}")
    print("\n🌡️   Heat Zone Thresholds")
    for zone, data in HEAT_ZONES.items():
        print(f"   {zone:<20} ≥ {data['threshold_c']}°C  "
              f"(~{data['estimated_pct_area']}% of area)")


if __name__ == "__main__":
    print("=" * 60)
    print("  UHI Detection — DEMO MODE")
    print(f"  City: {CITY}")
    print("=" * 60)

    print_stats_summary()

    report  = generate_ai_report()
    path    = save_report(report)

    print(f"\n✅  Done! Report saved → {path}")
    print("\n── Report Preview (first 800 chars) ──────────────────────")
    print(report[:800] + "…\n")
