import streamlit as st
import pandas as pd
from io import BytesIO

st.title("Record-by-Record Comparator")

file1 = st.file_uploader("Upload First Notepad File", type=["txt"])
file2 = st.file_uploader("Upload Second Notepad File", type=["txt"])

if file1 and file2:
    # Load files
    df1 = pd.read_csv(file1, header=None, names=["Record"], dtype=str)
    df2 = pd.read_csv(file2, header=None, names=["Record"], dtype=str)

    # Remove blank rows
    df1 = df1[df1["Record"].notna()]
    df2 = df2[df2["Record"].notna()]

    # Remove whitespace
    df1["Record"] = df1["Record"].str.strip()
    df2["Record"] = df2["Record"].str.strip()

    # Unique lists
    set1 = set(df1["Record"])
    set2 = set(df2["Record"])

    # Record-level comparison
    matched = sorted(list(set1.intersection(set2)))
    missing_in_file2
