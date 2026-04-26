Urban Heat Island Detection Dashboard
PyQGIS + Claude AI — Houston, TX


import streamlit as st
import anthropic
import os
import json

st.set_page_config(
    page_title="Urban Heat Island Detection",
    page_icon="🌡️",
    layout="wide",
)



with st.sidebar:
    st.title("🌡️ UHI Detection")
    st.caption("PyQGIS + Claude AI")

    st.divider()

    page = st.radio(
        "Navigate",
        [" Heat Map", " Zone Analysis", " AI Report", " Raw Bands"],
        label_visibility="collapsed",
    )

    st.divider()

    st.subheader("Settings")
    data_mode = st.selectbox(
        "Data source",
        ["Demo baseline (no download needed)", "Real Landsat 9 data"],
    )

    extreme_threshold = st.slider(
        "Extreme heat threshold (°C)", min_value=40, max_value=60, value=50
    )

    run = st.button("▶ Run pipeline", use_container_width=True, type="primary")



DEMO_STATS = {
    "city": "Houston, TX",
    "lst_min": 28.4,
    "lst_max": 58.7,
    "lst_mean": 41.2,
    "ndvi_mean": 0.23,
    "zones": {
        "Extreme Heat":    {"threshold": "≥ 49.9°C", "coverage": 6.7},
        "High Heat":       {"threshold": "≥ 44.1°C", "coverage": 30.9},
        "Moderate":        {"threshold": "≥ 41.2°C", "coverage": 50.0},
        "Cool/Vegetated":  {"threshold": "< 38.3°C", "coverage": 12.4},
    },
    "heatmap_path": "outputs/houston_heatmap.png",   # swap for real output path
}

ZONE_COLORS = {
    "Extreme Heat":   "#D85A30",
    "High Heat":      "#EF9F27",
    "Moderate":       "#FAC775",
    "Cool/Vegetated": "#5DCAA5",
}



def generate_ai_report(stats: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return (
            " Set the `ANTHROPIC_API_KEY` environment variable to generate a live report.\n\n"
            "**Example (from your README):**\n\n"
            "```\nexport ANTHROPIC_API_KEY=sk-ant-...\n```"
        )

    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""
You are an urban planning expert. Analyse this Urban Heat Island data for {stats['city']} 
and write a structured Markdown report.

Data:
{json.dumps(stats, indent=2)}

Include:
1. Executive Summary (2-3 sentences)
2. Heat Zone Analysis (interpret the 4 zones)
3. NDVI / Vegetation Correlation
4. Top 5 Mitigation Recommendations (specific to Houston geography)
5. Data Quality Notes

Be concise, technical, and actionable.
"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text




if "stats" not in st.session_state:
    st.session_state.stats = DEMO_STATS
if "report" not in st.session_state:
    st.session_state.report = None

if run:
    with st.spinner("Running pipeline..."):
        if data_mode.startswith("Real"):
            st.warning(
                "Real Landsat mode: make sure your TIF files are in `data/` "
                "and QGIS_PREFIX_PATH is set. Falling back to demo stats for now."
            )
        st.session_state.stats = DEMO_STATS   # replace with run_pipeline() call
        st.session_state.report = None        # reset cached report

stats = st.session_state.stats



if page == " Heat Map":
    st.header("Houston thermal heatmap")
    st.caption(f"Source: USGS Landsat 9 OLI/TIRS C2 L2 · City: {stats['city']}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Max LST", f"{stats['lst_max']}°C", help="Land surface temperature max")
    col2.metric("City mean", f"{stats['lst_mean']}°C")
    col3.metric("Min LST", f"{stats['lst_min']}°C")
    col4.metric("NDVI mean", f"{stats['ndvi_mean']:.2f}", help="Vegetation health index")

    import pathlib
    heatmap = pathlib.Path(stats["heatmap_path"])
    if heatmap.exists():
        st.image(str(heatmap), caption="QGIS-rendered LST heatmap", use_container_width=True)
    else:
        st.info(
            f"Heatmap not found at `{stats['heatmap_path']}`. "
            "Run the full pipeline with real Landsat data to generate it, "
            "or place your PNG at that path."
        )



elif page == " Zone Analysis":
    st.header("Heat zone breakdown")

    import pandas as pd
    import plotly.express as px

    rows = [
        {
            "Zone": name,
            "Threshold": info["threshold"],
            "Coverage (%)": info["coverage"],
            "Color": ZONE_COLORS[name],
        }
        for name, info in stats["zones"].items()
    ]
    df = pd.DataFrame(rows)

    col_a, col_b = st.columns([1, 1])

    with col_a:
        st.subheader("Coverage by zone")
        fig = px.bar(
            df,
            x="Zone",
            y="Coverage (%)",
            color="Zone",
            color_discrete_map=ZONE_COLORS,
            text="Coverage (%)",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(showlegend=False, margin=dict(t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Zone thresholds")
        st.dataframe(
            df[["Zone", "Threshold", "Coverage (%)"]].style.format({"Coverage (%)": "{:.1f}%"}),
            hide_index=True,
            use_container_width=True,
        )

    st.divider()
    st.subheader("Extreme heat threshold explorer")
    user_thresh = st.slider(
        "Adjust extreme heat threshold", 40, 60, extreme_threshold, key="zone_slider"
    )
    affected = sum(
        v["coverage"] for k, v in stats["zones"].items()
        if float(v["threshold"].replace("≥ ", "").replace("°C", "").replace("< ", "")) >= user_thresh
        or "Extreme" in k
    )
    st.info(
        f"At **{user_thresh}°C**, approximately **{stats['zones']['Extreme Heat']['coverage']:.1f}%** "
        "of the study area qualifies as extreme heat. Adjust the slider to explore sensitivity."
    )



elif page == " AI Report":
    st.header("AI-generated urban planning report")
    st.caption("Powered by Anthropic Claude")

    if st.session_state.report is None:
        if st.button("Generate report with Claude", type="primary"):
            with st.spinner("Claude is writing your report..."):
                st.session_state.report = generate_ai_report(stats)

    if st.session_state.report:
        st.markdown(st.session_state.report)
        st.download_button(
            "⬇ Download as Markdown",
            data=st.session_state.report,
            file_name="UHI_Report_Houston_TX.md",
            mime="text/markdown",
        )



elif page == " Raw Bands":
    st.header("Raw Landsat 9 band inputs")
    st.caption("Bands 4 (Red), 5 (NIR), 10 (Thermal) — place TIF files in `data/`")

    import pathlib

    band_map = {
        "Band 4 — Red":      "data/LC09_B4.TIF",
        "Band 5 — NIR":      "data/LC09_B5.TIF",
        "Band 10 — Thermal": "data/LC09_B10.TIF",
    }

    cols = st.columns(3)
    for col, (label, path) in zip(cols, band_map.items()):
        with col:
            st.subheader(label)
            p = pathlib.Path(path)
            if p.exists():
                st.success(f"`{path}` found ✓")
            else:
                st.warning(f"`{path}` not found")
                st.caption(
                    "Download from [earthexplorer.usgs.gov](https://earthexplorer.usgs.gov) "
                    "→ Landsat 9 OLI/TIRS C2 L2"
                )

    st.divider()
    st.subheader("How to download Landsat data")
    st.markdown(
        """
1. Go to [earthexplorer.usgs.gov](https://earthexplorer.usgs.gov)
2. Draw an AOI over Houston
3. Select **Landsat 9 OLI/TIRS C2 L2**
4. Download **Bands 4, 5, and 10**
5. Place files in the `data/` folder
6. Return to **Heat Map** and click **Run pipeline**
        """
    )
