# data_plan.py
import io
import re
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
    st.title("Data Plan Usage by Age Group")

    # -----------------------------
    # Helpers
    # -----------------------------
    def normalize_source_name(src: str) -> str:
        """
        Merge ALL variants into the base source name (remove trailing numbers).

        Examples:
          'BOB1' / 'BOB 1' / 'BOB-1' / 'BOB_1' / 'BOB(1)' -> 'BOB'
          'mypay(1)' / 'mypay 2' / 'mypay-3' -> 'mypay'
          'RMA2' / 'RMA_2' -> 'RMA'
        """
        if src is None:
            return "Unknown"

        s = str(src).strip()
        s = re.sub(r"\s+", " ", s).strip()

        # remove trailing bracket number: "mypay(1)" -> "mypay"
        s = re.sub(r"\(\s*\d+\s*\)\s*$", "", s)

        # normalize separators: "_" "-" -> space
        s = re.sub(r"[_\-]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()

        # remove trailing digits: "BOB 1" or "BOB1" -> "BOB"
        s = re.sub(r"\s*\d+\s*$", "", s).strip()

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
        # Kept for compatibility (not used in Plan Distribution anymore)
        s = clean_plan_name(x)
        plan_map = {
            "Newpackage": "New Package",
            "New Package": "New Package",
        }
        return plan_map.get(s, s)

    def add_bar_labels(fig, kind="count"):
        if kind == "money":
            fig.update_traces(textposition="outside", texttemplate="Nu %{text:,. hooking}")
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
            "Recharge_date", "RECHARGE_DATE", "recharge_date",
            "Recharge_Date",
            "Transaction_Date", "TRANSACTION_DATE", "transaction_date",
            "Date", "DATE", "date",
            "Txn_Date", "TXN_DATE", "txn_date",
            "Recharge_Time", "RECHARGE_TIME", "recharge_time",
            "Time", "TIME", "time",
        ]
        return pick_first_existing_col(df, candidates)

    # ✅ Plan/Talktime bucketing based ONLY on Amount
    def map_recharge_bucket(amount_value) -> str:
        """
        ONLY these are treated as Plans:
        Daily Plan 19
        Weekly Plan 49
        Monthly Plan 99/199/299/499/599/699/777/999/1,299
        Bi-Monthly Plan 1,499 / 1,999
        Quaterly Plan 2,499 / 2,999

        Everything else -> Talktime
        """
        try:
            amt = float(amount_value)
        except Exception:
            return "Talktime"

        amt_int = int(round(amt))

        daily = {19}
        weekly = {49}
        monthly = {99, 199, 299, 499, 599, 699, 777, 999, 1299}
        bi_monthly = {1499, 1999}
        quaterly = {2499, 2999}

        def fmt(n: int) -> str:
            return f"{n:,}"

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

    # -----------------------------
    # Upload section (SIDEBAR)
    # -----------------------------
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
                recharge_parts.append(df)
            except Exception as e:
                st.warning(f"Skipped {f.name} (could not read): {e}")

        if not recharge_parts:
            st.error("No recharge files could be read.")
            st.stop()

        recharge_df = pd.concat(recharge_parts, ignore_index=True)

    # -----------------------------
    # Detect date column + build period_label
    # -----------------------------
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

    # -----------------------------
    # Column detection
    # -----------------------------
    service_id_col = pick_first_existing_col(customer_df, ["Service_ID", "SERVICE_ID", "service_id"])
    dob_col = pick_first_existing_col(customer_df, ["date_of_birth", "Date_of_Birth", "DATE_OF_BIRTH", "DOB", "dob"])
    plan_col = pick_first_existing_col(customer_df, ["rate_plan_name", "Rate_Plan_Name", "RATE_PLAN_NAME", "plan", "Plan"])

    recharge_num_col = pick_first_existing_col(recharge_df, ["RECHARGE_NUMBER", "Recharge_Number", "recharge_number"])
    amount_col = pick_first_existing_col(
        recharge_df,
        ["Recharge_Amount(Nu)", "Recharge_Amount(Nu) ", "Recharge_Amount", "recharge_amount", "Amount", "amount"]
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

    # -----------------------------
    # Build BASE tables ONCE
    # -----------------------------
    with st.spinner("Processing and matching..."):
        # Customer base
        cust = customer_df[[service_id_col, dob_col, plan_col]].copy()
        cust["sid_raw"] = cust[service_id_col].astype(str).str.strip()
        cust = cust[~cust["sid_raw"].str.lower().isin(["nan", "none", ""])].copy()

        cust["Age"] = cust[dob_col].apply(calculate_age)
        cust["Plan"] = cust[plan_col].apply(standardize_plan)
        cust["sid_last8"] = cust["sid_raw"].apply(lambda x: last_n_digits(x, 8))
        cust = cust[cust["sid_last8"] != ""].copy()

        # Recharge base
        cols = [recharge_num_col, amount_col, "source"]
        if recharge_date_col:
            cols.append(recharge_date_col)

        rech = recharge_df[cols].copy()
        rech["rid_raw"] = rech[recharge_num_col].astype(str).str.strip()
        rech = rech[~rech["rid_raw"].str.lower().isin(["nan", "none", ""])].copy()
        rech["rid_last8"] = rech["rid_raw"].apply(lambda x: last_n_digits(x, 8))
        rech = rech[rech["rid_last8"] != ""].copy()

        rech["Amount"] = pd.to_numeric(rech[amount_col], errors="coerce").fillna(0.0)
        rech["Plan Bucket"] = rech["Amount"].apply(map_recharge_bucket)

        # date + month label (for month-wise charts)
        if recharge_date_col:
            rech["_dt"] = pd.to_datetime(rech[recharge_date_col], errors="coerce", dayfirst=True)
            rech["_month"] = rech["_dt"].dt.to_period("M").dt.to_timestamp()
            rech["_month_label"] = rech["_month"].dt.strftime("%b %Y")
        else:
            rech["_dt"] = pd.NaT
            rech["_month"] = pd.NaT
            rech["_month_label"] = "Unknown"

        merged_base = rech.merge(
            cust[["sid_last8", "Age", "Plan"]],
            left_on="rid_last8",
            right_on="sid_last8",
            how="inner",
        )

        total_rev = float(rech["Amount"].sum())
        total_recharges = int(len(rech))
        matched = int(len(merged_base))

        # Source totals
        source_df = (
            rech.groupby("source", as_index=False)
            .agg(
                **{
                    "Total Recharges": ("source", "size"),
                    "Total Amount (Nu)": ("Amount", "sum"),
                }
            )
        )
        if not source_df.empty:
            source_df["Total Amount (Nu)"] = source_df["Total Amount (Nu)"].round(2)
            source_df["Avg Amount (Nu)"] = (source_df["Total Amount (Nu)"] / source_df["Total Recharges"]).round(2)
            source_df = source_df.rename(columns={"source": "Source"}).sort_values("Total Amount (Nu)", ascending=False)
        else:
            source_df = pd.DataFrame(columns=["Source", "Total Recharges", "Total Amount (Nu)", "Avg Amount (Nu)"])

        # Month-wise (for the “single source, multiple months” case)
        month_source_df = pd.DataFrame()
        if recharge_date_col:
            month_source_df = (
                rech.dropna(subset=["_month"])
                .groupby(["source", "_month", "_month_label"], as_index=False)
                .agg(
                    **{
                        "Total Recharges": ("Amount", "size"),
                        "Total Amount (Nu)": ("Amount", "sum"),
                    }
                )
            )
            if not month_source_df.empty:
                month_source_df["Total Amount (Nu)"] = month_source_df["Total Amount (Nu)"].round(2)
                month_source_df["Avg Amount (Nu)"] = (month_source_df["Total Amount (Nu)"] / month_source_df["Total Recharges"]).round(2)
                month_source_df = month_source_df.sort_values(["source", "_month"])

    # -----------------------------
    # Tabs
    # -----------------------------
    tab_overview, tab_source, tab_age, tab_plans = st.tabs(
        ["Overview", "Source Analysis", "Age Group Analysis", "Plan Distribution"]
    )

    # -----------------------------
    # Overview tab
    # -----------------------------
    with tab_overview:
        st.subheader(f"Overview — {period_label}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Customers", f"{len(customer_df):,}")
        m2.metric("Total Recharges", f"{total_recharges:,}")
        m3.metric("Total Revenue (Nu)", format_currency_short(total_rev))
        m4.metric("Avg Recharge (Nu)", f"{(total_rev/total_recharges if total_recharges else 0):,.2f}")

        with st.expander("Debug: Matching Information", expanded=False):
            st.write(f"Matched recharges: **{matched:,}** / {total_recharges:,}")
            st.write("Source rule used: **base source name** (e.g., 'BOB1/BOB_1/BOB-1/BOB(1)' → 'BOB').")
            if recharge_date_col and dt_series is not None:
                st.write(f"Date column detected: **{recharge_date_col}** (period label auto, dayfirst=True)")
            else:
                st.write("No valid date column detected → period label is 'All Periods'.")

    # -----------------------------
    # Source tab
    # -----------------------------
    with tab_source:
        st.subheader("Revenue by Source Area")

        unique_sources = list(pd.Series(rech["source"].dropna().unique()).astype(str))
        n_sources = len(unique_sources)

        # ✅ If user uploads ONE source but multiple months -> show month comparison bars (not merged)
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
            # ✅ Default case (many sources OR only 1 month) -> keep aggregated by Source
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

    # -----------------------------
    # Age Group Analysis tab
    # -----------------------------
    with tab_age:
        st.subheader(f"Age Group Statistics — {period_label}")

        if "age_ranges" not in st.session_state:
            st.session_state.age_ranges = {
                "under_1": 15,
                "cut_2": 17,
                "cut_3": 24,
                "cut_4": 34,
                "cut_5": 44,
                "cut_6": 54,
                "cut_7": 65,
            }

        with st.expander("Edit Age Group Ranges (click Apply to update)", expanded=False):
            with st.form("age_group_form", clear_on_submit=False):
                c1, c2, c3, c4 = st.columns(4)
                under_1 = c1.number_input("Under (group 1)", 0, 120, int(st.session_state.age_ranges["under_1"]), 1)
                cut_2 = c2.number_input("Upper limit group 2 (e.g., 17)", int(under_1), 120, int(st.session_state.age_ranges["cut_2"]), 1)
                cut_3 = c3.number_input("Upper limit group 3 (e.g., 24)", int(cut_2), 120, int(st.session_state.age_ranges["cut_3"]), 1)
                cut_4 = c4.number_input("Upper limit group 4 (e.g., 34)", int(cut_3), 120, int(st.session_state.age_ranges["cut_4"]), 1)

                c5, c6, c7 = st.columns(3)
                cut_5 = c5.number_input("Upper limit group 5 (e.g., 44)", int(cut_4), 120, int(st.session_state.age_ranges["cut_5"]), 1)
                cut_6 = c6.number_input("Upper limit group 6 (e.g., 54)", int(cut_5), 120, int(st.session_state.age_ranges["cut_6"]), 1)
                cut_7 = c7.number_input("Upper limit group 7 (e.g., 65)", int(cut_6), 120, int(st.session_state.age_ranges["cut_7"]), 1)

                apply_btn = st.form_submit_button("✅ Apply age ranges")
                if apply_btn:
                    st.session_state.age_ranges = {
                        "under_1": int(under_1),
                        "cut_2": int(cut_2),
                        "cut_3": int(cut_3),
                        "cut_4": int(cut_4),
                        "cut_5": int(cut_5),
                        "cut_6": int(cut_6),
                        "cut_7": int(cut_7),
                    }
                    st.success("Applied. Charts updated below.")

        under_1 = st.session_state.age_ranges["under_1"]
        cut_2 = st.session_state.age_ranges["cut_2"]
        cut_3 = st.session_state.age_ranges["cut_3"]
        cut_4 = st.session_state.age_ranges["cut_4"]
        cut_5 = st.session_state.age_ranges["cut_5"]
        cut_6 = st.session_state.age_ranges["cut_6"]
        cut_7 = st.session_state.age_ranges["cut_7"]

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

            age_group_df = (
                tmp.groupby("Age Group", as_index=False)
                .agg(
                    Users=("rid_last8", "nunique"),
                    **{
                        "Total Recharges": ("rid_last8", "size"),
                        "Total Amount (Nu)": ("Amount", "sum"),
                    },
                )
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

    # -----------------------------
    # Plan Distribution tab
    # -----------------------------
    with tab_plans:
        st.subheader(f"Plan Usage Distribution by Age Group — {period_label}")

        def get_age_group_fixed(age: int) -> str:
            if age < 15:
                return "Under 15"
            if age <= 17:
                return "15-17"
            if age <= 24:
                return "18-24"
            if age <= 34:
                return "25-34"
            if age <= 44:
                return "35-44"
            if age <= 54:
                return "45-54"
            if age <= 65:
                return "55-65"
            return "65+"

        fixed_order = ["Under 15", "15-17", "18-24", "25-34", "35-44", "45-54", "55-65", "65+"]

        if merged_base.empty:
            st.warning("No plan distribution data (likely no matches).")
        else:
            tmp2 = merged_base.copy()
            tmp2["Age Group"] = tmp2["Age"].apply(get_age_group_fixed)

            if "Plan Bucket" not in tmp2.columns:
                tmp2["Plan Bucket"] = tmp2["Amount"].apply(map_recharge_bucket)

            plan_by_age_df = (
                tmp2.groupby(["Age Group", "Plan Bucket"], as_index=False)
                .agg(**{"Recharge Count": ("Plan Bucket", "size")})
            )

            if not plan_by_age_df.empty:
                plan_by_age_df["Age__ord"] = plan_by_age_df["Age Group"].apply(
                    lambda x: fixed_order.index(x) if x in fixed_order else 999
                )
                plan_by_age_df["Bucket__ord"] = plan_by_age_df["Plan Bucket"].apply(
                    lambda x: bucket_order.index(x) if x in bucket_order else 999
                )
                plan_by_age_df = (
                    plan_by_age_df.sort_values(["Age__ord", "Bucket__ord"], ascending=[True, True])
                    .drop(columns=["Age__ord", "Bucket__ord"])
                )

            st.dataframe(plan_by_age_df.reset_index(drop=True), use_container_width=True, hide_index=True)

            # ✅ Most popular = rank by Recharge Count DESC
            popular = (
                plan_by_age_df.groupby("Plan Bucket", as_index=False)["Recharge Count"].sum()
                .sort_values("Recharge Count", ascending=False)
                .reset_index(drop=True)
            )
            if not popular.empty:
                popular.insert(0, "Rank", range(1, len(popular) + 1))

            st.subheader("Most Popular Buckets")
            st.dataframe(popular, use_container_width=True, hide_index=True)

            # Bar chart in the same ranked order
            ranked_order = popular["Plan Bucket"].tolist() if not popular.empty else bucket_order

            fig_pop = px.bar(
                popular,
                x="Plan Bucket",
                y="Recharge Count",
                title=f"Most Popular Buckets by Recharge Count — {period_label}",
                labels={"Plan Bucket": "Plan Bucket", "Recharge Count": "Recharge Count"},
                text="Recharge Count",
                category_orders={"Plan Bucket": ranked_order},
            )
            fig_pop.update_layout(template="plotly_white", xaxis_tickangle=-45)
            add_bar_labels(fig_pop, kind="count")
            st.plotly_chart(fig_pop, use_container_width=True)
