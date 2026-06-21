"""
app.py — CTO ERP entry point.
Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from erp.views import customers, machine, operator, site, workorder

st.set_page_config(
    page_title="CTO ERP – Fleet Operations",
    page_icon="🏗️",
    layout="wide",
)

# A little density tuning for an internal tool.
st.markdown(
    """
    <style>
      .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px;}
      [data-testid="stMetricValue"] {font-size: 1.6rem;}
      h1, h2, h3 {letter-spacing: -0.01em;}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🏗️ CTO ERP")
    st.caption("Equipment Rental Operations · v1")
    page = st.radio(
        "Navigation",
        options=["Customers", "Sites", "Operators", "Machines", "Work Orders"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(
        "Demo runs on in-memory data. Dispatch a machine, then return to "
        "Fleet Status to see it flip to On Rent."
    )

if page == "Customers":
    customers.render()
elif page == "Sites":
    site.render()
elif page == "Operators":
    operator.render()
elif page == "Machines":
    machine.render()
elif page == "Work Orders":
    workorder.render()
else:
    st.error("Page not found.")
