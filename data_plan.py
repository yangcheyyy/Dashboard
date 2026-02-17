# data_plan.py
import io
import re
from datetime import datetime  # optional (safe to keep)

import pandas as pd
import streamlit as st
import plotly.express as px


@st.cache_data(show_spinner=False)
def read_uploaded_table_cached(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    name = file_name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes))
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(file_bytes))
    raise ValueError("Unsupported file type")


def run_data_plan():
    # -----------------------------
    # ✅ Cleaner title + subtitle
    # -----------------------------
    st.title("Data Plan Usage")
    st.caption("Age Group • Plan Distribution • Seasonality • Expiry & Renewal Behaviour")

    # -----------------------------
    # ✅ UI Polish (less messy)
    # -----------------------------
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.1rem; padding-bottom: 1.2rem;}

        button[data-baseweb="tab"] {
            font-size: 14px !important;
            padding: 8px 14px !important;
        }

        [data-testid="stMetric"] {
            padding: 10px 12px !important;
            border-radius: 12px !important;
            background: #fafafa !important;
            border: 1px solid #eee !important;
        }
        [data-testid="stMetricLabel"] {font-size: 13px !important;}
        [data-testid="stMetricValue"] {font-size: 26px !important;}

        h2, h3 {margin-top: 0.6rem !important; margin-bottom: 0.4rem !important;}
        h1 {margin-bottom: 0.6rem !important;}

        div[data-testid="stDataFrame"] {border-radius: 12px; border: 1px solid #eee;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # =========================
    # Helpers
    # =========================
    def normalize_source_name(src: str) -> str:
        """
        Merge ALL variants into the base source name (remove trailing numbers).
        ✅ Also: standardize My TashiCell variants to 'my tashicell'
        """
        if src is None:
            return "Unknown"

        s = str(src).strip()
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"\(\s*\d+\s*\)\s*$", "", s)  # "mypay(1)" -> "mypay"
        s = re.sub(r"[_\-]+", " ", s)  # "_" "-" -> space
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"\s*\d+\s*$", "", s).strip()  # trailing digits

        if s:
            s_lower = s.lower()
            compact = re.sub(r"\s+", "", s_lower)
            if compact == "mytashicell":
                return "my tashicell"
            if "tashicell" in s_lower and s_lower.startswith("my"):
                return "my tashicell"

        return s if s else "Unknown"

    def format_currency_short(n: float) -> str:
        n = float(n) if n is not None else 0.0
        if abs(n) >= 1_000_000_000:
            return f"Nu {n/1_000_000_000:.2f} B"
        if abs(n) >= 1_000_000:
            return f"Nu {n/1_000_000:.2f} M"
        return f"Nu {n:,.2f}"

    def parse_year_from_any_date(x):
        if x is None or str(x).strip() == "" or str(x).lower() in ["nan", "none"]:
            return None
        s = str(x).strip()
        try:
            dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
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
        return s.title()

    def standardize_plan(x):
        s = clean_plan_name(x)
        plan_map = {
            "Newpackage": "New Package",
            "New Package": "New Package",
        }
        return plan_map.get(s, s)

    def add_bar_labels(fig, kind="count"):
        if kind == "money":
            fig.update_traces(textposition="outside", texttemplate="Nu %{text:,.2f}")
        else:
            fig.update_traces(textposition="outside", texttemplate="%{text:,}")
        fig.update_layout(uniformtext_minsize=8, uniformtext_mode="hide", margin=dict(t=80))
        return fig

    def last_n_digits(x, n=8):
        if x is None:
            return ""
        s = str(x).strip()
        if s.lower() in ["nan", "none", ""]:
            return ""
        digits = re.sub(r"\D+", "", s)
        if len(digits) < n:
            return ""
        return digits[-n:]

    def detect_recharge_date_column(df):
        candidates = [
            "Recharge_date",
            "RECHARGE_DATE",
            "recharge_date",
            "Recharge_Date",
            "Transaction_Date",
            "TRANSACTION_DATE",
            "transaction_date",
            "Date",
            "DATE",
            "date",
            "Txn_Date",
            "TXN_DATE",
            "txn_date",
            "Recharge_Time",
            "RECHARGE_TIME",
            "recharge_time",
            "Time",
            "TIME",
            "time",
        ]
        return pick_first_existing_col(df, candidates)

    # =========================================================
    # Bucket mapping (includes Late Night plans)
    # =========================================================
    def map_recharge_bucket(amount_value, dt_value=None) -> str:
        try:
            amt = float(amount_value)
        except Exception:
            return "Talktime"

        amt_int = int(round(amt))

        year = None
        try:
            if dt_value is not None and pd.notna(dt_value):
                year = pd.to_datetime(dt_value, errors="coerce", dayfirst=True).year
        except Exception:
            year = None

        use_gst = (year is not None and year >= 2026)

        daily = {19}
        weekly = {49}
        monthly = {99, 199, 299, 499, 599, 699, 777, 999, 1299}
        bi_monthly = {1499, 1999}
        quaterly = {2499, 2999}

        daily_late = {61} if use_gst else {57}
        weekly_late = {221} if use_gst else {207}

        def fmt(n: int) -> str:
            return f"{n:,}"

        if amt_int in daily_late:
            return f"Daily Unlimited Late Night {fmt(amt_int)}"
        if amt_int in weekly_late:
            return f"Weekly Unlimited Late Night {fmt(amt_int)}"

        if amt_int in daily:
            return f"Daily Plan {fmt(amt_int)}"
        if amt_int in weekly:
            return f"Weekly Plan {fmt(amt_int)}"
        if amt_int in monthly:
            return f"Monthly Plan {fmt(amt_int)}"
        if amt_int in bi_monthly:
            return f"Bi-Monthly Plan {fmt(amt_int)}"
        if amt_int in quaterly:
            return f"Quaterly Plan {fmt(amt_int)}"

        return "Talktime"

    bucket_order = [
        "Daily Plan 19",
        "Weekly Plan 49",
        "Daily Unlimited Late Night 57",
        "Weekly Unlimited Late Night 207",
        "Daily Unlimited Late Night 61",
        "Weekly Unlimited Late Night 221",
        "Monthly Plan 99",
        "Monthly Plan 199",
        "Monthly Plan 299",
        "Monthly Plan 499",
        "Monthly Plan 599",
        "Monthly Plan 699",
        "Monthly Plan 777",
        "Monthly Plan 999",
        "Monthly Plan 1,299",
        "Bi-Monthly Plan 1,499",
        "Bi-Monthly Plan 1,999",
        "Quaterly Plan 2,499",
        "Quaterly Plan 2,999",
        "Talktime",
    ]

    # =========================
    # Sidebar Upload
    # =========================
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
        for f in recharge_files:
            try:
                df = read_uploaded_table_cached(f.name, f.getvalue())
                raw_src = f.name.rsplit(".", 1)[0]
                df["source"] = normalize_source_name(raw_src)
                df["_file"] = f.name
                recharge_parts.append(df)
            except Exception as e:
                st.warning(f"Skipped {f.name} (could not read): {e}")

        if not recharge_parts:
            st.error("No recharge files could be read.")
            st.stop()

        recharge_df = pd.concat(recharge_parts, ignore_index=True)

    # =========================
    # Detect date column + period label
    # =========================
    recharge_date_col = detect_recharge_date_column(recharge_df)
    dt_series = None
    if recharge_date_col:
        dt_series = pd.to_datetime(recharge_df[recharge_date_col], errors="coerce", dayfirst=True)
        if dt_series.notna().sum() == 0:
            dt_series = None

    if dt_series is not None:
        tmp_dt = pd.DataFrame({"dt": dt_series}).dropna()
        if tmp_dt.empty:
            period_label = "All Periods"
        else:
            mn = tmp_dt["dt"].min()
            mx = tmp_dt["dt"].max()
            if mn.year == mx.year and mn.month == mx.month:
                period_label = mn.strftime("%b %Y")
            else:
                period_label = f"{mn.strftime('%b %Y')} to {mx.strftime('%b %Y')}"
    else:
        period_label = "All Periods"

    # =========================
    # Column detection
    # =========================
    service_id_col = pick_first_existing_col(customer_df, ["Service_ID", "SERVICE_ID", "service_id"])
    dob_col = pick_first_existing_col(customer_df, ["date_of_birth", "Date_of_Birth", "DATE_OF_BIRTH", "DOB", "dob"])
    plan_col = pick_first_existing_col(
        customer_df, ["rate_plan_name", "Rate_Plan_Name", "RATE_PLAN_NAME", "plan", "Plan"]
    )

    recharge_num_col = pick_first_existing_col(recharge_df, ["RECHARGE_NUMBER", "Recharge_Number", "recharge_number"])
    amount_col = pick_first_existing_col(
        recharge_df,
        ["Recharge_Amount(Nu)", "Recharge_Amount(Nu) ", "Recharge_Amount", "recharge_amount", "Amount", "amount"],
    )

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

    # =========================
    # Build BASE tables once
    # =========================
    with st.spinner("Processing and matching..."):
        cust = customer_df[[service_id_col, dob_col, plan_col]].copy()
        cust["sid_raw"] = cust[service_id_col].astype(str).str.strip()
        cust = cust[~cust["sid_raw"].str.lower().isin(["nan", "none", ""])].copy()

        cust["Age"] = cust[dob_col].apply(calculate_age)
        cust["Plan"] = cust[plan_col].apply(standardize_plan)

        cust["sid_text"] = cust["sid_raw"].astype(str).str.replace(r"\.0$", "", regex=True)
        cust["sid_last8"] = cust["sid_text"].apply(lambda x: last_n_digits(x, 8))
        cust = cust[cust["sid_last8"] != ""].copy()

        cols = [recharge_num_col, amount_col, "source", "_file"]
        if recharge_date_col:
            cols.append(recharge_date_col)

        rech = recharge_df[cols].copy()

        rech["rid_text"] = rech[recharge_num_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        rech["rid_raw"] = rech["rid_text"]
        rech = rech[~rech["rid_raw"].str.lower().isin(["nan", "none", ""])].copy()

        rech["rid_last8"] = rech["rid_raw"].apply(lambda x: last_n_digits(x, 8))
        rech = rech[rech["rid_last8"] != ""].copy()

        rech["Amount"] = pd.to_numeric(rech[amount_col], errors="coerce").fillna(0.0)

        if recharge_date_col:
            rech["_dt"] = pd.to_datetime(rech[recharge_date_col], errors="coerce", dayfirst=True)
            rech["_month"] = rech["_dt"].dt.to_period("M").dt.to_timestamp()
            rech["_month_label"] = rech["_month"].dt.strftime("%b %Y")
        else:
            rech["_dt"] = pd.NaT
            rech["_month"] = pd.NaT
            rech["_month_label"] = "Unknown"

        rech["Plan Bucket"] = rech.apply(lambda r: map_recharge_bucket(r["Amount"], r["_dt"]), axis=1)

        merged_base = rech.merge(
            cust[["sid_last8", "Age", "Plan"]],
            left_on="rid_last8",
            right_on="sid_last8",
            how="inner",
        )

        total_rev = float(rech["Amount"].sum())
        total_recharges = int(len(rech))
        matched_recharges = int(len(merged_base))
        unmatched_recharges = int(max(total_recharges - matched_recharges, 0))

        total_unique_numbers = int(rech["rid_last8"].nunique())
        matched_unique_numbers = int(merged_base["rid_last8"].nunique()) if not merged_base.empty else 0
        unmatched_unique_numbers = int(max(total_unique_numbers - matched_unique_numbers, 0))

        matched_keys = set(cust["sid_last8"].dropna().astype(str))
        unmatched_df = rech[~rech["rid_last8"].isin(matched_keys)].copy()
        unmatched_unique_df = unmatched_df.drop_duplicates(subset=["rid_last8"]).copy()

        source_df = rech.groupby("source", as_index=False).agg(
            **{"Total Recharges": ("source", "size"), "Total Amount (Nu)": ("Amount", "sum")}
        )
        if not source_df.empty:
            source_df["Total Amount (Nu)"] = source_df["Total Amount (Nu)"].round(2)
            source_df["Avg Amount (Nu)"] = (source_df["Total Amount (Nu)"] / source_df["Total Recharges"]).round(2)
            source_df = source_df.rename(columns={"source": "Source"}).sort_values("Total Amount (Nu)", ascending=False)
        else:
            source_df = pd.DataFrame(columns=["Source", "Total Recharges", "Total Amount (Nu)", "Avg Amount (Nu)"])

        month_source_df = pd.DataFrame()
        if recharge_date_col:
            month_source_df = (
                rech.dropna(subset=["_month"])
                .groupby(["source", "_month", "_month_label"], as_index=False)
                .agg(**{"Total Recharges": ("Amount", "size"), "Total Amount (Nu)": ("Amount", "sum")})
            )
            if not month_source_df.empty:
                month_source_df["Total Amount (Nu)"] = month_source_df["Total Amount (Nu)"].round(2)
                month_source_df["Avg Amount (Nu)"] = (
                    month_source_df["Total Amount (Nu)"] / month_source_df["Total Recharges"]
                ).round(2)
                month_source_df = month_source_df.sort_values(["source", "_month"])

    # =========================================================
    # ✅ Independent Age Range States (3 separate)
    # =========================================================
    if "age_ranges_age" not in st.session_state:
        st.session_state.age_ranges_age = {
            "under_1": 15,
            "cut_2": 17,
            "cut_3": 24,
            "cut_4": 34,
            "cut_5": 44,
            "cut_6": 54,
            "cut_7": 65,
        }

    if "age_ranges_plan" not in st.session_state:
        st.session_state.age_ranges_plan = {
            "under_1": 15,
            "cut_2": 17,
            "cut_3": 24,
            "cut_4": 34,
            "cut_5": 44,
            "cut_6": 54,
            "cut_7": 65,
        }

    if "age_ranges_expiry" not in st.session_state:
        st.session_state.age_ranges_expiry = {
            "under_1": 15,
            "cut_2": 17,
            "cut_3": 24,
            "cut_4": 34,
            "cut_5": 44,
            "cut_6": 54,
            "cut_7": 65,
        }

    def validate_ranges(r: dict) -> tuple[bool, str]:
        vals = [r["under_1"], r["cut_2"], r["cut_3"], r["cut_4"], r["cut_5"], r["cut_6"], r["cut_7"]]
        if any(v < 0 or v > 120 for v in vals):
            return False, "All limits must be between 0 and 120."
        if not (vals[0] <= vals[1] <= vals[2] <= vals[3] <= vals[4] <= vals[5] <= vals[6]):
            return False, "Limits must be in increasing order (Under <= Cut2 <= Cut3 <= ... <= Cut7)."
        return True, ""

    # =========================
    # Tabs
    # =========================
    tab_overview, tab_source, tab_age, tab_plans, tab_season, tab_expiry = st.tabs(
        ["Overview", "Source Analysis", "Age Group Analysis", "Plan Distribution", "Season-wise Unlimited", "Expiry & Extension"]
    )

    # =========================
    # ✅ Overview
    # =========================
    with tab_overview:
        st.subheader(f"Overview — {period_label}")

        k1, k2, k3, k4 = st.columns(4, gap="small")
        k1.metric("Total Customers", f"{len(customer_df):,}")
        k2.metric("Transactions", f"{total_recharges:,}")
        k3.metric("Revenue", format_currency_short(total_rev))
        k4.metric("Avg Recharge", f"{(total_rev/total_recharges if total_recharges else 0):,.2f}")

        st.divider()

        st.markdown("#### Matching Health")
        a1, a2, a3 = st.columns(3, gap="small")
        a1.metric("Matched Transactions", f"{matched_recharges:,}")
        a2.metric("Unmatched Transactions", f"{unmatched_recharges:,}")
        match_rate = (matched_recharges / total_recharges * 100) if total_recharges else 0
        a3.metric("Match Rate", f"{match_rate:.1f}%")

        st.markdown("#### Unique Numbers")
        b1, b2, b3 = st.columns(3, gap="small")
        b1.metric("Unique Numbers", f"{total_unique_numbers:,}")
        b2.metric("Matched Unique", f"{matched_unique_numbers:,}")
        b3.metric("Unmatched Unique", f"{unmatched_unique_numbers:,}")

        with st.expander("Show debugging details", expanded=False):
            st.write(f"Matched transactions (rows): **{matched_recharges:,}** / {total_recharges:,}")
            st.write(f"Unique numbers (all): **{total_unique_numbers:,}**")
            st.write(f"Unique matched numbers: **{matched_unique_numbers:,}**")
            st.write(f"Unique unmatched numbers: **{unmatched_unique_numbers:,}**")
            st.write("Source rule: base source name (BOB1/BOB_1/BOB-1/BOB(1) → BOB).")

        st.divider()

        st.markdown("#### Unmatched Recharges (Unique Numbers)")
        st.caption("These recharge numbers do not exist in customer file (after last-8 matching).")

        view_unmatched = unmatched_unique_df.copy()
        show_cols = [c for c in ["_file", "rid_text", "Amount", "_month_label", "Plan Bucket"] if c in view_unmatched.columns]
        if "Amount" in view_unmatched.columns:
            view_unmatched = view_unmatched.sort_values("Amount", ascending=False)

        with st.expander(f"Show unmatched table ({len(view_unmatched):,})", expanded=False):
            display_df = (
                view_unmatched[show_cols]
                .copy()
                .rename(
                    columns={
                        "_file": "File",
                        "_month_label": "Month",
                        "rid_text": "Recharge Number",
                    }
                )
            )
            st.dataframe(display_df.reset_index(drop=True), use_container_width=True, hide_index=True)

            csv_bytes = display_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download unmatched unique numbers (CSV)",
                data=csv_bytes,
                file_name=f"unmatched_unique_numbers_{period_label.replace(' ', '_')}.csv",
                mime="text/csv",
            )

    # =========================
    # Source Analysis
    # =========================
    with tab_source:
        st.subheader("Revenue by Source Area")

        unique_sources = list(pd.Series(rech["source"].dropna().unique()).astype(str))
        n_sources = len(unique_sources)

        has_months = (recharge_date_col is not None) and (not month_source_df.empty)
        multi_month = False
        if has_months and n_sources == 1:
            months_for_that_source = month_source_df[month_source_df["source"] == unique_sources[0]]["_month"].nunique()
            multi_month = months_for_that_source >= 2

        if n_sources == 1 and multi_month:
            only_source = unique_sources[0]
            st.caption(f"Detected single source **{only_source}** with multiple months → showing month-wise comparison.")

            ms = month_source_df[month_source_df["source"] == only_source].copy()
            ms = ms.rename(columns={"source": "Source", "_month_label": "Month"})[
                ["Source", "Month", "Total Recharges", "Total Amount (Nu)", "Avg Amount (Nu)"]
            ]

            st.dataframe(ms.reset_index(drop=True), use_container_width=True, hide_index=True)

            fig_m_amt = px.bar(
                ms,
                x="Month",
                y="Total Amount (Nu)",
                title=f"Total Revenue (Nu) — {only_source} (Month-wise)",
                labels={"Month": "Month", "Total Amount (Nu)": "Total Revenue (Nu)"},
                text="Total Amount (Nu)",
            )
            fig_m_amt.update_layout(template="plotly_white", xaxis_tickangle=-45)
            add_bar_labels(fig_m_amt, kind="money")
            st.plotly_chart(fig_m_amt, use_container_width=True)

            fig_m_cnt = px.bar(
                ms,
                x="Month",
                y="Total Recharges",
                title=f"Total Recharges — {only_source} (Month-wise)",
                labels={"Month": "Month", "Total Recharges": "Total Recharges"},
                text="Total Recharges",
            )
            fig_m_cnt.update_layout(template="plotly_white", xaxis_tickangle=-45)
            add_bar_labels(fig_m_cnt, kind="count")
            st.plotly_chart(fig_m_cnt, use_container_width=True)

        else:
            st.dataframe(source_df.reset_index(drop=True), use_container_width=True, hide_index=True)

            if not source_df.empty:
                fig_src_amt = px.bar(
                    source_df,
                    x="Source",
                    y="Total Amount (Nu)",
                    title=f"Total Revenue (Nu) by Source Area — {period_label}",
                    labels={"Source": "Source Area", "Total Amount (Nu)": "Total Revenue (Nu)"},
                    text="Total Amount (Nu)",
                )
                fig_src_amt.update_layout(template="plotly_white", xaxis_tickangle=-45)
                add_bar_labels(fig_src_amt, kind="money")
                st.plotly_chart(fig_src_amt, use_container_width=True)

                fig_src_cnt = px.bar(
                    source_df,
                    x="Source",
                    y="Total Recharges",
                    title=f"Total Recharges by Source Area — {period_label}",
                    labels={"Source": "Source Area", "Total Recharges": "Total Recharges"},
                    text="Total Recharges",
                )
                fig_src_cnt.update_layout(template="plotly_white", xaxis_tickangle=-45)
                add_bar_labels(fig_src_cnt, kind="count")
                st.plotly_chart(fig_src_cnt, use_container_width=True)

    # =========================
    # Age Group Analysis
    # =========================
    with tab_age:
        st.subheader(f"Age Group Statistics — {period_label}")

        with st.expander("Edit Age Group Ranges", expanded=False):
            with st.form("age_group_form_age", clear_on_submit=False):
                r = st.session_state.age_ranges_age

                c1, c2, c3, c4 = st.columns(4)
                under_1 = c1.number_input("Under (group 1)", 0, 120, int(r["under_1"]), 1, key="age_under_1__age")
                cut_2 = c2.number_input("Upper limit group 2 (e.g., 17)", 0, 120, int(r["cut_2"]), 1, key="age_cut_2__age")
                cut_3 = c3.number_input("Upper limit group 3 (e.g., 24)", 0, 120, int(r["cut_3"]), 1, key="age_cut_3__age")
                cut_4 = c4.number_input("Upper limit group 4 (e.g., 34)", 0, 120, int(r["cut_4"]), 1, key="age_cut_4__age")

                c5, c6, c7 = st.columns(3)
                cut_5 = c5.number_input("Upper limit group 5 (e.g., 44)", 0, 120, int(r["cut_5"]), 1, key="age_cut_5__age")
                cut_6 = c6.number_input("Upper limit group 6 (e.g., 54)", 0, 120, int(r["cut_6"]), 1, key="age_cut_6__age")
                cut_7 = c7.number_input("Upper limit group 7 (e.g., 65)", 0, 120, int(r["cut_7"]), 1, key="age_cut_7__age")

                apply_btn = st.form_submit_button("✅ Apply age ranges (Age Group Analysis)")
                if apply_btn:
                    new_ranges = {
                        "under_1": int(under_1),
                        "cut_2": int(cut_2),
                        "cut_3": int(cut_3),
                        "cut_4": int(cut_4),
                        "cut_5": int(cut_5),
                        "cut_6": int(cut_6),
                        "cut_7": int(cut_7),
                    }
                    ok, msg = validate_ranges(new_ranges)
                    if not ok:
                        st.error(msg)
                    else:
                        st.session_state.age_ranges_age = new_ranges
                        st.success("Applied. Age Group Analysis updated.")
                        st.rerun()

        r = st.session_state.age_ranges_age
        under_1, cut_2, cut_3, cut_4, cut_5, cut_6, cut_7 = (
            r["under_1"],
            r["cut_2"],
            r["cut_3"],
            r["cut_4"],
            r["cut_5"],
            r["cut_6"],
            r["cut_7"],
        )

        age_labels = [
            f"Under {under_1}",
            f"{under_1}-{cut_2}",
            f"{cut_2+1}-{cut_3}",
            f"{cut_3+1}-{cut_4}",
            f"{cut_4+1}-{cut_5}",
            f"{cut_5+1}-{cut_6}",
            f"{cut_6+1}-{cut_7}",
            f"{cut_7+1}+",
        ]
        order = age_labels.copy()

        def get_age_group_editable(age: int) -> str:
            if age < under_1:
                return age_labels[0]
            if age <= cut_2:
                return age_labels[1]
            if age <= cut_3:
                return age_labels[2]
            if age <= cut_4:
                return age_labels[3]
            if age <= cut_5:
                return age_labels[4]
            if age <= cut_6:
                return age_labels[5]
            if age <= cut_7:
                return age_labels[6]
            return age_labels[7]

        if merged_base.empty:
            st.warning("No age-group stats (likely no matches).")
        else:
            tmp = merged_base.copy()
            tmp["Age Group"] = tmp["Age"].apply(get_age_group_editable)

            age_group_df = tmp.groupby("Age Group", as_index=False).agg(
                Users=("rid_last8", "nunique"),
                **{"Total Recharges": ("rid_last8", "size"), "Total Amount (Nu)": ("Amount", "sum")},
            )

            if not age_group_df.empty:
                age_group_df["Total Amount (Nu)"] = age_group_df["Total Amount (Nu)"].round(2)
                age_group_df["Avg Amount (Nu)"] = (age_group_df["Total Amount (Nu)"] / age_group_df["Total Recharges"]).round(2)
                age_group_df["__ord"] = age_group_df["Age Group"].apply(lambda x: order.index(x) if x in order else 999)
                age_group_df = age_group_df.sort_values("__ord").drop(columns="__ord")

            st.dataframe(age_group_df.reset_index(drop=True), use_container_width=True, hide_index=True)

            fig_age_rech = px.bar(
                age_group_df,
                x="Age Group",
                y="Total Recharges",
                title=f"Total Recharges by Age Group — {period_label}",
                labels={"Age Group": "Age Group", "Total Recharges": "Total Recharges"},
                category_orders={"Age Group": order},
                text="Total Recharges",
            )
            fig_age_rech.update_layout(template="plotly_white")
            add_bar_labels(fig_age_rech, kind="count")
            st.plotly_chart(fig_age_rech, use_container_width=True)

            fig_age_amt = px.bar(
                age_group_df,
                x="Age Group",
                y="Total Amount (Nu)",
                title=f"Total Revenue (Nu) by Age Group — {period_label}",
                labels={"Age Group": "Age Group", "Total Amount (Nu)": "Total Revenue (Nu)"},
                category_orders={"Age Group": order},
                text="Total Amount (Nu)",
            )
            fig_age_amt.update_layout(template="plotly_white")
            add_bar_labels(fig_age_amt, kind="money")
            st.plotly_chart(fig_age_amt, use_container_width=True)

    # =========================
    # Plan Distribution
    # =========================
    with tab_plans:
        st.subheader(f"Plan Usage Distribution by Age Group — {period_label}")

        # ✅ CHANGED TITLE (as requested)
        with st.expander("Edit Age Group Ranges", expanded=False):
            with st.form("age_group_form_plan", clear_on_submit=False):
                r = st.session_state.age_ranges_plan

                c1, c2, c3, c4 = st.columns(4)
                under_1_new = c1.number_input("Under (group 1)", 0, 120, int(r["under_1"]), 1, key="age_under_1__plan")
                cut_2_new = c2.number_input("Upper limit group 2", 0, 120, int(r["cut_2"]), 1, key="age_cut_2__plan")
                cut_3_new = c3.number_input("Upper limit group 3", 0, 120, int(r["cut_3"]), 1, key="age_cut_3__plan")
                cut_4_new = c4.number_input("Upper limit group 4", 0, 120, int(r["cut_4"]), 1, key="age_cut_4__plan")

                c5, c6, c7 = st.columns(3)
                cut_5_new = c5.number_input("Upper limit group 5", 0, 120, int(r["cut_5"]), 1, key="age_cut_5__plan")
                cut_6_new = c6.number_input("Upper limit group 6", 0, 120, int(r["cut_6"]), 1, key="age_cut_6__plan")
                cut_7_new = c7.number_input("Upper limit group 7", 0, 120, int(r["cut_7"]), 1, key="age_cut_7__plan")

                apply_btn = st.form_submit_button("✅ Apply age ranges (Plan Distribution)")
                if apply_btn:
                    new_ranges = {
                        "under_1": int(under_1_new),
                        "cut_2": int(cut_2_new),
                        "cut_3": int(cut_3_new),
                        "cut_4": int(cut_4_new),
                        "cut_5": int(cut_5_new),
                        "cut_6": int(cut_6_new),
                        "cut_7": int(cut_7_new),
                    }
                    ok, msg = validate_ranges(new_ranges)
                    if not ok:
                        st.error(msg)
                    else:
                        st.session_state.age_ranges_plan = new_ranges
                        st.success("Applied. Plan Distribution updated.")
                        st.rerun()

        r = st.session_state.age_ranges_plan
        under_1, cut_2, cut_3, cut_4, cut_5, cut_6, cut_7 = (
            r["under_1"], r["cut_2"], r["cut_3"], r["cut_4"], r["cut_5"], r["cut_6"], r["cut_7"]
        )

        age_labels_plans = [
            f"Under {under_1}",
            f"{under_1}-{cut_2}",
            f"{cut_2+1}-{cut_3}",
            f"{cut_3+1}-{cut_4}",
            f"{cut_4+1}-{cut_5}",
            f"{cut_5+1}-{cut_6}",
            f"{cut_6+1}-{cut_7}",
            f"{cut_7+1}+",
        ]
        order_plans = age_labels_plans.copy()

        def get_age_group_editable_plans(age: int) -> str:
            if age < under_1:
                return age_labels_plans[0]
            if age <= cut_2:
                return age_labels_plans[1]
            if age <= cut_3:
                return age_labels_plans[2]
            if age <= cut_4:
                return age_labels_plans[3]
            if age <= cut_5:
                return age_labels_plans[4]
            if age <= cut_6:
                return age_labels_plans[5]
            if age <= cut_7:
                return age_labels_plans[6]
            return age_labels_plans[7]

        if merged_base.empty:
            st.warning("No plan distribution data (likely no matches).")
        else:
            tmp2 = merged_base.copy()
            tmp2["Age Group"] = tmp2["Age"].apply(get_age_group_editable_plans)

            if "Plan Bucket" not in tmp2.columns:
                tmp2["Plan Bucket"] = tmp2.apply(lambda rr: map_recharge_bucket(rr["Amount"], rr.get("_dt", None)), axis=1)

            plan_by_age_df = tmp2.groupby(["Age Group", "Plan Bucket"], as_index=False).agg(
                **{"Recharge Count": ("Plan Bucket", "size")}
            )

            popular = (
                plan_by_age_df.groupby("Plan Bucket", as_index=False)["Recharge Count"]
                .sum()
                .sort_values("Recharge Count", ascending=False)
                .reset_index(drop=True)
            )
            if not popular.empty:
                popular.insert(0, "Sl.No", range(1, len(popular) + 1))

            st.subheader("Most Popular Buckets")
            st.dataframe(popular, use_container_width=True, hide_index=True)

            ranked_order = popular["Plan Bucket"].tolist() if not popular.empty else bucket_order

            cA, cB = st.columns([1, 1])
            with cA:
                view_mode = st.radio(
                    "Chart View",
                    ["Horizontal (Recommended)", "Stacked (Vertical)"],
                    horizontal=True,
                    key="plan_view_mode__main",
                )
            with cB:
                top_n_show = st.slider(
                    "Show Top N Plans (by total count)",
                    min_value=5,
                    max_value=min(30, len(ranked_order)) if ranked_order else 10,
                    value=min(12, len(ranked_order)) if ranked_order else 10,
                    step=1,
                    key="plan_top_n__main",
                )

            top_plans_to_show = ranked_order[:top_n_show] if ranked_order else bucket_order[:top_n_show]
            plan_by_age_top = plan_by_age_df[plan_by_age_df["Plan Bucket"].isin(top_plans_to_show)].copy()
            top_order = [p for p in ranked_order if p in top_plans_to_show] if ranked_order else top_plans_to_show

            if view_mode == "Horizontal (Recommended)":
                fig_stack = px.bar(
                    plan_by_age_top,
                    x="Recharge Count",
                    y="Plan Bucket",
                    color="Age Group",
                    barmode="stack",
                    orientation="h",
                    category_orders={"Plan Bucket": top_order[::-1], "Age Group": order_plans},
                    title=f"Recharge Count by Data Plan (Top {top_n_show}, stacked by Age Group) — {period_label}",
                    labels={"Plan Bucket": "Data Plan", "Recharge Count": "Recharge Count", "Age Group": "Age Group"},
                )
                fig_stack.update_layout(
                    template="plotly_white",
                    height=850,
                    font=dict(size=14),
                    legend_title_text="Age Group",
                    margin=dict(t=80, l=10, r=10, b=10),
                )
                fig_stack.update_traces(
                    texttemplate="%{x:,}",
                    textposition="inside",
                    insidetextanchor="middle",
                    cliponaxis=False,
                    hovertemplate=(
                        "Plan=%{y}<br>"
                        "Age Group=%{fullData.name}<br>"
                        "Recharge Count=%{x:,}<extra></extra>"
                    ),
                )
            else:
                fig_stack = px.bar(
                    plan_by_age_top,
                    x="Plan Bucket",
                    y="Recharge Count",
                    color="Age Group",
                    barmode="stack",
                    text="Recharge Count",
                    category_orders={"Plan Bucket": top_order, "Age Group": order_plans},
                    title=f"Recharge Count by Data Plan (Top {top_n_show}, stacked by Age Group) — {period_label}",
                    labels={"Plan Bucket": "Data Plan", "Recharge Count": "Recharge Count", "Age Group": "Age Group"},
                )
                fig_stack.update_layout(
                    template="plotly_white",
                    xaxis_tickangle=-45,
                    height=700,
                    font=dict(size=14),
                    legend_title_text="Age Group",
                    margin=dict(t=80),
                )
                fig_stack.update_traces(
                    textposition="inside",
                    texttemplate="%{text:,}",
                    insidetextanchor="middle",
                    cliponaxis=False,
                )
                fig_stack.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")

            st.plotly_chart(fig_stack, use_container_width=True)

            st.markdown("### Zoom View (Small Plans)")
            plan_totals = (
                plan_by_age_df.groupby("Plan Bucket", as_index=False)["Recharge Count"]
                .sum()
                .sort_values("Recharge Count", ascending=False)
            )

            TOP_N = 5
            small_plans = plan_totals["Plan Bucket"].iloc[TOP_N:].tolist()
            if "Monthly Plan 777" in plan_totals["Plan Bucket"].values and "Monthly Plan 777" not in small_plans:
                small_plans.append("Monthly Plan 777")
            if len(small_plans) == 0:
                small_plans = plan_totals.tail(10)["Plan Bucket"].tolist()

            zoom_df = plan_by_age_df[plan_by_age_df["Plan Bucket"].isin(small_plans)].copy()
            zoom_order = [p for p in ranked_order if p in small_plans] or small_plans

            fig_zoom = px.bar(
                zoom_df,
                x="Recharge Count",
                y="Plan Bucket",
                color="Age Group",
                barmode="stack",
                orientation="h",
                category_orders={"Plan Bucket": zoom_order[::-1], "Age Group": order_plans},
                title=f"Recharge Count by Data Plan (Zoomed: excluding top {TOP_N}) — {period_label}",
                labels={"Plan Bucket": "Data Plan", "Recharge Count": "Recharge Count", "Age Group": "Age Group"},
            )
            fig_zoom.update_layout(
                template="plotly_white",
                height=750,
                font=dict(size=14),
                legend_title_text="Age Group",
                margin=dict(t=80, l=10, r=10, b=10),
            )
            fig_zoom.update_traces(
                texttemplate="%{x:,}",
                textposition="inside",
                insidetextanchor="middle",
                cliponaxis=False,
                hovertemplate=(
                    "Plan=%{y}<br>"
                    "Age Group=%{fullData.name}<br>"
                    "Recharge Count=%{x:,}<extra></extra>"
                ),
            )
            st.plotly_chart(fig_zoom, use_container_width=True)

            with st.expander("Show zoomed plan list", expanded=False):
                st.write(zoom_order)

    # =========================
    # Season-wise Unlimited
    # =========================
    with tab_season:
        st.subheader("Season-wise Unlimited Late Night Plans")

        if recharge_date_col is None:
            st.warning("Recharge date column is required for season analysis.")
        else:
            season_map = {
                12: "Winter", 1: "Winter", 2: "Winter",
                3: "Spring", 4: "Spring", 5: "Spring",
                6: "Summer", 7: "Summer", 8: "Summer",
                9: "Autumn", 10: "Autumn", 11: "Autumn",
            }
            season_order = ["Winter", "Spring", "Summer", "Autumn"]

            tmpu = rech.dropna(subset=["_dt"]).copy()
            tmpu = tmpu[tmpu["Plan Bucket"].str.contains("Late Night", na=False)].copy()

            if tmpu.empty:
                st.info("No Unlimited Late Night plan records found.")
            else:
                tmpu["_season"] = tmpu["_dt"].dt.month.map(season_map)
                tmpu["_month_label2"] = tmpu["_dt"].dt.to_period("M").dt.to_timestamp().dt.strftime("%b %Y")
                tmpu["_month_ts2"] = tmpu["_dt"].dt.to_period("M").dt.to_timestamp()

                season_df = tmpu.groupby(["_season", "Plan Bucket"], as_index=False).agg(
                    Recharges=("Amount", "size"),
                    Revenue=("Amount", "sum"),
                )
                season_df["Revenue"] = season_df["Revenue"].round(2)
                season_df["_season"] = pd.Categorical(season_df["_season"], categories=season_order, ordered=True)
                season_df = season_df.sort_values(["_season", "Plan Bucket"])

                season_table = season_df.rename(columns={"_season": "Season"}).copy()
                st.dataframe(season_table, use_container_width=True, hide_index=True)

                figS1 = px.bar(
                    season_df,
                    x="_season",
                    y="Recharges",
                    color="Plan Bucket",
                    barmode="group",
                    title="Unlimited Late Night Recharges by Season",
                    text="Recharges",
                    category_orders={"_season": season_order},
                )
                figS1.update_layout(template="plotly_white", xaxis_title="Season")
                add_bar_labels(figS1, kind="count")
                st.plotly_chart(figS1, use_container_width=True)

                figS2 = px.bar(
                    season_df,
                    x="_season",
                    y="Revenue",
                    color="Plan Bucket",
                    barmode="group",
                    title="Unlimited Late Night Revenue by Season (Nu)",
                    text="Revenue",
                    category_orders={"_season": season_order},
                )
                figS2.update_layout(template="plotly_white", xaxis_title="Season")
                add_bar_labels(figS2, kind="money")
                st.plotly_chart(figS2, use_container_width=True)

                with st.expander("Show month breakdown inside each season (optional)", expanded=False):
                    season_month_df = tmpu.groupby(
                        ["_season", "_month_ts2", "_month_label2", "Plan Bucket"], as_index=False
                    ).agg(
                        Recharges=("Amount", "size"),
                        Revenue=("Amount", "sum"),
                    )
                    season_month_df["Revenue"] = season_month_df["Revenue"].round(2)
                    season_month_df["_season"] = pd.Categorical(
                        season_month_df["_season"], categories=season_order, ordered=True
                    )
                    season_month_df = season_month_df.sort_values(["_season", "_month_ts2", "Plan Bucket"])
                    season_month_df = season_month_df.drop(columns=["_month_ts2"])

                    season_month_table = season_month_df.rename(
                        columns={"_season": "Season", "_month_label2": "Month"}
                    ).copy()
                    st.dataframe(season_month_table, use_container_width=True, hide_index=True)

    # =========================
    # Expiry & Extension
    # =========================
    with tab_expiry:
        st.subheader("Expiry & Extension (Renewal Behaviour)")

        if merged_base.empty:
            st.warning("No matched records for expiry/extension analysis.")
            st.stop()

        tmpx = merged_base.copy()

        if "_dt" not in tmpx.columns:
            st.warning("No recharge date found (_dt). Ensure recharge date column is detected.")
            st.stop()

        tmpx = tmpx.dropna(subset=["_dt"]).copy()
        if tmpx.empty:
            st.warning("No valid recharge dates found for expiry/extension analysis.")
            st.stop()

        validity_map_days = {
            "Daily": 1,
            "Weekly": 7,
            "Monthly": 30,
            "Bi-Monthly": 60,
            "Quarterly": 90,
            "Quaterly": 90,
        }
        validity_df = pd.DataFrame(
            [
                ("Daily Plan", 1),
                ("Weekly Plan", 7),
                ("Monthly Plan", 30),
                ("Bi-Monthly Plan", 60),
                ("Quaterly Plan", 90),
                ("Daily Unlimited Late Night", 1),
                ("Weekly Unlimited Late Night", 7),
            ],
            columns=["Plan Type", "Validity (Days)"],
        )
        st.dataframe(validity_df, use_container_width=True, hide_index=True)

        # ✅ CHANGED TITLE (as requested)
        st.markdown("### Edit Age Group Ranges")
        with st.expander("Edit Age Group Ranges", expanded=False):
            with st.form("age_group_form_expiry", clear_on_submit=False):
                rE = st.session_state.age_ranges_expiry

                c1, c2, c3, c4 = st.columns(4)
                under_1_e = c1.number_input("Under (group 1)", 0, 120, int(rE["under_1"]), 1, key="age_under_1__exp")
                cut_2_e = c2.number_input("Upper limit group 2", 0, 120, int(rE["cut_2"]), 1, key="age_cut_2__exp")
                cut_3_e = c3.number_input("Upper limit group 3", 0, 120, int(rE["cut_3"]), 1, key="age_cut_3__exp")
                cut_4_e = c4.number_input("Upper limit group 4", 0, 120, int(rE["cut_4"]), 1, key="age_cut_4__exp")

                c5, c6, c7 = st.columns(3)
                cut_5_e = c5.number_input("Upper limit group 5", 0, 120, int(rE["cut_5"]), 1, key="age_cut_5__exp")
                cut_6_e = c6.number_input("Upper limit group 6", 0, 120, int(rE["cut_6"]), 1, key="age_cut_6__exp")
                cut_7_e = c7.number_input("Upper limit group 7", 0, 120, int(rE["cut_7"]), 1, key="age_cut_7__exp")

                apply_e = st.form_submit_button("✅ Apply age ranges (Expiry & Extension)")
                if apply_e:
                    new_ranges = {
                        "under_1": int(under_1_e),
                        "cut_2": int(cut_2_e),
                        "cut_3": int(cut_3_e),
                        "cut_4": int(cut_4_e),
                        "cut_5": int(cut_5_e),
                        "cut_6": int(cut_6_e),
                        "cut_7": int(cut_7_e),
                    }
                    ok, msg = validate_ranges(new_ranges)
                    if not ok:
                        st.error(msg)
                    else:
                        st.session_state.age_ranges_expiry = new_ranges
                        st.success("Applied. Expiry tab updated.")
                        st.rerun()

        def infer_validity_days_from_bucket(bucket: str) -> int:
            b = str(bucket).lower()
            if "bi-monthly" in b or "bimonthly" in b:
                return validity_map_days["Bi-Monthly"]
            if "quarterly" in b or "quaterly" in b:
                return validity_map_days["Quarterly"]
            if "monthly" in b:
                return validity_map_days["Monthly"]
            if "weekly" in b:
                return validity_map_days["Weekly"]
            if "daily" in b:
                return validity_map_days["Daily"]
            return 0

        if "Plan Bucket" not in tmpx.columns:
            tmpx["Plan Bucket"] = tmpx.apply(lambda rr: map_recharge_bucket(rr["Amount"], rr.get("_dt", None)), axis=1)

        tmpx["Validity Days"] = tmpx["Plan Bucket"].apply(infer_validity_days_from_bucket)
        tmpx = tmpx[tmpx["Validity Days"] > 0].copy()

        if tmpx.empty:
            st.warning("Could not infer validity days from Plan Bucket. Check bucket names.")
            st.stop()

        tmpx["_dt_date"] = tmpx["_dt"].dt.floor("D")
        tmpx["Expiry Date"] = (
            tmpx["_dt_date"]
            + pd.to_timedelta(tmpx["Validity Days"] - 1, unit="D")
            + pd.Timedelta(hours=23, minutes=59, seconds=59)
        )

        tmpx = tmpx.sort_values(["rid_last8", "_dt"])
        tmpx["Next Recharge Date"] = tmpx.groupby("rid_last8")["_dt"].shift(-1)
        tmpx["Has Next Recharge"] = tmpx["Next Recharge Date"].notna()

        def classify_renewal_short(row) -> str:
            if not row["Has Next Recharge"]:
                return "No Next Recharge"
            next_dt = row["Next Recharge Date"]
            exp_dt = row["Expiry Date"]
            if pd.isna(next_dt) or pd.isna(exp_dt):
                return "No Next Recharge"
            if next_dt.date() == exp_dt.date():
                return "On-time"
            if next_dt < exp_dt:
                return "Early"
            return "Late"

        tmpx["Renewal Type"] = tmpx.apply(classify_renewal_short, axis=1)

        rE = st.session_state.age_ranges_expiry
        under_1, cut_2, cut_3, cut_4, cut_5, cut_6, cut_7 = (
            rE["under_1"], rE["cut_2"], rE["cut_3"], rE["cut_4"], rE["cut_5"], rE["cut_6"], rE["cut_7"]
        )

        age_labels_exp = [
            f"Under {under_1}",
            f"{under_1}-{cut_2}",
            f"{cut_2+1}-{cut_3}",
            f"{cut_3+1}-{cut_4}",
            f"{cut_4+1}-{cut_5}",
            f"{cut_5+1}-{cut_6}",
            f"{cut_6+1}-{cut_7}",
            f"{cut_7+1}+",
        ]
        age_order = age_labels_exp.copy()

        def get_age_group_editable_exp(age: int) -> str:
            if age < under_1:
                return age_labels_exp[0]
            if age <= cut_2:
                return age_labels_exp[1]
            if age <= cut_3:
                return age_labels_exp[2]
            if age <= cut_4:
                return age_labels_exp[3]
            if age <= cut_5:
                return age_labels_exp[4]
            if age <= cut_6:
                return age_labels_exp[5]
            if age <= cut_7:
                return age_labels_exp[6]
            return age_labels_exp[7]

        tmpx["Age Group"] = tmpx["Age"].apply(get_age_group_editable_exp)

        st.markdown("### Renewal Behaviour by Age Group")
        renewal_order = ["Early", "Late", "On-time"]

        age_renew_table = (
            tmpx[tmpx["Has Next Recharge"]]
            .groupby(["Age Group", "Renewal Type"], as_index=False)
            .agg(Recharge_Count=("rid_last8", "size"), Unique_Customers=("rid_last8", "nunique"))
        )

        if age_renew_table.empty:
            st.info("No renewal comparison available (no next recharge records).")
        else:
            age_renew_table["Renewal Type"] = pd.Categorical(age_renew_table["Renewal Type"], categories=renewal_order, ordered=True)
            age_renew_table["Age Group"] = pd.Categorical(age_renew_table["Age Group"], categories=age_order, ordered=True)
            age_renew_table = age_renew_table.sort_values(["Age Group", "Renewal Type"])

            fig_age = px.bar(
                age_renew_table,
                x="Age Group",
                y="Recharge_Count",
                color="Renewal Type",
                barmode="stack",
                text="Unique_Customers",
                category_orders={"Age Group": age_order, "Renewal Type": renewal_order},
                title="Renewal Behaviour by Age Group",
                labels={"Recharge_Count": "Recharge Count", "Age Group": "Age Group"},
            )
            fig_age.update_layout(template="plotly_white", legend_title_text="Renewal Type")
            fig_age.update_traces(
                textposition="inside",
                texttemplate="%{text:,}",
                insidetextanchor="middle",
                cliponaxis=False,
                hovertemplate=(
                    "Renewal Type=%{fullData.name}<br>"
                    "Age Group=%{x}<br>"
                    "Recharge Count=%{y:,}<br>"
                    "Unique Customers=%{text:,}<extra></extra>"
                ),
            )
            fig_age.update_layout(
                xaxis_title="Age Group",
                yaxis_title="Recharge Count",
                uniformtext_minsize=9,
                uniformtext_mode="hide",
                margin=dict(t=70),
            )
            st.plotly_chart(fig_age, use_container_width=True)
            st.caption("Numbers inside bars represent Unique Customers")

        st.markdown("### Monthly Renewal Type Distribution (100%)")

        tmpx["_month_ts4"] = tmpx["_dt"].dt.to_period("M").dt.to_timestamp()
        tmpx["Month"] = tmpx["_month_ts4"].dt.strftime("%b %Y")

        month_df = (
            tmpx[tmpx["Has Next Recharge"]]
            .groupby(["_month_ts4", "Month", "Renewal Type"], as_index=False)
            .agg(
                Recharge_Count=("rid_last8", "size"),
                Unique_Customers=("rid_last8", "nunique"),
            )
        )

        if month_df.empty:
            st.info("No monthly distribution available (no next recharge records).")
        else:
            month_df["Renewal Type"] = pd.Categorical(month_df["Renewal Type"], categories=renewal_order, ordered=True)
            month_df = month_df.sort_values(["_month_ts4", "Renewal Type"])

            month_df["Total"] = month_df.groupby("_month_ts4")["Recharge_Count"].transform("sum")
            month_df["Percentage"] = (month_df["Recharge_Count"] / month_df["Total"]) * 100
            month_df = month_df.drop(columns=["Total"])

            month_table = month_df.drop(columns=["_month_ts4"]).copy()
            st.dataframe(month_table, use_container_width=True, hide_index=True)

            fig_month = px.bar(
                month_df,
                y="Month",
                x="Percentage",
                color="Renewal Type",
                orientation="h",
                barmode="stack",
                category_orders={"Renewal Type": renewal_order},
                title="Monthly Renewal Type Distribution (100%)",
                labels={"Percentage": "Percentage (%)", "Month": "Month"},
                custom_data=["Recharge_Count", "Unique_Customers"],
                text="Percentage",
            )

            fig_month.update_traces(
                texttemplate="%{x:.1f}%",
                textposition="inside",
                insidetextanchor="middle",
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Renewal Type: %{fullData.name}<br>"
                    "Percentage: %{x:.1f}%<br>"
                    "Recharge Count: %{customdata[0]:,}<br>"
                    "Unique Customers: %{customdata[1]:,}"
                    "<extra></extra>"
                ),
            )

            fig_month.update_layout(
                template="plotly_white",
                xaxis_title="Percentage (%)",
                yaxis_title="Month",
                legend_title_text="Renewal Type",
                margin=dict(t=70),
            )
            st.plotly_chart(fig_month, use_container_width=True)
