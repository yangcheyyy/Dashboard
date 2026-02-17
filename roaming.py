# roaming.py
import io
import re
import os
from typing import Tuple

import pandas as pd
import streamlit as st
import plotly.express as px
import pycountry

MAPPING_PATH = "mapping/network_to_country.csv"
PARTNER_MAPPING_PATH = "mapping/partner_to_country.csv"

# =========================
# Network ID standardisation (code changes / alias TADIG)
# =========================
NETWORK_ID_ALIASES = {
    "THACO": "THACA",   # TrueMove old → new code
    "THAK9": "THAWN",   # Alias TADIG → main code
}

# =========================
# Helpers
# =========================
def safe_year_from_filename(name: str):
    m = re.search(r"(19\d{2}|20\d{2})", str(name))
    return int(m.group(1)) if m else None


def df_index_from_1(df: pd.DataFrame, index_name: str = "#") -> pd.DataFrame:
    """Return a copy of df with displayed index starting from 1 (for Streamlit tables)."""
    out = df.copy()
    out.index = range(1, len(out) + 1)
    out.index.name = index_name
    return out


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
    df = df.copy()
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    rename_map = {}
    for c in df.columns:
        lc = _norm(c)
        if "partnername" in lc:
            rename_map[c] = "Partner Name"
        elif "networkid" in lc:
            rename_map[c] = "Network ID"
    df = df.rename(columns=rename_map)

    total_sub_col = None
    total_rec_col = None
    total_volume_col = None
    total_duration_col = None
    total_gprs_col = None
    total_voice_col = None

    for c in df.columns:
        lc = _norm(c)
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

    p_subcount = re.compile(r"(?:^|[^a-z])subcount(?:$|[^a-z])")
    p_reccount = re.compile(r"(?:^|[^a-z])reccount(?:$|[^a-z])")
    p_volume_kb = re.compile(r"(?:^|[^a-z])volume\(kb\)(?:$|[^a-z])")
    p_duration_min = re.compile(r"(?:^|[^a-z])duration\(min\)(?:$|[^a-z])")
    p_gprs_amt = re.compile(r"(?:^|[^a-z])gprsamount\(usd\)(?:$|[^a-z])")
    p_voice_amt = re.compile(r"(?:^|[^a-z])voiceamount\(usd\)(?:$|[^a-z])")

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

    m["Network ID"] = m["Network ID"].astype(str).str.strip().str.upper()
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


# =========================
# ✅ In-app Mapping Editor (SAVE to CSV)
# =========================
def _ensure_dir_for(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def save_mapping_df(df: pd.DataFrame, path: str):
    _ensure_dir_for(path)
    df.to_csv(path, index=False)


def upsert_mapping(mapping: pd.DataFrame, network_id: str, country: str) -> pd.DataFrame:
    nid = str(network_id).strip().upper()
    ctry = str(country).strip()
    if nid == "" or ctry == "":
        return mapping

    m = mapping.copy()
    m["Network ID"] = m["Network ID"].astype(str).str.strip().str.upper()
    m["Country"] = m["Country"].astype(str).fillna("").str.strip()

    if (m["Network ID"] == nid).any():
        m.loc[m["Network ID"] == nid, "Country"] = ctry
    else:
        m = pd.concat([m, pd.DataFrame([{"Network ID": nid, "Country": ctry}])], ignore_index=True)

    m = m.drop_duplicates(subset=["Network ID"], keep="last").sort_values("Network ID").reset_index(drop=True)
    return m


def upsert_partner_mapping(pm: pd.DataFrame, partner_name: str, country: str) -> pd.DataFrame:
    pname = str(partner_name).strip()
    ctry = str(country).strip()
    if pname == "" or ctry == "":
        return pm

    p = pm.copy()
    p["Partner Name"] = p["Partner Name"].astype(str).str.strip()
    p["Country"] = p["Country"].astype(str).fillna("").str.strip()

    mask = p["Partner Name"].str.lower() == pname.lower()
    if mask.any():
        p.loc[mask, "Partner Name"] = pname
        p.loc[mask, "Country"] = ctry
    else:
        p = pd.concat([p, pd.DataFrame([{"Partner Name": pname, "Country": ctry}])], ignore_index=True)

    p = p.drop_duplicates(subset=["Partner Name"], keep="last").sort_values("Partner Name").reset_index(drop=True)
    return p


def render_mapping_editor_sidebar(mapping: pd.DataFrame, partner_map: pd.DataFrame):
    with st.sidebar.expander("🛠️ Mapping Manager (Edit in App)", expanded=False):
        st.caption("Add / update mapping here. It saves into CSV and refreshes automatically.")

        tab1, tab2 = st.tabs(["Network ID → Country", "Partner → Country"])

        with tab1:
            nid = st.text_input("Network ID", placeholder="e.g., THAWN", key="mm_nid")
            ctry = st.text_input("Country", placeholder="e.g., Thailand", key="mm_country")
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button("💾 Save Network Mapping", use_container_width=True, key="mm_save_nid"):
                    new_map = upsert_mapping(mapping, nid, ctry)
                    save_mapping_df(new_map, MAPPING_PATH)
                    st.success("Saved ✅ (network_to_country.csv)")
                    st.rerun()
            with col_b:
                if st.button("📄 View Network Map", use_container_width=True, key="mm_view_nid"):
                    st.dataframe(df_index_from_1(mapping), use_container_width=True, height=250)

        with tab2:
            pname = st.text_input(
                "Partner Name",
                placeholder="e.g., Advanced Wireless Network Company Limited",
                key="mm_partner",
            )
            ctry2 = st.text_input("Country", placeholder="e.g., Thailand", key="mm_country2")
            col_c, col_d = st.columns([1, 1])
            with col_c:
                if st.button("💾 Save Partner Mapping", use_container_width=True, key="mm_save_partner"):
                    new_pm = upsert_partner_mapping(partner_map, pname, ctry2)
                    save_mapping_df(new_pm, PARTNER_MAPPING_PATH)
                    st.success("Saved ✅ (partner_to_country.csv)")
                    st.rerun()
            with col_d:
                if st.button("📄 View Partner Map", use_container_width=True, key="mm_view_partner"):
                    st.dataframe(df_index_from_1(partner_map), use_container_width=True, height=250)


def render_missing_mappings_ui(raw_all: pd.DataFrame, mapping: pd.DataFrame, partner_map: pd.DataFrame):
    with st.expander("⚠️ Missing mappings (Fix here)", expanded=False):
        # Network IDs
        if "Network ID" in raw_all.columns:
            all_nids = raw_all["Network ID"].astype(str).str.strip().str.upper().replace(NETWORK_ID_ALIASES)
            all_nids = [x for x in all_nids.unique().tolist() if x and x.lower() not in ["nan", "none"]]
        else:
            all_nids = []

        known_nids = set(mapping["Network ID"].astype(str).str.strip().str.upper())
        missing_nids = sorted([x for x in set(all_nids) if x not in known_nids])

        st.markdown("### Missing Network IDs (not in `network_to_country.csv`)")
        if not missing_nids:
            st.success("No missing Network IDs ✅")
        else:
            st.warning(f"{len(missing_nids)} missing Network IDs found.")
            for nid in missing_nids[:30]:
                c1, c2, c3 = st.columns([1.0, 1.6, 0.8])
                with c1:
                    st.code(nid)
                with c2:
                    country = st.text_input(f"Country for {nid}", key=f"miss_nid_country_{nid}")
                with c3:
                    if st.button("Add", key=f"miss_nid_add_{nid}"):
                        new_map = upsert_mapping(mapping, nid, country)
                        save_mapping_df(new_map, MAPPING_PATH)
                        st.success(f"Added {nid} ✅")
                        st.rerun()

            if len(missing_nids) > 30:
                st.caption("Showing first 30 missing IDs. Add them, then refresh to continue.")

        # Partner Names
        st.markdown("---")
        st.markdown("### Missing Partner Names (optional: save into `partner_to_country.csv`)")

        if "Partner Name" in raw_all.columns:
            all_partners = raw_all["Partner Name"].astype(str).str.strip()
            all_partners = [
                p for p in all_partners.unique().tolist()
                if p and p.lower() not in ["nan", "none", "total", "grand total"]
            ]
        else:
            all_partners = []

        known_partners = set(partner_map["Partner Name"].astype(str).str.strip().str.lower())
        missing_partners = sorted([p for p in set(all_partners) if p.lower() not in known_partners])

        if not missing_partners:
            st.success("No missing Partner Names ✅")
        else:
            st.info(f"{len(missing_partners)} partner names not in partner map. Add only if needed.")
            for pname in missing_partners[:20]:
                c1, c2, c3 = st.columns([1.4, 1.2, 0.8])
                with c1:
                    st.write(pname)
                with c2:
                    country = st.text_input("Country", key=f"miss_partner_country_{pname}")
                with c3:
                    if st.button("Add", key=f"miss_partner_add_{pname}"):
                        new_pm = upsert_partner_mapping(partner_map, pname, country)
                        save_mapping_df(new_pm, PARTNER_MAPPING_PATH)
                        st.success("Added ✅")
                        st.rerun()

            if len(missing_partners) > 20:
                st.caption("Showing first 20 missing partners. Add them, then refresh to continue.")


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

        df["Network ID"] = (
            df["Network ID"].astype("string").str.strip().str.upper()
            .replace(NETWORK_ID_ALIASES).fillna("")
        )

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

    df["Network ID"] = (
        df["Network ID"].astype(str).str.strip().str.upper()
        .replace(NETWORK_ID_ALIASES)
    )

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


# =========================
# Bulk upload cache (upload all years once)
# =========================
def _init_cache():
    if "roaming_cache" not in st.session_state:
        st.session_state["roaming_cache"] = {
            "files_sig": None,
            "raw_all": None,
            "df_ok": None,
            "country_usage": None,
            "years": [],
        }


def _signature(files) -> Tuple[Tuple[str, int], ...]:
    return tuple(sorted([(f.name, getattr(f, "size", 0)) for f in files]))


def _rebuild_all(uploaded_files, mapping, partner_map, pm_dict):
    all_data = []
    for uf in uploaded_files:
        part = parse_workbook(uf.getvalue(), uf.name)
        part["SourceFile"] = uf.name
        all_data.append(part)

    raw_all = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
    if raw_all.empty:
        return raw_all, raw_all, raw_all, []

    # show missing mapping UI for whole dataset
    render_missing_mappings_ui(raw_all, mapping, partner_map)

    # reload mapping after any in-app edits
    mapping2 = load_mapping()
    partner_map2 = load_partner_mapping()
    pm_dict2 = dict(zip(
        partner_map2["Partner Name"].astype(str).str.lower(),
        partner_map2["Country"].astype(str),
    ))

    df_ok = _apply_country_mapping(raw_all, mapping2, pm_dict2)
    if df_ok.empty:
        return raw_all, df_ok, pd.DataFrame(), []

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
    return raw_all, df_ok, country_usage, years


def _clear_cache():
    st.session_state["roaming_cache"] = {
        "files_sig": None,
        "raw_all": None,
        "df_ok": None,
        "country_usage": None,
        "years": [],
    }
    st.rerun()


# =========================
# Main Page
# =========================
def run_roaming():

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

    _init_cache()

    metric_options = [
        "Total Volume(GB)",
        "Total Duration(min)",
        "Total GPRS Amount(USD)",
        "Total Voice Amount(USD)",
        "Total SubCount",
        "Total RecCount",
    ]

    # Sidebar upload
    st.sidebar.title("Upload (ALL years)")
    uploaded_files = st.sidebar.file_uploader(
        "Upload Daily In Roamers Report Excel file(s) (upload all years here once)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="main_roaming_uploader_all_years",
    )
    st.sidebar.caption(" ")
    st.sidebar.button("🧹 Clear loaded data", use_container_width=True, on_click=_clear_cache)

    # Mapping
    mapping = load_mapping()
    partner_map = load_partner_mapping()
    render_mapping_editor_sidebar(mapping, partner_map)
    pm_dict = dict(zip(
        partner_map["Partner Name"].astype(str).str.lower(),
        partner_map["Country"].astype(str),
    ))

    st.markdown(
        """
        <div class="title-row">
          <div class="title-icon"></div>
          <div class="title-text">Roaming Data Usage by Country</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not uploaded_files:
        st.info("Upload all year Excel files first (multiple files). After that you can select any year and compare years.")
        st.stop()

    # Build / reuse cached dataset
    sig = _signature(uploaded_files)
    cache = st.session_state["roaming_cache"]

    if cache["files_sig"] != sig or cache["country_usage"] is None:
        raw_all, df_ok, country_usage, years = _rebuild_all(uploaded_files, mapping, partner_map, pm_dict)

        if raw_all.empty:
            st.error("No usable data found. Check sheet names/headers.")
            st.stop()
        if df_ok.empty:
            st.error("All countries are missing after mapping. Please update mapping CSVs.")
            st.stop()
        if not years:
            st.error("Year not detected from filenames. Ensure filenames include year like 2019, 2020, etc.")
            st.stop()

        st.session_state["roaming_cache"] = {
            "files_sig": sig,
            "raw_all": raw_all,
            "df_ok": df_ok,
            "country_usage": country_usage,
            "years": years,
        }
        cache = st.session_state["roaming_cache"]

    df_ok = cache["df_ok"]
    country_usage = cache["country_usage"]
    years = cache["years"]

    # View mode
    st.sidebar.markdown("---")
    st.sidebar.subheader("View Mode")
    view_mode = st.sidebar.radio(
        "Select view",
        ["Single Year", "Compare Years (Multi-year)"],
        index=0,
        label_visibility="collapsed",
    )

    # =========================
    # SINGLE YEAR
    # =========================
    if view_mode == "Single Year":
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
            st.markdown(f"### Top {top_n} Countries ({metric}) - {year_selected}")
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
            st.markdown(f"### World Map ({metric}) - {year_selected}")
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

        st.markdown("---")
        st.markdown("## Month-wise and Season-wise Analysis")

        month_usage = (
            df_ok[df_ok["Year"] == year_selected]
            .groupby(["Month"], as_index=False)
            .agg({metric: "sum"})
        )
        month_usage["Month"] = month_usage["Month"].astype(str).str.strip()
        month_usage["MonthNum"] = month_usage["Month"].apply(_month_sort_key)
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

        return

    # =========================
    # COMPARE YEARS (MULTI-YEAR COMPARISON, NOT DIFFERENCE)
    # =========================
    st.markdown("## Compare Years (Multi-year comparison)")

    default_years = years[-2:] if len(years) >= 2 else years
    years_selected = st.multiselect(
        "Select Years to Compare",
        options=years,
        default=default_years,
    )

    metric = st.selectbox("Metric", metric_options, index=0, key="metric_compare_mode")

    compare_type = st.radio(
        "Compare Type",
        ["Monthly Trend (multi-year)", "Country vs Country (multi-year totals)"],
        horizontal=True,
    )

    if not years_selected or len(years_selected) < 2:
        st.info("Select at least 2 years to compare.")
        st.stop()

    df_cmp = df_ok[df_ok["Year"].isin(years_selected)].copy()

    # ✅ Make Year discrete so Plotly shows LEGEND (not a continuous colorbar)
    df_cmp["Year"] = df_cmp["Year"].astype(int).astype(str)

    df_cmp["Month"] = df_cmp["Month"].astype(str).str.strip()
    df_cmp["MonthNum"] = df_cmp["Month"].apply(_month_sort_key)
    df_cmp["MonthLabel"] = df_cmp["MonthNum"].apply(month_label_from_num)

    month_order = (
        df_cmp[["MonthNum", "MonthLabel"]]
        .drop_duplicates()
        .sort_values("MonthNum")["MonthLabel"]
        .tolist()
    )

    if compare_type == "Monthly Trend (multi-year)":
        trend_cmp = (
            df_cmp.groupby(["Year", "MonthNum", "MonthLabel"], as_index=False)[metric]
            .sum()
            .sort_values(["MonthNum", "Year"])
        )

        fig_trend = px.line(
            trend_cmp,
            x="MonthLabel",
            y=metric,
            color="Year",
            markers=True,
            category_orders={"MonthLabel": month_order},
            title=f"Monthly Trend Comparison of {metric} (Years: {', '.join(map(str, years_selected))})",
        )
        fig_trend.update_layout(
            height=560,
            template="plotly_white",
            xaxis_tickangle=-35,
            xaxis_title="Month",
            margin=dict(t=90, l=10, r=10, b=40),
            legend_title_text="Year",
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown("### Monthly Comparison Table")
        pivot_tbl = trend_cmp.pivot_table(
            index=["MonthNum", "MonthLabel"],
            columns="Year",
            values=metric,
            aggfunc="sum",
            fill_value=0,
        ).reset_index().sort_values("MonthNum")
        pivot_tbl = pivot_tbl.drop(columns=["MonthNum"])
        st.dataframe(df_index_from_1(pivot_tbl), use_container_width=True, height=420)

    else:
        top_n = st.slider("Top N countries", 5, 30, 15)

        ctry_year = (
            df_cmp.groupby(["Year", "Country"], as_index=False)[metric]
            .sum()
        )

        ctry_total = (
            ctry_year.groupby("Country", as_index=False)[metric].sum()
            .sort_values(metric, ascending=False)
            .head(top_n)
        )
        top_countries = ctry_total["Country"].tolist()
        ctry_year_top = ctry_year[ctry_year["Country"].isin(top_countries)].copy()

        fig_country = px.bar(
            ctry_year_top,
            x="Country",
            y=metric,
            color="Year",
            barmode="group",
            category_orders={"Country": top_countries},
            title=f"Country Comparison of {metric} across Years (Top {top_n})",
        )
        fig_country.update_layout(
            height=560,
            template="plotly_white",
            xaxis_tickangle=-35,
            xaxis_title="Country",
            yaxis_title=metric,
            margin=dict(t=90, l=10, r=10, b=50),
            legend_title_text="Year",
        )
        st.plotly_chart(fig_country, use_container_width=True)

        # ✅ Removed the map section in Compare Years (as you requested)

        st.markdown("### Country Comparison Table")
        pivot_country = ctry_year_top.pivot_table(
            index="Country",
            columns="Year",
            values=metric,
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        st.dataframe(df_index_from_1(pivot_country), use_container_width=True, height=420)
