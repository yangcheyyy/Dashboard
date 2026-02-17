# app.py
import streamlit as st

from roaming import run_roaming
from roaming_predictive import run_roaming_predictive
from data_plan import run_data_plan

st.set_page_config(page_title="TashiCell Analytics Dashboard", layout="wide")

analysis = st.sidebar.selectbox(
    "Select analysis",
    [
        "1) Roaming Data Usage by Country",
        "2) Roaming Predictive Analysis (2022 onwards)",
        "3) Data Plan Usage by Age Group",
    ],
)

if analysis.startswith("1)"):
    run_roaming()
elif analysis.startswith("2)"):
    run_roaming_predictive()  # ✅ no upload required
else:
    run_data_plan()
