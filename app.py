import streamlit as st
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Table Count Comparator", layout="wide")
st.title("Table Count Comparator (Before vs After)")

# ---------------------- Parsing Logic (YOUR CODE) ----------------------

def parse_report_text(text):
    # Pattern 1: TABLE | name | ... | number
    pattern = re.compile(r'\bTABLE\s*\|\s*([^\|]+?)\s*\|.*?\|\s*([\d,]+)\b', re.IGNORECASE)
    rows = []
    for m in pattern.finditer(text):
        table = m.group(1).strip()
        cnt = int(m.group(2).replace(',', ''))
        rows.append((table, cnt))

    # Fallback pattern: name | 123
    if not rows:
        fallback = re.compile(r'([A-Za-z0-9_.\- ]+?)\s*\|\s*([\d,]+)')
        for m in fallback.finditer(text):
            table = m.group(1).strip()
            cnt = int(m.group(2).replace(',', ''))
            rows.append((table, cnt))

    df = pd.DataFrame(rows, columns=['TableName', 'Count'])
    return df


def normalize(df):
    df = df.copy()
    df["key"] = df["TableName"].str.strip().str.lower()
    return df


def compare(df1, df2):
    d1 = normalize(df1).rename(columns={"Count": "Source"})
    d2 = normalize(df2).rename(columns={"Count": "Target"})

    merged = pd.merge(d1, d2, on="key", how="outer", suffixes=("_s", "_t"))
    merged["TableName"] = merged["TableName_s"].combine_first(merged["TableName_t"])
    merged["Source"] = merged["Source"].fillna(0).astype(int)
    merged["Target"] = merged["Target"].fillna(0).astype(int)
    merged["Difference"] = merged["Source"] - merged["Target"]

    merged["Status"] = merged.apply(
        lambda row: "MATCH" if row["Source"] == row["Target"] else "NOT MATCH",
        axis=1
    )

    return merged[["TableName", "Source", "Target", "Difference", "Status"]]

# ----------------------------------------------------------------------

file1 = st.file_uploader("Upload BEFORE file", type=["txt"])
file2 = st.file_uploader("Upload AFTER file", type=["txt"])

if file1 and file2:
    st.success("Files uploaded successfully!")

    # Read content safely
    text1 = file1.read().decode("utf-8", errors="ignore")
    text2 = file2.read().decode("utf-8", errors="ignore")

    df1 = parse_report_text(text1)
    df2 = parse_report_text(text2)

    if df1.empty:
        st.warning("⚠ No table rows parsed from BEFORE file. Check format.")
    if df2.empty:
        st.warning("⚠ No table rows parsed from AFTER file. Check format.")

    result = compare(df1, df2)

    st.subheader("Comparison Result")
    st.dataframe(result, use_container_width=True)

    # Filter NOT MATCH rows
    notmatch = result[result["Status"] == "NOT MATCH"]

    # Prepare Excel in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="All_Data", index=False)
        notmatch.to_excel(writer, sheet_name="Differences", index=False)

    excel_data = output.getvalue()

    st.download_button(
        label="📥 Download Comparison Excel",
        data=excel_data,
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Please upload BEFORE and AFTER files to begin comparison.")
