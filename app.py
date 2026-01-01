import io
import re
import os
import importlib.util
import pandas as pd
import streamlit as st
import plotly.express as px
import pycountry

# ============================================================
# App settings
# ============================================================
st.set_page_config(page_title="Roaming Usage Dashboard", layout="wide")
st.title("📶 Roaming Data Usage by Country")

MAPPING_PATH = "mapping/network_to_country.csv"
PARTNER_MAPPING_PATH = "mapping/partner_to_country.csv"

# ============================================================
# Helpers
# ============================================================
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
            phrase = " ".join(words[i : i + n])
            try:
                c = pycountry.countries.lookup(phrase)
                return c.name
            except Exception:
                pass
    return None


# ============================================================
# Extract totals
# ============================================================
def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    rename_map = {}

    def norm(s: str) -> str:
        return re.sub(r"\s+", "", str(s).strip().lower())

    total_volume_col = None
    total_gprs_col = None
    total_voice_col = None
    total_duration_col = None
    daily_volume_cols = []
    daily_vol_regex = re.compile(r"^volume\s*\(kb\)(\.\d+)?$", re.IGNORECASE)

    for c in df.columns:
        lc = norm(c)
        if "partnername" in lc:
            rename_map[c] = "Partner Name"
            continue
        if "networkid" in lc:
            rename_map[c] = "Network ID"
            continue
        if lc == "totalvolume(kb)" or ("total" in lc and "volume(kb)" in lc):
            total_volume_col = c
            continue
        if lc == "totalduration(min)" or ("total" in lc and "duration(min)" in lc) or ("totalduration" in lc and "min" in lc):
            total_duration_col = c
            continue
        if ("totalgprs" in lc and "amount" in lc) or ("totalgprsamount" in lc):
            total_gprs_col = c
            continue
        if ("totalvoice" in lc and "amount" in lc) or ("totalvoiceamount" in lc):
            total_voice_col = c
            continue
        if daily_vol_regex.match(c):
            daily_volume_cols.append(c)
            continue

    df = df.rename(columns=rename_map)

    if total_volume_col is not None:
        df["Total Volume(KB)"] = pd.to_numeric(df[total_volume_col], errors="coerce").fillna(0)
    elif daily_volume_cols:
        df["Total Volume(KB)"] = df[daily_volume_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    else:
        df["Total Volume(KB)"] = 0.0

    df["Total Duration(min)"] = pd.to_numeric(df[total_duration_col], errors="coerce").fillna(0) if total_duration_col else 0.0
    df["Total GPRS Amount(USD)"] = pd.to_numeric(df[total_gprs_col], errors="coerce").fillna(0) if total_gprs_col else 0.0
    df["Total Voice Amount(USD)"] = pd.to_numeric(df[total_voice_col], errors="coerce").fillna(0) if total_voice_col else 0.0

    return df


# ============================================================
# Mapping load/save
# ============================================================
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


def save_new_mappings_to_csv(mapping_df: pd.DataFrame, new_pairs_df: pd.DataFrame):
    if new_pairs_df.empty:
        return mapping_df
    new_pairs_df = new_pairs_df.copy()
    new_pairs_df["Network ID"] = new_pairs_df["Network ID"].astype(str).str.strip()
    new_pairs_df["Country"] = new_pairs_df["Country"].astype(str).str.strip()
    new_pairs_df = new_pairs_df[(new_pairs_df["Network ID"] != "") & (new_pairs_df["Country"] != "")]
    if new_pairs_df.empty:
        return mapping_df
    combined = pd.concat([mapping_df[["Network ID", "Country"]], new_pairs_df[["Network ID", "Country"]]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["Network ID"], keep="last").sort_values("Network ID")
    os.makedirs(os.path.dirname(MAPPING_PATH), exist_ok=True)
    combined.to_csv(MAPPING_PATH, index=False)
    return combined


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


def save_partner_mappings(pm_df: pd.DataFrame, new_df: pd.DataFrame):
    if new_df.empty:
        return pm_df
    new_df = new_df.copy()
    new_df["Partner Name"] = new_df["Partner Name"].astype(str).str.strip()
    new_df["Country"] = new_df["Country"].astype(str).str.strip()
    new_df = new_df[(new_df["Partner Name"] != "") & (new_df["Country"] != "")]
    if new_df.empty:
        return pm_df
    combined = pd.concat([pm_df[["Partner Name", "Country"]], new_df[["Partner Name", "Country"]]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["Partner Name"], keep="last").sort_values("Partner Name")
    os.makedirs(os.path.dirname(PARTNER_MAPPING_PATH), exist_ok=True)
    combined.to_csv(PARTNER_MAPPING_PATH, index=False)
    return combined


# ============================================================
# Workbook parsing
# ============================================================
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
        needed = ["Partner Name", "Network ID", "Total Volume(KB)", "Total Duration(min)", "Total GPRS Amount(USD)", "Total Voice Amount(USD)"]
        if any(col not in df.columns for col in needed):
            continue
        partner = df["Partner Name"].astype("string").str.strip().fillna("")
        network = df["Network ID"].astype("string").str.strip().fillna("")
        df = df[(partner != "") & (network != "") & (~partner.str.lower().isin(["total", "grand total"])) & (~network.str.lower().isin(["total", "grand total"]))].copy()
        for col in ["Total Volume(KB)", "Total Duration(min)", "Total GPRS Amount(USD)", "Total Voice Amount(USD)"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["Year"] = year
        df["Month"] = sheet
        rows.append(df[needed + ["Year", "Month"]])

    if not rows:
        return pd.DataFrame(columns=["Partner Name", "Network ID", "Total Volume(KB)", "Total Duration(min)", "Total GPRS Amount(USD)", "Total Voice Amount(USD)", "Year", "Month"])
    return pd.concat(rows, ignore_index=True)


def has_kaleido() -> bool:
    return importlib.util.find_spec("kaleido") is not None


# ============================================================
# UI - Sidebar
# ============================================================
st.sidebar.header("Upload")
uploaded_files = st.sidebar.file_uploader(
    "Upload Daily In Roamers Report Excel file(s)",
    type=["xlsx"],
    accept_multiple_files=True
)

mapping = load_mapping()
partner_map = load_partner_mapping()

if not uploaded_files:
    st.warning("Upload one or more Excel files to begin.")
    st.stop()

# ============================================================
# Parse
# ============================================================
all_data = []
for uf in uploaded_files:
    part = parse_workbook(uf.getvalue(), uf.name)
    part["SourceFile"] = uf.name
    all_data.append(part)

raw_all = pd.concat(all_data, ignore_index=True)
if raw_all.empty:
    st.error("No usable data found. Check sheet names/headers.")
    st.stop()

# ============================================================
# Merge mapping + inference chain
# ============================================================
raw_all["Network ID"] = raw_all["Network ID"].astype(str).str.strip()
df = raw_all.merge(mapping[["Network ID", "Country"]], on="Network ID", how="left")

pm_dict = dict(zip(partner_map["Partner Name"].astype(str).str.lower(), partner_map["Country"].astype(str)))

def infer_chain(row):
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

df["Country_inferred"] = df.apply(infer_chain, axis=1)
df["Country_inferred"] = df["Country_inferred"].where(df["Country_inferred"].notna(), "")
df["Country_inferred"] = df["Country_inferred"].astype("string").str.strip().fillna("")
df.loc[df["Country_inferred"].str.lower().isin(["none", "nan"]), "Country_inferred"] = ""

# Auto-save inferred mappings (network)
new_pairs = df[["Network ID", "Country_inferred"]].rename(columns={"Country_inferred": "Country"}).drop_duplicates()
mapped_set = set(mapping["Network ID"].astype(str).str.strip().tolist())
new_pairs = new_pairs[~new_pairs["Network ID"].astype(str).str.strip().isin(mapped_set)]
new_pairs = new_pairs[new_pairs["Country"].astype(str).str.strip() != ""]
if not new_pairs.empty:
    mapping = save_new_mappings_to_csv(mapping, new_pairs)

# Auto-save inferred mappings (partner)
new_partner_pairs = df[df["Country_inferred"].astype(str).str.strip() != ""][["Partner Name", "Country_inferred"]].rename(columns={"Country_inferred": "Country"}).drop_duplicates()
existing_pm = set(partner_map["Partner Name"].astype(str).str.lower())
new_partner_pairs = new_partner_pairs[~new_partner_pairs["Partner Name"].astype(str).str.lower().isin(existing_pm)]
if not new_partner_pairs.empty:
    partner_map = save_partner_mappings(partner_map, new_partner_pairs)

df["Country"] = df["Country_inferred"]

# ============================================================
# Missing after inference (editable)
# ============================================================
missing = df[df["Country"] == ""]
missing_ids = missing[["Network ID", "Partner Name"]].drop_duplicates().sort_values("Network ID")

if not missing_ids.empty:
    st.warning(f"⚠️ Still missing: {missing_ids.shape[0]} Network IDs. Fill Country below and click Save (one-time only).")
    with st.expander("🛠️ Fix missing Network IDs (type Country and Save)"):
        edit_df = missing_ids.copy()
        edit_df["Country"] = ""
        edited = st.data_editor(
            edit_df,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Network ID": st.column_config.TextColumn(disabled=True),
                "Partner Name": st.column_config.TextColumn(disabled=True),
                "Country": st.column_config.TextColumn(help="Type the country name (e.g., Bermuda, India)"),
            },
            key="missing_editor",
        )
        if st.button("✅ Save mappings", type="primary"):
            to_save = edited.copy()
            to_save["Network ID"] = to_save["Network ID"].astype(str).str.strip()
            to_save["Country"] = to_save["Country"].astype(str).str.strip()
            to_save = to_save[(to_save["Network ID"] != "") & (to_save["Country"] != "")]
            if to_save.empty:
                st.error("Please fill at least one Country before saving.")
            else:
                mapping = save_new_mappings_to_csv(mapping, to_save[["Network ID", "Country"]])
                p_save = edited.copy()
                p_save["Partner Name"] = p_save["Partner Name"].astype(str).str.strip()
                p_save["Country"] = p_save["Country"].astype(str).str.strip()
                p_save = p_save[(p_save["Partner Name"] != "") & (p_save["Country"] != "")]
                if not p_save.empty:
                    partner_map = save_partner_mappings(p_save, p_save[["Partner Name", "Country"]].drop_duplicates())
                st.success(f"Saved {to_save.shape[0]} mapping(s). Refreshing…")
                st.rerun()

# ============================================================
# Aggregate
# ============================================================
df_ok = df[df["Country"] != ""].copy()
country_usage = df_ok.groupby(["Year", "Country"], as_index=False).agg({
    "Total Volume(KB)": "sum",
    "Total Duration(min)": "sum",
    "Total GPRS Amount(USD)": "sum",
    "Total Voice Amount(USD)": "sum"
})
country_usage["ISO3"] = country_usage["Country"].apply(country_to_iso3)

# ============================================================
# Controls
# ============================================================
years = sorted([y for y in country_usage["Year"].dropna().unique() if pd.notna(y)])
if not years:
    st.error("Year not detected from filenames. Ensure filenames include year like 2019, 2020, etc.")
    st.stop()

colA, colB, colC = st.columns([1, 1, 2])
with colA:
    year_selected = st.selectbox("Select Year", years, index=len(years) - 1)
with colB:
    metric = st.selectbox(
        "Metric",
        ["Total Volume(KB)", "Total Duration(min)", "Total GPRS Amount(USD)", "Total Voice Amount(USD)"],
    )
with colC:
    top_n = st.slider("Top N countries", 5, 30, 15)

year_df = country_usage[country_usage["Year"] == year_selected].copy().sort_values(metric, ascending=False)

# ============================================================
# Visuals with Top Operator per Country
# ============================================================
left, right = st.columns([1, 1])

# --------------------------
# Top N Countries Bar Chart
# --------------------------
with left:
    st.subheader(f"🏆 Top {top_n} Countries ({metric}) - {year_selected}")
    top_df = year_df.head(top_n).copy()
    # Add top operator for bar hover
    top_operator_df = (
        df_ok[df_ok["Year"] == year_selected]
        .groupby(["Country", "Partner Name"], as_index=False)
        .agg({metric: "sum"})
    )
    top_operator_per_country = (
        top_operator_df.loc[top_operator_df.groupby("Country")[metric].idxmax()]
        .set_index("Country")["Partner Name"]
        .to_dict()
    )
    top_df["Top Operator"] = top_df["Country"].map(top_operator_per_country)
    fig_bar = px.bar(
        top_df,
        x="Country",
        y=metric,
        hover_data={"Top Operator": True, metric: True},
        category_orders={"Country": top_df["Country"].tolist()},
        title=""
    )
    fig_bar.update_layout(xaxis_tickangle=-45, template="plotly_white")
    st.plotly_chart(fig_bar, use_container_width=True)

# --------------------------
# World Map with Top Operator
# --------------------------
with right:
    st.subheader(f"🗺️ World Map ({metric}) - {year_selected}")
    map_df = year_df[year_df["ISO3"].notna()].copy()
    map_df["Top Operator"] = map_df["Country"].map(top_operator_per_country)
    map_df["hover_text"] = (
        map_df["Country"] + "<br>" +
        metric + ": " + map_df[metric].astype(str) + "<br>" +
        "Top Operator: " + map_df["Top Operator"].fillna("N/A")
    )
    fig_map = px.choropleth(
        map_df,
        locations="ISO3",
        color=metric,
        hover_name="hover_text",
        color_continuous_scale="Blues",
        title=""
    )
    fig_map.update_layout(
        template="plotly_white",
        geo=dict(showframe=False, showcoastlines=True, projection_type="natural earth")
    )
    st.plotly_chart(fig_map, use_container_width=True)

with st.expander("🧪 Debug: values used for ranking (top 50)"):
    st.dataframe(year_df.head(50), use_container_width=True)

# ============================================================
# Download charts
# ============================================================
st.subheader("⬇️ Download Charts")

safe_metric = re.sub(r"[^A-Za-z0-9_]+", "_", str(metric)).strip("_")

bar_html = fig_bar.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")
map_html = fig_map.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.download_button(
        "📊 Bar (HTML)",
        data=bar_html,
        file_name=f"bar_{safe_metric}_{year_selected}.html",
        mime="text/html",
    )

with c2:
    st.download_button(
        "🗺️ Map (HTML)",
        data=map_html,
        file_name=f"map_{safe_metric}_{year_selected}.html",
        mime="text/html",
    )

# PNG downloads (optional)
png_enabled = False

# This checks kaleido is installed, but PNG may still fail if Chrome/Chromium is missing
if has_kaleido():
    try:
        bar_png = fig_bar.to_image(format="png", scale=3)
        map_png = fig_map.to_image(format="png", scale=3)
        png_enabled = True

        with c3:
            st.download_button(
                "📊 Bar (PNG)",
                data=bar_png,
                file_name=f"bar_{safe_metric}_{year_selected}.png",
                mime="image/png",
            )

        with c4:
            st.download_button(
                "🗺️ Map (PNG)",
                data=map_png,
                file_name=f"map_{safe_metric}_{year_selected}.png",
                mime="image/png",
            )

    except Exception:
        # Don't crash the app if Chrome isn't available in the deployment env
        png_enabled = False

if has_kaleido() and not png_enabled:
    st.info("PNG export is not available on this deployment (missing Chrome/Chromium). Use HTML downloads instead.")
