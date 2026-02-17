# roaming_predictive.py
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

try:
    import joblib
except Exception:
    joblib = None
import pickle

# =========================================================
# FOLDER (MATCH YOUR STRUCTURE)
# =========================================================
MODELS_DIR = Path("roaming_models")

MONTHLY_CSV = MODELS_DIR / "monthly_data.csv"
YOY_CSV = MODELS_DIR / "yoy_growth.csv"
TOP_OPERATOR_CSV = MODELS_DIR / "top_operator_by_country_year.csv"

PROPHET_REVENUE = MODELS_DIR / "prophet_revenue.pkl"
PROPHET_VOLUME = MODELS_DIR / "prophet_volume.pkl"
PROPHET_DURATION = MODELS_DIR / "prophet_duration.pkl"
PROPHET_SUBCOUNT = MODELS_DIR / "prophet_subcount.pkl"

# =========================================================
# Helpers
# =========================================================
MONTH_LABELS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

def month_to_season(m: int) -> str:
    if m in [12, 1, 2]:
        return "Winter"
    if m in [3, 4, 5]:
        return "Spring"
    if m in [6, 7, 8]:
        return "Summer"
    if m in [9, 10, 11]:
        return "Autumn"
    return "Unknown"

def load_model(path: Path):
    if not path.exists():
        st.error(f"Missing model: {path}")
        st.stop()

    if joblib is not None:
        try:
            return joblib.load(path)
        except Exception:
            pass

    with open(path, "rb") as f:
        return pickle.load(f)

def format_num(x, d=2):
    try:
        return f"{float(x):,.{d}f}"
    except Exception:
        return str(x)

def _norm_col(c: str) -> str:
    return str(c).strip().lower().replace(" ", "").replace("_", "").replace("-", "")

def _find_col(df: pd.DataFrame, candidates):
    norm_map = {_norm_col(c): c for c in df.columns}
    for cand in candidates:
        key = _norm_col(cand)
        if key in norm_map:
            return norm_map[key]
    return None

# =========================================================
# Robust CSV loader (comma OR tab)
# =========================================================
@st.cache_data(show_spinner=False)
def read_csv_auto(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    return df

@st.cache_data(show_spinner=False)
def read_monthly_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        st.error("monthly_data.csv not found inside roaming_models/")
        st.stop()
    return read_csv_auto(path)

# =========================================================
# Forecast Builder (Prophet outputs)
# =========================================================
@st.cache_data(show_spinner=False)
def build_forecast():
    df = read_monthly_file(MONTHLY_CSV)

    # --- find ds or build it ---
    ds_col = _find_col(df, ["ds"])
    year_col = _find_col(df, ["Year"])
    monthnum_col = _find_col(df, ["MonthNum", "month_num", "month"])

    if ds_col is None:
        if year_col is None or monthnum_col is None:
            st.error("monthly_data.csv must contain either 'ds' OR ('Year' and 'MonthNum').")
            st.stop()

        df["ds"] = pd.to_datetime(
            df[year_col].astype(str) + "-" + df[monthnum_col].astype(str) + "-01",
            errors="coerce",
        )
    else:
        # ds like 01-10-2013 (DD-MM-YYYY)
        df["ds"] = pd.to_datetime(df[ds_col], errors="coerce", dayfirst=True)

    df = df.dropna(subset=["ds"]).sort_values("ds")

    last_ds = df["ds"].max()
    periods = max(1, (2030 - last_ds.year) * 12)

    # Load Prophet models
    m_rev = load_model(PROPHET_REVENUE)
    m_vol = load_model(PROPHET_VOLUME)
    m_dur = load_model(PROPHET_DURATION)
    m_sub = load_model(PROPHET_SUBCOUNT)

    future = m_rev.make_future_dataframe(periods=periods, freq="MS")

    rev = m_rev.predict(future)[["ds", "yhat"]].rename(columns={"yhat": "Revenue"})
    vol = m_vol.predict(future)[["ds", "yhat"]].rename(columns={"yhat": "VolumeGB"})
    dur = m_dur.predict(future)[["ds", "yhat"]].rename(columns={"yhat": "Duration"})
    sub = m_sub.predict(future)[["ds", "yhat"]].rename(columns={"yhat": "SubCount"})

    fc = rev.merge(vol, on="ds").merge(dur, on="ds").merge(sub, on="ds")

    # No negatives
    for col in ["Revenue", "VolumeGB", "Duration", "SubCount"]:
        fc[col] = pd.to_numeric(fc[col], errors="coerce").fillna(0).clip(lower=0)

    fc["Year"] = fc["ds"].dt.year
    fc["MonthNum"] = fc["ds"].dt.month
    fc["Month"] = fc["MonthNum"].map(MONTH_LABELS)
    fc["Season"] = fc["MonthNum"].apply(month_to_season)

    return fc[fc["Year"] >= 2022].copy()

# =========================================================
# Top Operator Loader (from saved CSV)
# =========================================================
@st.cache_data(show_spinner=False)
def load_top_operator_table():
    if not TOP_OPERATOR_CSV.exists():
        return None

    df = read_csv_auto(TOP_OPERATOR_CSV)

    year_col = _find_col(df, ["Year"])
    country_col = _find_col(df, ["Country"])
    op_col = _find_col(df, ["Top Operator", "TopOperator", "Operator", "Partner", "PartnerName", "Partner Name"])
    rev_col = _find_col(df, ["Revenue", "Total Revenue", "RevenueUSD", "Revenue(USD)", "TotalAmount(USD)", "TotalAmountUSD"])

    if not all([year_col, country_col, op_col]):
        return {"raw": df, "ok": False, "reason": "Missing required columns"}

    df2 = df.rename(columns={
        year_col: "Year",
        country_col: "Country",
        op_col: "Top Operator",
    }).copy()

    if rev_col is not None:
        df2 = df2.rename(columns={rev_col: "Revenue"}).copy()
        df2["Revenue"] = pd.to_numeric(df2["Revenue"], errors="coerce").fillna(0)
    else:
        df2["Revenue"] = 0.0

    df2["Year"] = pd.to_numeric(df2["Year"], errors="coerce")
    df2 = df2.dropna(subset=["Year"]).copy()
    df2["Year"] = df2["Year"].astype(int)

    df2["Country"] = df2["Country"].astype(str).str.strip()
    df2["Top Operator"] = df2["Top Operator"].astype(str).str.strip()

    return {"raw": df2, "ok": True, "reason": ""}

# =========================================================
# YoY Loader + Chart Prep
# =========================================================
@st.cache_data(show_spinner=False)
def load_yoy_table():
    if not YOY_CSV.exists():
        return None

    yoy = read_csv_auto(YOY_CSV)

    year_col = _find_col(yoy, ["Year", "year"])
    yoy_col = _find_col(yoy, ["YoY_Growth_%", "YoYGrowth%", "YoYGrowth", "YoYGrowth", "YoY", "yoy_growth", "yoy_growth_%"])

    # If detection fails, still show raw
    if year_col is None or yoy_col is None:
        return {"raw": yoy, "ok": False, "reason": "Could not detect Year / YoY column reliably."}

    df = yoy.rename(columns={year_col: "Year", yoy_col: "YoY_Growth_%"}).copy()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["YoY_Growth_%"] = pd.to_numeric(df["YoY_Growth_%"], errors="coerce")

    df = df.dropna(subset=["Year"]).copy()
    df["Year"] = df["Year"].astype(int)
    df = df.sort_values("Year")

    return {"raw": df, "ok": True, "reason": ""}

# =========================================================
# MAIN PAGE
# =========================================================
def run_roaming_predictive():
    st.title("🔮 Roaming Predictive Dashboard")
    st.caption("Forecast roaming totals (2022+), show peak months with season, and show top operator names (from saved CSV).")

    forecast_df = build_forecast()
    years = sorted(forecast_df["Year"].unique())

    col1, col2, col3 = st.columns([1, 1, 1.5])
    with col1:
        year = st.selectbox("Year", years, index=0)
    with col2:
        month = st.selectbox("Month", list(MONTH_LABELS.values()), index=0)
    with col3:
        metric = st.selectbox("Peak based on", ["Revenue", "VolumeGB", "Duration", "SubCount"], index=0)

    month_num = {v: k for k, v in MONTH_LABELS.items()}[month]

    row = forecast_df[(forecast_df["Year"] == year) & (forecast_df["MonthNum"] == month_num)]
    if row.empty:
        st.warning("No forecast available for selected year/month.")
        return

    r = row.iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Revenue (USD)", format_num(r["Revenue"]))
    k2.metric("Volume (GB)", format_num(r["VolumeGB"]))
    k3.metric("Duration (min)", format_num(r["Duration"], 0))
    k4.metric("Subscribers", format_num(r["SubCount"], 0))

    st.caption(f"Season for selected month: **{r['Season']}**")
    st.markdown("---")

    # Peak months
    year_df = forecast_df[forecast_df["Year"] == year].copy()
    top3 = year_df.sort_values(metric, ascending=False).head(3).copy()
    top3["PeakLabel"] = top3["Month"] + " (" + top3["Season"] + ")"
    peak_list = ", ".join(top3["PeakLabel"].tolist())

    st.subheader("📈 Peak Months")
    st.info(f"Top 3 months in **{year}** based on **{metric}**: {peak_list}")

    fig = px.bar(
        year_df.sort_values("MonthNum"),
        x="Month",
        y=metric,
        title=f"{metric} Forecast - {year}",
        text_auto=".2s",
    )
    fig.update_layout(template="plotly_white", height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Top Operator (from CSV)
    top_pack = load_top_operator_table()
    if top_pack is not None:
        if not top_pack.get("ok", False):
            st.warning("Top operator file found but column detection failed. Showing file preview below.")
            st.dataframe(top_pack.get("raw", pd.DataFrame()).head(20), use_container_width=True)
        else:
            top_op_df = top_pack["raw"]
            year_ops = top_op_df[top_op_df["Year"] == year].copy()

            st.subheader("🏆 Top Operator")
            if year_ops.empty:
                st.warning(f"No top-operator rows found for year {year} in top_operator_by_country_year.csv")
            else:
                overall = (
                    year_ops.groupby("Top Operator", as_index=False)["Revenue"]
                    .sum()
                    .sort_values("Revenue", ascending=False)
                )
                overall_top_name = overall.iloc[0]["Top Operator"] if not overall.empty else "N/A"
                overall_top_rev = overall.iloc[0]["Revenue"] if not overall.empty else 0

                st.success(
                    f"Overall Top Operator in **{year}** (by total revenue across countries): "
                    f"**{overall_top_name}** — Revenue: **{format_num(overall_top_rev)} USD**"
                )

                st.markdown("#### Top Operators by Country")
                show_df = year_ops.sort_values("Revenue", ascending=False).head(15).copy()
                show_df["Revenue"] = show_df["Revenue"].round(2)
                st.dataframe(show_df[["Country", "Top Operator", "Revenue"]], use_container_width=True)

    st.markdown("---")

    # =========================================================
    # YoY Growth (historical) + GRAPH ✅
    # =========================================================
    yoy_pack = load_yoy_table()
    if yoy_pack is None:
        st.info("yoy_growth.csv not found inside roaming_models/.")
        return

    st.subheader("📊 Historical YoY Growth")

    if not yoy_pack.get("ok", False):
        st.warning(f"{yoy_pack.get('reason', 'YoY file loaded but format not detected.')} Showing preview only.")
        st.dataframe(yoy_pack.get("raw", pd.DataFrame()), use_container_width=True)
        return

    yoy_df = yoy_pack["raw"].copy()

    # KPI
    latest = yoy_df.dropna(subset=["YoY_Growth_%"]).iloc[-1] if not yoy_df.dropna(subset=["YoY_Growth_%"]).empty else None
    if latest is not None:
        st.caption(f"Latest YoY: **{latest['Year']} → {format_num(latest['YoY_Growth_%'], 2)}%**")

    # Chart type toggle
    chart_type = st.radio("Chart type", ["Line", "Bar"], horizontal=True)

    if chart_type == "Line":
        fig_yoy = px.line(
            yoy_df,
            x="Year",
            y="YoY_Growth_%",
            markers=True,
            title="YoY Growth % (Historical)",
        )
    else:
        fig_yoy = px.bar(
            yoy_df,
            x="Year",
            y="YoY_Growth_%",
            title="YoY Growth % (Historical)",
            text_auto=".2f",
        )

    fig_yoy.update_layout(template="plotly_white", height=420)
    fig_yoy.update_yaxes(title="YoY Growth (%)")
    st.plotly_chart(fig_yoy, use_container_width=True)

    # Table
    st.markdown("#### YoY Table")
    st.dataframe(yoy_df, use_container_width=True)
