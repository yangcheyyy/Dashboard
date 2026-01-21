# app.py
import io
import re
import os
import pandas as pd
import streamlit as st
import plotly.express as px
import pycountry

st.set_page_config(page_title="TashiCell Analytics Dashboard", layout="wide")

analysis = st.sidebar.selectbox(
    "Select analysis",
    [
        "1) Roaming Data Usage by Country",
        "2) Data Plan Usage by Age Group",
    ],
)

MAPPING_PATH = "mapping/network_to_country.csv"
PARTNER_MAPPING_PATH = "mapping/partner_to_country.csv"


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
            phrase = " ".join(words[i: i + n])
            try:
                c = pycountry.countries.lookup(phrase)
                return c.name
            except Exception:
                pass
    return None


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    rename_map = {}

    def norm(s: str) -> str:
        return re.sub(r"\s+", "", str(s).strip().lower())

    total_sub_col = None
    total_rec_col = None
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

        if lc == "totalsubcount" or ("total" in lc and "subcount" in lc):
            total_sub_col = c
            continue
        if lc == "totalreccount" or ("total" in lc and "reccount" in lc):
            total_rec_col = c
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

        if daily_vol_regex.match(str(c)):
            daily_volume_cols.append(c)
            continue

    df = df.rename(columns=rename_map)

    df["Total SubCount"] = pd.to_numeric(df[total_sub_col], errors="coerce").fillna(0) if total_sub_col else 0.0
    df["Total RecCount"] = pd.to_numeric(df[total_rec_col], errors="coerce").fillna(0) if total_rec_col else 0.0

    if total_volume_col is not None:
        df["Total Volume(KB)"] = pd.to_numeric(df[total_volume_col], errors="coerce").fillna(0)
    elif daily_volume_cols:
        df["Total Volume(KB)"] = df[daily_volume_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    else:
        df["Total Volume(KB)"] = 0.0

    df["Total Duration(min)"] = pd.to_numeric(df[total_duration_col], errors="coerce").fillna(0) if total_duration_col else 0.0
    df["Total GPRS Amount(USD)"] = pd.to_numeric(df[total_gprs_col], errors="coerce").fillna(0) if total_gprs_col else 0.0
    df["Total Voice Amount(USD)"] = pd.to_numeric(df[total_voice_col], errors="coerce").fillna(0) if total_voice_col else 0.0
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

        for col in [
            "Total SubCount", "Total RecCount",
            "Total Duration(min)",
            "Total Volume(KB)", "Total Volume(GB)",
            "Total GPRS Amount(USD)", "Total Voice Amount(USD)"
        ]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df["Year"] = year
        df["Month"] = sheet
        rows.append(df[needed + ["Year", "Month"]])

    if not rows:
        return pd.DataFrame(columns=[
            "Partner Name", "Network ID",
            "Total SubCount", "Total RecCount",
            "Total Duration(min)",
            "Total Volume(KB)", "Total Volume(GB)",
            "Total GPRS Amount(USD)", "Total Voice Amount(USD)",
            "Year", "Month"
        ])
    return pd.concat(rows, ignore_index=True)


def run_roaming():
    st.title("Roaming Data Usage by Country")

    st.sidebar.header("Upload (Roaming)")
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

    all_data = []
    for uf in uploaded_files:
        part = parse_workbook(uf.getvalue(), uf.name)
        part["SourceFile"] = uf.name
        all_data.append(part)

    raw_all = pd.concat(all_data, ignore_index=True)
    if raw_all.empty:
        st.error("No usable data found. Check sheet names/headers.")
        st.stop()

    raw_all["Network ID"] = raw_all["Network ID"].astype(str).str.strip()
    df = raw_all.merge(mapping[["Network ID", "Country"]], on="Network ID", how="left")

    pm_dict = dict(zip(
        partner_map["Partner Name"].astype(str).str.lower(),
        partner_map["Country"].astype(str)
    ))

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
    df["Country"] = df["Country_inferred"]

    df_ok = df[df["Country"] != ""].copy()

    country_usage = df_ok.groupby(["Year", "Country"], as_index=False).agg({
        "Total SubCount": "sum",
        "Total RecCount": "sum",
        "Total Duration(min)": "sum",
        "Total Volume(KB)": "sum",
        "Total Volume(GB)": "sum",
        "Total GPRS Amount(USD)": "sum",
        "Total Voice Amount(USD)": "sum"
    })
    country_usage["ISO3"] = country_usage["Country"].apply(country_to_iso3)

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
            [
                "Total Volume(GB)",
                "Total Duration(min)",
                "Total GPRS Amount(USD)",
                "Total Voice Amount(USD)",
            ],
        )
    with colC:
        top_n = st.slider("Top N countries", 5, 30, 15)

    year_df = country_usage[country_usage["Year"] == year_selected].copy().sort_values(metric, ascending=False)

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

    left, right = st.columns([1, 1])

    with left:
        st.subheader(f"Top {top_n} Countries by {metric} ({year_selected})")
        top_df = year_df.head(top_n).copy()
        top_df["Top Operator"] = top_df["Country"].map(top_operator_per_country)

        fig_bar = px.bar(
            top_df,
            x="Country",
            y=metric,
            hover_data={"Top Operator": True, metric: ":,.4f"},
            category_orders={"Country": top_df["Country"].tolist()},
            title=f"Top {top_n} Countries by {metric} ({year_selected})",
        )
        fig_bar.update_layout(xaxis_tickangle=-45, template="plotly_white")
        st.plotly_chart(fig_bar, use_container_width=True)

    with right:
        st.subheader(f"World Map of {metric} ({year_selected})")
        map_df = year_df[year_df["ISO3"].notna()].copy()
        map_df["Top Operator"] = map_df["Country"].map(top_operator_per_country)

        fig_map = px.choropleth(
            map_df,
            locations="ISO3",
            color=metric,
            hover_data={
                "Country": True,
                metric: ":,.4f",
                "Top Operator": True,
                "ISO3": False
            },
            color_continuous_scale="Blues",
            title=f"World Map: {metric} ({year_selected})",
        )
        fig_map.update_layout(
            template="plotly_white",
            geo=dict(showframe=False, showcoastlines=True, projection_type="natural earth")
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with st.expander("Debug: Values Used for Ranking (Top 50)"):
        dbg = year_df.head(50).copy()
        dbg["Top Operator"] = dbg["Country"].map(top_operator_per_country)
        dbg.insert(0, "No.", range(1, len(dbg) + 1))
        dbg = dbg[
            [
                "No.",
                "Country",
                "Total SubCount",
                "Total RecCount",
                "Total Duration(min)",
                "Total Volume(KB)",
                "Total Volume(GB)",
                "Total GPRS Amount(USD)",
                "Total Voice Amount(USD)",
                "ISO3",
                "Top Operator",
            ]
        ]
        st.dataframe(dbg, use_container_width=True, hide_index=True)

    st.subheader("Download Charts")

    safe_metric = re.sub(r"[^A-Za-z0-9_]+", "_", str(metric)).strip("_")
    bar_html = fig_bar.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")
    map_html = fig_map.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download Bar Chart (HTML)",
            data=bar_html,
            file_name=f"bar_{safe_metric}_{year_selected}.html",
            mime="text/html",
        )
    with c2:
        st.download_button(
            "Download Map (HTML)",
            data=map_html,
            file_name=f"map_{safe_metric}_{year_selected}.html",
            mime="text/html",
        )


@st.cache_data(show_spinner=False)
def read_uploaded_table_cached(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    name = file_name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes))
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(file_bytes))
    raise ValueError("Unsupported file type")


def run_data_plan():
    st.title("Data Plan Usage by Age Group")

    def parse_year_from_any_date(x):
        if x is None or str(x).strip() == "" or str(x).lower() in ["nan", "none"]:
            return None
        s = str(x).strip()
        try:
            dt = pd.to_datetime(s, errors="coerce")
            if pd.notna(dt):
                return int(dt.year)
        except Exception:
            pass
        m = re.search(r"(19\d{2}|20\d{2})", s)
        return int(m.group(1)) if m else None

    def calculate_age(dob_value):
        birth_year = parse_year_from_any_date(dob_value)
        if not birth_year:
            return 0
        current_year = pd.Timestamp.today().year
        age = current_year - birth_year
        return int(age) if age >= 0 else 0

    def get_age_group(age: int) -> str:
        if age < 18:
            return "Under 18"
        if age < 25:
            return "18-24"
        if age < 35:
            return "25-34"
        if age < 45:
            return "35-44"
        if age < 55:
            return "45-54"
        return "55+"

    def pick_first_existing_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    def clean_plan_name(x):
        if x is None:
            return ""
        s = str(x).strip()
        if s.lower() in ["nan", "none"]:
            return ""
        s = s.replace("_", " ")
        s = re.sub(r"\s+", " ", s).strip()
        s = s.title()
        return s

    def standardize_plan(x):
        s = clean_plan_name(x)
        plan_map = {
            "Newpackage": "New Package",
            "New Package": "New Package",
        }
        return plan_map.get(s, s)

    st.sidebar.header("Upload (Data Plan)")
    customer_file = st.sidebar.file_uploader(
        "Upload Customer Data (CSV/Excel)",
        type=["csv", "xlsx", "xls"],
        key="customer_upload",
    )
    recharge_files = st.sidebar.file_uploader(
        "Upload Recharge Data (multiple files)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key="recharge_upload",
    )

    if not customer_file or not recharge_files:
        st.info("Upload BOTH customer data and recharge data to begin.")
        st.stop()

    with st.spinner("Reading files..."):
        customer_df = read_uploaded_table_cached(customer_file.name, customer_file.getvalue())

        recharge_parts = []
        source_map = {}
        for f in recharge_files:
            try:
                df = read_uploaded_table_cached(f.name, f.getvalue())
                src = f.name.rsplit(".", 1)[0]
                df["source"] = src
                recharge_parts.append(df)
                source_map[src] = df
            except Exception as e:
                st.warning(f"Skipped {f.name} (could not read): {e}")

        if not recharge_parts:
            st.error("No recharge files could be read.")
            st.stop()

        recharge_df = pd.concat(recharge_parts, ignore_index=True)

    service_id_col = pick_first_existing_col(customer_df, ["Service_ID", "SERVICE_ID", "service_id"])
    dob_col = pick_first_existing_col(customer_df, ["date_of_birth", "Date_of_Birth", "DATE_OF_BIRTH", "DOB", "dob"])
    plan_col = pick_first_existing_col(customer_df, ["rate_plan_name", "Rate_Plan_Name", "RATE_PLAN_NAME", "plan", "Plan"])

    recharge_num_col = pick_first_existing_col(recharge_df, ["RECHARGE_NUMBER", "Recharge_Number", "recharge_number"])
    amount_col = pick_first_existing_col(recharge_df, ["Recharge_Amount(Nu)", "Recharge_Amount", "recharge_amount", "Amount", "amount"])

    missing_cols = []
    if not service_id_col:
        missing_cols.append("Service_ID (customer)")
    if not dob_col:
        missing_cols.append("date_of_birth (customer)")
    if not plan_col:
        missing_cols.append("rate_plan_name (customer)")
    if not recharge_num_col:
        missing_cols.append("RECHARGE_NUMBER (recharge)")
    if not amount_col:
        missing_cols.append("Recharge_Amount(Nu) (recharge)")

    if missing_cols:
        st.error("Missing required columns:\n- " + "\n- ".join(missing_cols))
        st.write("Customer columns:", list(customer_df.columns))
        st.write("Recharge columns:", list(recharge_df.columns))
        st.stop()

    with st.spinner("Processing and matching..."):
        cust = customer_df[[service_id_col, dob_col, plan_col]].copy()
        cust["sid"] = cust[service_id_col].astype(str).str.strip()
        cust = cust[~cust["sid"].str.lower().isin(["nan", "none", ""])].copy()

        cust["Plan"] = cust[plan_col].apply(standardize_plan)
        cust["Age"] = cust[dob_col].apply(calculate_age)
        cust["Age Group"] = cust["Age"].apply(get_age_group)

        rech = recharge_df[[recharge_num_col, amount_col, "source"]].copy()
        rech["rid"] = rech[recharge_num_col].astype(str).str.strip()
        rech = rech[~rech["rid"].str.lower().isin(["nan", "none", ""])].copy()
        rech["rid_no975"] = rech["rid"].str.replace(r"^975", "", regex=True)
        rech["Amount"] = pd.to_numeric(rech[amount_col], errors="coerce").fillna(0.0)

        merged = rech.merge(cust[["sid", "Age Group", "Plan"]], left_on="rid_no975", right_on="sid", how="inner")
        matched = len(merged)

        order = ["Under 18", "18-24", "25-34", "35-44", "45-54", "55+"]

        age_group_df = (
            merged.groupby("Age Group", as_index=False)
            .agg(
                Users=("rid_no975", "nunique"),
                **{
                    "Total Recharges": ("rid_no975", "size"),
                    "Total Amount (Nu)": ("Amount", "sum"),
                }
            )
        )
        if not age_group_df.empty:
            age_group_df["Total Amount (Nu)"] = age_group_df["Total Amount (Nu)"].round(2)
            age_group_df["Avg Amount (Nu)"] = (age_group_df["Total Amount (Nu)"] / age_group_df["Total Recharges"]).round(2)
            age_group_df["__ord"] = age_group_df["Age Group"].apply(lambda x: order.index(x) if x in order else 999)
            age_group_df = age_group_df.sort_values("__ord").drop(columns="__ord")

        merged["Plan"] = merged["Plan"].replace("", "Unknown plan")
        plan_by_age_df = (
            merged.groupby(["Age Group", "Plan"], as_index=False)
            .agg(**{"Recharge Count": ("Plan", "size")})
        )
        if not plan_by_age_df.empty:
            plan_by_age_df["__ord"] = plan_by_age_df["Age Group"].apply(lambda x: order.index(x) if x in order else 999)
            plan_by_age_df = plan_by_age_df.sort_values(["__ord", "Recharge Count"], ascending=[True, False]).drop(columns="__ord")

        source_rows = []
        for src, df in source_map.items():
            a = pd.to_numeric(df.get(amount_col), errors="coerce").fillna(0).sum() if amount_col in df.columns else 0
            source_rows.append({
                "Source": src,
                "Total Recharges": len(df),
                "Total Amount (Nu)": float(a),
                "Avg Amount (Nu)": float(a / len(df)) if len(df) else 0.0
            })
        source_df = pd.DataFrame(source_rows).sort_values("Total Amount (Nu)", ascending=False)

        total_rev = pd.to_numeric(recharge_df[amount_col], errors="coerce").fillna(0).sum()

    tab_overview, tab_source, tab_age, tab_plans = st.tabs(
        ["Overview", "Source Analysis", "Age Group Analysis", "Plan Distribution"]
    )

    with tab_overview:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Customers", f"{len(customer_df):,}")
        m2.metric("Total Recharges", f"{len(recharge_df):,}")
        m3.metric("Total Revenue (Nu)", f"{total_rev:,.2f}")
        m4.metric("Avg Recharge (Nu)", f"{(total_rev/len(recharge_df) if len(recharge_df) else 0):,.2f}")

        with st.expander("Debug: Matching Information", expanded=False):
            st.write(f"Matched recharges: **{matched:,}** / {len(recharge_df):,}")
            if matched == 0:
                st.error("No matches found. Check if customer Service_ID matches recharge RECHARGE_NUMBER (with/without 975).")

    with tab_source:
        st.subheader("Revenue by Source Area")
        st.dataframe(source_df.reset_index(drop=True), use_container_width=True, hide_index=True)

        if not source_df.empty:
            fig_src_amt = px.bar(
                source_df,
                x="Source",
                y="Total Amount (Nu)",
                title="Total Revenue (Nu) by Source Area",
                labels={"Source": "Source Area", "Total Amount (Nu)": "Total Revenue (Nu)"},
            )
            fig_src_amt.update_layout(template="plotly_white", xaxis_tickangle=-45)
            st.plotly_chart(fig_src_amt, use_container_width=True)

            fig_src_cnt = px.bar(
                source_df,
                x="Source",
                y="Total Recharges",
                title="Total Recharges by Source Area",
                labels={"Source": "Source Area", "Total Recharges": "Total Recharges"},
            )
            fig_src_cnt.update_layout(template="plotly_white", xaxis_tickangle=-45)
            st.plotly_chart(fig_src_cnt, use_container_width=True)

    with tab_age:
        st.subheader("Age Group Statistics")
        if age_group_df.empty:
            st.warning("No age-group stats (likely no matches). Check Debug.")
        else:
            st.dataframe(age_group_df.reset_index(drop=True), use_container_width=True, hide_index=True)

            fig_age_rech = px.bar(
                age_group_df,
                x="Age Group",
                y="Total Recharges",
                title="Total Recharges by Age Group",
                labels={"Age Group": "Age Group", "Total Recharges": "Total Recharges"},
                category_orders={"Age Group": order},
            )
            fig_age_rech.update_layout(template="plotly_white")
            st.plotly_chart(fig_age_rech, use_container_width=True)

            fig_age_amt = px.bar(
                age_group_df,
                x="Age Group",
                y="Total Amount (Nu)",
                title="Total Revenue (Nu) by Age Group",
                labels={"Age Group": "Age Group", "Total Amount (Nu)": "Total Revenue (Nu)"},
                category_orders={"Age Group": order},
            )
            fig_age_amt.update_layout(template="plotly_white")
            st.plotly_chart(fig_age_amt, use_container_width=True)

    with tab_plans:
        st.subheader("Plan Usage Distribution by Age Group")
        if plan_by_age_df.empty:
            st.warning("No plan distribution data (likely no matches). Check Debug.")
        else:
            st.dataframe(plan_by_age_df.reset_index(drop=True), use_container_width=True, hide_index=True)

            popular = (
                plan_by_age_df.groupby("Plan", as_index=False)["Recharge Count"].sum()
                .sort_values("Recharge Count", ascending=False)
                .head(25)
            )

            st.subheader("Most Popular Plans (Overall)")
            st.dataframe(popular.reset_index(drop=True), use_container_width=True, hide_index=True)

            fig_pop = px.bar(
                popular,
                x="Plan",
                y="Recharge Count",
                title="Top 25 Most Popular Plans by Recharge Count",
                labels={"Plan": "Plan Name", "Recharge Count": "Recharge Count"},
            )
            fig_pop.update_layout(template="plotly_white", xaxis_tickangle=-45)
            st.plotly_chart(fig_pop, use_container_width=True)


if analysis.startswith("1)"):
    run_roaming()
else:
    run_data_plan()
