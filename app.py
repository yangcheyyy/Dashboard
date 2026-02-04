# app.py
import streamlit as st

from roaming import run_roaming
from data_plan import run_data_plan


st.set_page_config(
    page_title="TashiCell Analytics Dashboard",
    layout="wide",
)

analysis = st.sidebar.selectbox(
    "Select analysis",
    [
        "1) Roaming Data Usage by Country",
        "2) Data Plan Usage by Age Group",
    ],
)

if analysis.startswith("1)"):
    run_roaming()
else:
    run_data_plan()
