# roaming.py
import io
import re
import os
import pandas as pd
import streamlit as st
import plotly.express as px
import pycountry

MAPPING_PATH = "mapping/network_to_country.csv"
PARTNER_MAPPING_PATH = "mapping/partner_to_country.csv"


# =========================
# Helpers
# =========================
def safe_year_from_filename(name: str):
    m = re.search(r"(19\d{2}|20\d{2})", str(name))
    return int(m.group(1)) if m else None


def country_to_iso3(country_name: str):
    if pd.isna(country_name) or str(country_name).strip() == "":
        return None
    name = str(country_name).strip()
    fixes = {
        "USA": "United States",
        "U.S.A": "United States",
        "UK": "United Kingdom",
        "Russia": "Russian Federation",
        "South Korea": "Korea, Republic of",
        "Viet Nam": "Vietnam",
        "Iran": "Iran, Islamic Republic of",
        "Syria": "Syrian Arab Republic",
        "Bolivia": "Bolivia, Plurinational State of",
        "Tanzania": "Tanzania, United Republic of",
        "Laos": "Lao People's Democratic Republic",
        "Moldova": "Moldova, Republic of",
        "Brunei": "Brunei Darussalam",
        "Hongkong": "Hong Kong",
        "Hong Kong SAR": "Hong Kong",
        "Macau": "Macao",
    }
    name = fixes.get(name, name)
    try:
        c = pycountry.countries.lookup(name)
        return c.alpha_3
    except Exception:
        return None


def infer_country_from_network_id(network_id: str):
    if pd.isna(network_id):
        return None
    nid = str(network_id).strip().upper()
    prefix = nid[:3]
    prefix_map = {
        "ARG": "Argentina", "AUS": "Australia", "ESP": "Spain", "GBR": "United Kingdom",
        "HKG": "Hong Kong", "HRV": "Croatia", "IND": "India", "IRL": "Ireland",
        "ISR": "Israel", "JPN": "Japan", "KOR": "South Korea", "KWT": "Kuwait",
        "LBN": "Lebanon", "LTU": "Lithuania", "LUX": "Luxembourg", "MAC": "Macau",
        "MDV": "Maldives", "MEX": "Mexico", "MMR": "Myanmar", "MYS": "Malaysia",
        "NOR": "Norway", "NPL": "Nepal", "NZL": "New Zealand", "OMN": "Oman",
        "PAN": "Panama", "POL": "Poland", "PRI": "Puerto Rico", "QAT": "Qatar",
        "ROM": "Romania", "RUS": "Russia", "SAU": "Saudi Arabia", "SVK": "Slovakia",
        "SWE": "Sweden", "THA": "Thailand", "TUR": "Turkey", "USA": "United States",
        "AAZ": "Malta", "AFG": "Afghanistan", "ALB": "Albania", "AUT": "Austria",
        "BEL": "Belgium", "BGD": "Bangladesh", "BGR": "Bulgaria", "BRA": "Brazil",
        "CAN": "Canada", "CHE": "Switzerland", "CHN": "China", "CZE": "Czech Republic",
        "DEU": "Germany", "DNK": "Denmark", "EGY": "Egypt", "EST": "Estonia",
        "FIN": "Finland", "FRA": "France", "GHA": "Ghana", "GRC": "Greece",
        "HUN": "Hungary", "IDN": "Indonesia", "ITA": "Italy", "LKA": "Sri Lanka",
        "NLD": "Netherlands", "PAK": "Pakistan", "PHL": "Philippines", "PRT": "Portugal",
        "SGP": "Singapore", "ZAF": "South Africa", "LVA": "Latvia", "BMU": "Bermuda",
    }
    return prefix_map.get(prefix)


def infer_country_from_partner(partner_name: str):
    if pd.isna(partner_name):
        return None
    name = str(partner_name).strip().lower()
    rules = {
        "reliance jio": "India", "jio infocomm": "India", "bharti airtel": "India",
        "airtel": "India", "vodafone essar": "India", "mtnl": "India",
        "mahanagar telephone nigam": "India", "tele2 latvia": "Latvia",
        "tele 2 latvia": "Latvia", "bermuda": "Bermuda",
    }
    for k, v in rules.items():
        if k in name:
            return v
    return None


def detect_country_from_partner_text(partner_name: str):
    if pd.isna(partner_name):
        return None
    txt = re.sub(r"[^A-Za-z\s]", " ", str(partner_name)).strip()
    if not txt:
        return None
    words = [w for w in txt.split() if len(w) >= 4]
    for n in [4, 3, 2, 1]:
        for i in range(0, len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            try:
                c = pycountry.countries.lookup(phrase)
                return c.name
            except Exception:
                pass
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s).strip().lower())


def _sum_matching_cols(df: pd.DataFrame, pattern: re.Pattern) -> float:
    cols = [c for c in df.columns if pattern.search(_norm(c))]
    if not cols:
        return 0.0
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Robust standardisation that works for:
    - "TotalVolume(KB)" style sheets, AND
    - sheets with repeated blocks like "1st / 2nd / 3rd" where columns repeat (Volume(KB), Duration(min), etc.)
      which pandas reads as: 'Volume(KB)', 'Volume(KB).1', 'Volume(KB).2', ...
    """
    df = df.copy()
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    # Rename common identifier cols
    rename_map = {}
    for c in df.columns:
        lc = _norm(c)
        if "partnername" in lc:
            rename_map[c] = "Partner Name"
        elif "networkid" in lc:
            rename_map[c] = "Network ID"
    df = df.rename(columns=rename_map)

    # Detect TOTAL columns (if present)
    total_sub_col = None
    total_rec_col = None
    total_volume_col = None
    total_duration_col = None
    total_gprs_col = None
    total_voice_col = None

    for c in df.columns:
        lc = _norm(c)

        # totals
        if lc == "totalsubcount" or ("total" in lc and "subcount" in lc):
            total_sub_col = c
        elif lc == "totalreccount" or ("total" in lc and "reccount" in lc):
            total_rec_col = c
        elif lc == "totalvolume(kb)" or ("total" in lc and "volume(kb)" in lc):
            total_volume_col = c
        elif lc == "totalduration(min)" or ("total" in lc and "duration(min)" in lc) or ("totalduration" in lc and "min" in lc):
            total_duration_col = c
        elif ("totalgprs" in lc and "amount" in lc) or ("totalgprsamount" in lc):
            total_gprs_col = c
        elif ("totalvoice" in lc and "amount" in lc) or ("totalvoiceamount" in lc):
            total_voice_col = c

    # Patterns for repeated blocks (1st/2nd/3rd...) where columns repeat without "Total"
    p_subcount = re.compile(r"(?:^|[^a-z])subcount(?:$|[^a-z])")
    p_reccount = re.compile(r"(?:^|[^a-z])reccount(?:$|[^a-z])")
    p_volume_kb = re.compile(r"(?:^|[^a-z])volume\(kb\)(?:$|[^a-z])")
    p_duration_min = re.compile(r"(?:^|[^a-z])duration\(min\)(?:$|[^a-z])")
    p_gprs_amt = re.compile(r"(?:^|[^a-z])gprsamount\(usd\)(?:$|[^a-z])")
    p_voice_amt = re.compile(r"(?:^|[^a-z])voiceamount\(usd\)(?:$|[^a-z])")

    # Build standardized numeric columns
    df["Total SubCount"] = (
        pd.to_numeric(df[total_sub_col], errors="coerce").fillna(0)
        if total_sub_col else _sum_matching_cols(df, p_subcount)
    )
    df["Total RecCount"] = (
        pd.to_numeric(df[total_rec_col], errors="coerce").fillna(0)
        if total_rec_col else _sum_matching_cols(df, p_reccount)
    )
    df["Total Volume(KB)"] = (
        pd.to_numeric(df[total_volume_col], errors="coerce").fillna(0)
        if total_volume_col else _sum_matching_cols(df, p_volume_kb)
    )
    df["Total Duration(min)"] = (
        pd.to_numeric(df[total_duration_col], errors="coerce").fillna(0)
        if total_duration_col else _sum_matching_cols(df, p_duration_min)
    )
    df["Total GPRS Amount(USD)"] = (
        pd.to_numeric(df[total_gprs_col], errors="coerce").fillna(0)
        if total_gprs_col else _sum_matching_cols(df, p_gprs_amt)
    )
    df["Total Voice Amount(USD)"] = (
        pd.to_numeric(df[total_voice_col], errors="coerce").fillna(0)
        if total_voice_col else _sum_matching_cols(df, p_voice_amt)
    )

    df["Total Volume(GB)"] = df["Total Volume(KB)"] / (1024 * 1024)
    return df


def load_mapping():
    os.makedirs(os.path.dirname(MAPPING_PATH), exist_ok=True)
    if not os.path.exists(MAPPING_PATH) or os.path.getsize(MAPPING_PATH) == 0:
        pd.DataFrame({"Network ID": [], "Country": []}).to_csv(MAPPING_PATH, index=False)

    m = pd.read_csv(MAPPING_PATH)
    if "Network ID" not in m.columns or "Country" not in m.columns:
        st.error("Mapping file must have columns: Network ID, Country")
        st.stop()

    m["Network ID"] = m["Network ID"].astype(str).str.strip()
    m["Country"] = m["Country"].astype(str).fillna("").str.strip()
    m.loc[m["Country"].str.lower().isin(["none", "nan"]), "Country"] = ""
    return m


def load_partner_mapping():
    os.makedirs(os.path.dirname(PARTNER_MAPPING_PATH), exist_ok=True)
    if not os.path.exists(PARTNER_MAPPING_PATH) or os.path.getsize(PARTNER_MAPPING_PATH) == 0:
        pd.DataFrame({"Partner Name": [], "Country": []}).to_csv(PARTNER_MAPPING_PATH, index=False)

    pm = pd.read_csv(PARTNER_MAPPING_PATH)
    if "Partner Name" not in pm.columns or "Country" not in pm.columns:
        st.error("Partner mapping file must have columns: Partner Name, Country")
        st.stop()

    pm["Partner Name"] = pm["Partner Name"].astype(str).str.strip()
    pm["Country"] = pm["Country"].astype(str).fillna("").str.strip()
    pm.loc[pm["Country"].str.lower().isin(["none", "nan"]), "Country"] = ""
    return pm


def parse_workbook(file_bytes: bytes, filename: str):
    year = safe_year_from_filename(filename)
    xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    rows = []

    for sheet in xls.sheet_names:
        s = sheet.strip().lower()
        if s in ["total", "sheet1"]:
            continue

        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, skiprows=1, engine="openpyxl")
        df = standardize_columns(df)

        needed = [
            "Partner Name", "Network ID",
            "Total SubCount", "Total RecCount",
            "Total Duration(min)",
            "Total Volume(KB)", "Total Volume(GB)",
            "Total GPRS Amount(USD)", "Total Voice Amount(USD)"
        ]
        if any(col not in df.columns for col in needed):
            continue

        partner = df["Partner Name"].astype("string").str.strip().fillna("")
        network = df["Network ID"].astype("string").str.strip().fillna("")

        df = df[
            (partner != "") &
            (network != "") &
            (~partner.str.lower().isin(["total", "grand total"])) &
            (~network.str.lower().isin(["total", "grand total"]))
        ].copy()

        for col in needed[2:]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df["Year"] = year
        df["Month"] = sheet
        rows.append(df[needed + ["Year", "Month"]])

    if not rows:
        return pd.DataFrame(columns=needed + ["Year", "Month"])
    return pd.concat(rows, ignore_index=True)


def _month_sort_key(x: str) -> int:
    if x is None:
        return 99
    s = str(x).strip().lower()

    month_map = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    if s in month_map:
        return month_map[s]

    if re.fullmatch(r"\d{1,2}", s):
        v = int(s)
        return v if 1 <= v <= 12 else 99

    for k, v in month_map.items():
        if k in s:
            return v

    m = re.search(r"(?:^|[^0-9])(0?[1-9]|1[0-2])(?:[^0-9]|$)", s)
    if m:
        v = int(m.group(1))
        return v if 1 <= v <= 12 else 99

    return 99


def month_label_from_num(n: int) -> str:
    labels = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
        99: "Unknown"
    }
    return labels.get(int(n), "Unknown")


def month_to_season(month_num: int) -> str:
    if month_num in [12, 1, 2]:
        return "Winter"
    if month_num in [3, 4, 5]:
        return "Spring"
    if month_num in [6, 7, 8]:
        return "Summer"
    if month_num in [9, 10, 11]:
        return "Autumn"
    return None


def season_order():
    return ["Winter", "Spring", "Summer", "Autumn"]


def _apply_country_mapping(df_in: pd.DataFrame, mapping: pd.DataFrame, pm_dict: dict) -> pd.DataFrame:
    df = df_in.copy()
    df["Network ID"] = df["Network ID"].astype(str).str.strip()
    df = df.merge(mapping[["Network ID", "Country"]], on="Network ID", how="left")

    def infer_chain_row(row):
        c = row.get("Country", "")
        if pd.notna(c) and str(c).strip() != "":
            return str(c).strip()

        pname = str(row.get("Partner Name", "")).strip()
        nid = str(row.get("Network ID", "")).strip()

        if pname:
            c_pm = pm_dict.get(pname.lower(), "")
            if c_pm:
                return c_pm

        c2 = infer_country_from_partner(pname)
        if c2:
            return c2

        c3 = detect_country_from_partner_text(pname)
        if c3:
            return c3

        return infer_country_from_network_id(nid)

    df["Country_inferred"] = df.apply(infer_chain_row, axis=1)
    df["Country_inferred"] = df["Country_inferred"].where(df["Country_inferred"].notna(), "")
    df["Country_inferred"] = df["Country_inferred"].astype("string").str.strip().fillna("")
    df.loc[df["Country_inferred"].str.lower().isin(["none", "nan"]), "Country_inferred"] = ""
    df["Country"] = df["Country_inferred"]

    return df[df["Country"] != ""].copy()


def _reset_compare_uploader():
    st.session_state["compare_uploader_version"] = st.session_state.get("compare_uploader_version", 0) + 1
    st.rerun()


# =========================
# Main Page
# =========================
def run_roaming():
    # ✅ Fix: increase top padding so title is not cut (Streamlit Cloud + wide layout)
    st.markdown(
        """
        <style>
        .block-container { padding-top: 4.2rem !important; padding-bottom: 1.2rem; }
        header[data-testid="stHeader"] { background: rgba(0,0,0,0); }

        section[data-testid="stSidebar"] { border-right: 1px solid #eee; }
        h1, h2, h3 { margin-bottom: 0.35rem; }

        .title-row { display:flex; align-items:center; gap:12px; font-weight:800; margin: 0.2rem 0 0.4rem 0; flex-wrap: wrap; }
        .title-row .title-text { font-size: 40px; line-height: 1.15; }
        @media (max-width: 1100px) { .title-row .title-text { font-size: 34px; } }
        .title-icon { width:44px; height:44px; display:flex; align-items:center; justify-content:center; border-radius:10px; background: rgba(37, 99, 235, 0.10); }

        div[data-testid="stSelectbox"] > div { max-width: 520px; }
        [data-testid="stPlotlyChart"] > div { height: 100% !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- Sidebar ----------
    st.sidebar.title("Upload")

    uploaded_files = st.sidebar.file_uploader(
        "Upload Daily In Roamers Report Excel file(s)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="main_roaming_uploader",
    )

    st.sidebar.caption(" ")
    if "compare_uploader_version" not in st.session_state:
        st.session_state["compare_uploader_version"] = 0
    compare_key = f"compare_years_sidebar_{st.session_state['compare_uploader_version']}"

    st.sidebar.caption("Compare Years (optional)")
    compare_files = st.sidebar.file_uploader(
        "Compare years files",
        type=["xlsx"],
        accept_multiple_files=True,
        key=compare_key,
        label_visibility="collapsed",
    )

    mapping = load_mapping()
    partner_map = load_partner_mapping()
    pm_dict = dict(
        zip(
            partner_map["Partner Name"].astype(str).str.lower(),
            partner_map["Country"].astype(str),
        )
    )

    metric_options = [
        "Total Volume(GB)",
        "Total Duration(min)",
        "Total GPRS Amount(USD)",
        "Total Voice Amount(USD)",
        "Total SubCount",
        "Total RecCount",
    ]

    # ==========================================================
    # ✅ Compare Mode (NO main "Roaming Data Usage by Country" title)
    # ==========================================================
    if compare_files:
        metric = st.session_state.get("metric_normal_mode", "Total Volume(GB)")
        if metric not in metric_options:
            metric = "Total Volume(GB)"

        back_col, title_col = st.columns([1, 6])
        with back_col:
            if st.button("← Back", use_container_width=True):
                _reset_compare_uploader()
        with title_col:
            st.markdown("## Compare Years (Monthly Trend)")

        if len(compare_files) < 2:
            st.warning("Please upload at least 2 files in the sidebar Compare Years section.")
            st.stop()

        if len(compare_files) > 3:
            st.warning("You uploaded more than 3 files. Only the first 3 will be used.")
            compare_files = compare_files[:3]

        cmp_parts = []
        for uf in compare_files:
            p = parse_workbook(uf.getvalue(), uf.name)
            p["SourceFile"] = uf.name
            cmp_parts.append(p)

        cmp_raw = pd.concat(cmp_parts, ignore_index=True)
        if cmp_raw.empty:
            st.error("No usable data found in compare files.")
            st.stop()

        cmp_ok = _apply_country_mapping(cmp_raw, mapping, pm_dict)
        if cmp_ok.empty:
            st.error("All countries are missing in compare files after mapping.")
            st.stop()

        # ✅ MonthLabel -> Month (so chart shows Month, not MonthLabel)
        cmp_ok["Month"] = cmp_ok["Month"].astype(str).str.strip()
        cmp_ok["MonthNum"] = cmp_ok["Month"].apply(_month_sort_key)
        cmp_ok["Month"] = cmp_ok["MonthNum"].apply(month_label_from_num)

        cmp_trend = (
            cmp_ok.groupby(["Year", "MonthNum", "Month"], as_index=False)[metric]
            .sum()
            .sort_values(["MonthNum", "Year"])
        )

        years_cmp = sorted([int(y) for y in cmp_trend["Year"].dropna().unique() if pd.notna(y)])
        month_order = (
            cmp_trend[["MonthNum", "Month"]]
            .drop_duplicates()
            .sort_values("MonthNum")["Month"]
            .tolist()
        )

        fig_trend_compare = px.line(
            cmp_trend,
            x="Month",
            y=metric,
            color="Year",
            markers=True,
            category_orders={"Month": month_order},
            title=f"Monthly Trend Comparison of {metric} (Years: {', '.join(map(str, years_cmp))})",
        )
        fig_trend_compare.update_layout(
            height=560,
            template="plotly_white",
            xaxis_tickangle=-35,
            xaxis_title="Month",
            margin=dict(t=90, l=10, r=10, b=40),
        )
        st.plotly_chart(fig_trend_compare, use_container_width=True)
        st.stop()

    # ==========================================================
    # ✅ Normal Mode (SHOW title only here)
    # ==========================================================
    st.markdown(
        """
        <div class="title-row">
          <div class="title-icon">📶</div>
          <div class="title-text">Roaming Data Usage by Country</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not uploaded_files:
        st.markdown(
            """
            <div style="
                background:#fff9db;
                border-radius:10px;
                padding:14px 16px;
                border: 1px solid rgba(0,0,0,0.05);
                font-size:16px;">
                Upload one or more Excel files to begin.
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()

    # ---------- Load / combine ----------
    all_data = []
    for uf in uploaded_files:
        part = parse_workbook(uf.getvalue(), uf.name)
        part["SourceFile"] = uf.name
        all_data.append(part)

    raw_all = pd.concat(all_data, ignore_index=True)
    if raw_all.empty:
        st.error("No usable data found. Check sheet names/headers.")
        st.stop()

    df_ok = _apply_country_mapping(raw_all, mapping, pm_dict)
    if df_ok.empty:
        st.error("All countries are missing after mapping. Please update mapping CSVs.")
        st.stop()

    # ---------- Prepare aggregated country usage ----------
    country_usage = (
        df_ok.groupby(["Year", "Country"], as_index=False)
        .agg(
            {
                "Total SubCount": "sum",
                "Total RecCount": "sum",
                "Total Duration(min)": "sum",
                "Total Volume(KB)": "sum",
                "Total Volume(GB)": "sum",
                "Total GPRS Amount(USD)": "sum",
                "Total Voice Amount(USD)": "sum",
            }
        )
    )
    country_usage["ISO3"] = country_usage["Country"].apply(country_to_iso3)

    years = sorted([y for y in country_usage["Year"].dropna().unique() if pd.notna(y)])
    if not years:
        st.error("Year not detected from filenames. Ensure filenames include year like 2019, 2020, etc.")
        st.stop()

    ctrl1, ctrl2, ctrl3 = st.columns([1.1, 1.35, 2.1])
    with ctrl1:
        year_selected = st.selectbox("Select Year", years, index=len(years) - 1)
    with ctrl2:
        metric = st.selectbox("Metric", metric_options, index=0, key="metric_normal_mode")
    with ctrl3:
        top_n = st.slider("Top N countries", 5, 30, 15)

    year_df = country_usage[country_usage["Year"] == year_selected].copy().sort_values(metric, ascending=False)

    top_operator_df = (
        df_ok[df_ok["Year"] == year_selected]
        .groupby(["Country", "Partner Name"], as_index=False)
        .agg({metric: "sum"})
    )
    if not top_operator_df.empty:
        top_operator_per_country = (
            top_operator_df.loc[top_operator_df.groupby("Country")[metric].idxmax()]
            .set_index("Country")["Partner Name"]
            .to_dict()
        )
    else:
        top_operator_per_country = {}

    left, right = st.columns([1, 1])

    with left:
        st.markdown(f"### 🏆 Top {top_n} Countries ({metric}) - {year_selected}")
        top_df = year_df.head(top_n).copy()
        top_df["Top Operator"] = top_df["Country"].map(top_operator_per_country)

        fig_bar = px.bar(
            top_df,
            x="Country",
            y=metric,
            hover_data={"Top Operator": True, metric: ":,.4f"},
            category_orders={"Country": top_df["Country"].tolist()},
        )
        fig_bar.update_traces(texttemplate="%{y:,.2f}", textposition="outside")
        fig_bar.update_layout(
            height=500,
            template="plotly_white",
            margin=dict(t=30, l=10, r=10, b=40),
            xaxis_tickangle=-35,
            yaxis_title=metric,
            xaxis_title="Country",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with right:
        st.markdown(f"### 🗺️ World Map ({metric}) - {year_selected}")
        map_df = year_df[year_df["ISO3"].notna()].copy()
        map_df["Top Operator"] = map_df["Country"].map(top_operator_per_country)

        fig_map = px.choropleth(
            map_df,
            locations="ISO3",
            color=metric,
            hover_data={"Country": True, metric: ":,.4f", "Top Operator": True, "ISO3": False},
            color_continuous_scale="Blues",
        )
        fig_map.update_layout(
            height=500,
            template="plotly_white",
            margin=dict(t=30, l=10, r=10, b=10),
            geo=dict(showframe=False, showcoastlines=True, projection_type="natural earth"),
            coloraxis_colorbar=dict(title=metric),
        )
        st.plotly_chart(fig_map, use_container_width=True)

    # ==========================================================
    # Month-wise + Season-wise
    # ==========================================================
    st.markdown("---")
    st.markdown("## Month-wise and Season-wise Analysis")

    month_usage = (
        df_ok[df_ok["Year"] == year_selected]
        .groupby(["Month"], as_index=False)
        .agg({metric: "sum"})
    )
    month_usage["Month"] = month_usage["Month"].astype(str).str.strip()
    month_usage["MonthNum"] = month_usage["Month"].apply(_month_sort_key)

    # ✅ MonthLabel removed: overwrite Month to be Jan/Feb/...
    month_usage["Month"] = month_usage["MonthNum"].apply(month_label_from_num)

    trend = (
        month_usage.groupby(["MonthNum", "Month"], as_index=False)[metric]
        .sum()
        .sort_values("MonthNum")
    )

    season_df = df_ok[df_ok["Year"] == year_selected].copy()
    season_df["MonthNum"] = season_df["Month"].astype(str).str.strip().apply(_month_sort_key)
    season_df["Season"] = season_df["MonthNum"].apply(month_to_season)
    season_df = season_df[season_df["Season"].notna()].copy()

    season_trend = season_df.groupby(["Season"], as_index=False)[metric].sum()
    s_order = season_order()
    season_trend["Season"] = pd.Categorical(season_trend["Season"], categories=s_order, ordered=True)
    season_trend = season_trend.sort_values("Season")

    c1, c2 = st.columns([1.25, 1])

    with c1:
        fig_trend_single = px.bar(
            trend,
            x="Month",
            y=metric,
            title=f"Monthly Trend of {metric} ({year_selected})",
        )
        fig_trend_single.update_traces(texttemplate="%{y:,.2f}", textposition="outside")
        fig_trend_single.update_layout(
            height=420,
            margin=dict(t=70, l=10, r=10, b=40),
            template="plotly_white",
            xaxis_tickangle=-35,
            xaxis_title="Month",
        )
        fig_trend_single.update_xaxes(categoryorder="array", categoryarray=trend["Month"].tolist())
        st.plotly_chart(fig_trend_single, use_container_width=True)

    with c2:
        fig_season_donut = px.pie(
            season_trend,
            names="Season",
            values=metric,
            hole=0.55,
            title=f"Season Share ({year_selected})",
            category_orders={"Season": s_order},
        )
        fig_season_donut.update_traces(textposition="inside", textinfo="label+percent")
        fig_season_donut.update_layout(
            height=420,
            margin=dict(t=70, l=10, r=10, b=10),
            template="plotly_white",
            legend_title_text="Season",
        )
        st.plotly_chart(fig_season_donut, use_container_width=True)
