import streamlit as st
import re
import pandas as pd
from io import BytesIO

# -------------------- PAGE STYLE --------------------
st.set_page_config(page_title="Table Count Comparator", layout="wide")

# Add link at the top right (this must NOT be inside CSS)
st.markdown("""
<div style='text-align: right; font-size: 17px;'>
    <a href="https://github.com/sahilostwal" target="_blank">sahilostwal</a>
</div>
""", unsafe_allow_html=True)

# Soft purple → pink gradient background
page_bg = """
<style>
body {
    background: linear-gradient(135deg, #d9c8ff 0%, #f5b6c8 100%);
    font-family: 'Segoe UI', sans-serif;
}

.block-container {
    background: rgba(255, 255, 255, 0.15);
    padding: 2.2rem 2.5rem;
    border-radius: 16px;
    backdrop-filter: blur(10px);
    box-shadow: 0 0 25px rgba(0,0,0,0.15);
}

h1, h2, h3, h4 {
    color: #3b338c;
}

.status-match {
    padding: 6px 12px;
    background-color: #d4f8e8;
    color: #037d50;
    font-weight: bold;
    border-radius: 10px;
    display: inline-block;
}

.status-notmatch {
    padding: 6px 12px;
    background-color: #ffe1e1;
    color: #d11a2a;
    font-weight: bold;
    border-radius: 10px;
    display: inline-block;
}
</style>
"""
st.markdown(page_bg, unsafe_allow_html=True)
