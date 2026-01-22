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
