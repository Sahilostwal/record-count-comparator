import streamlit as st
import re
import pandas as pd
from io import BytesIO

# -------------------- PAGE STYLE --------------------
st.set_page_config(page_title="Table Count Comparator", layout="wide")

# Add gradient background + card UI
page_bg = """
<style>
body {
    background: linear-gradient(135deg, #eef2f7 0%, #ffffff 100%);
    font-family: 'Segoe UI', sans-serif;
}
.block-container {
    background: yellow;
    padding: 2.2rem 2.5rem;
    border-radius: 18px;
    box-shadow: 0 0 25px rgba(0,0,0,0.08);
}
h1, h2, h3, h4 {
    color: #2a4d9b;
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

# -------------------- TITLE --------------------
st.title("Table Count Comparator (Before vs After)")
st.write("Upload two table report text files to compare row counts after deployment.")

# -------------------- YOUR ORIGINAL LOGIC --------------------
def parse_report_text(text):
    # Pattern 1: TABLE | name | ... | number
    pattern = re.compile(r'\\bTABLE\\s*\\|\\s*([^\\|]+?)\\s*\\|.*?\\|\\s*([\\d,]+)\\b', re.IGNORECASE)
    rows = []
    for m in pattern.finditer(text):
        table = m.group(1).strip()
        cnt = int(m.group(2).replace(',', ''))
        rows.append((table, cnt))

    # Fallback pattern: name | 123
    if not rows:
        fallback = re.compile(r'([A-Za-z0-9_.\\- ]+?)\\s*\\|\\s*([\\d,]+)')
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

# -------------------- FILE UPLOAD SECTION --------------------
st.subheader("Upload Files")

file1 = st.file_uploader("Upload BEFORE file (txt)", type=["txt"])
file2 = st.file_uploader("Upload AFTER file (txt)", type=["txt"])

if file1 and file2:
    st.success("Files uploaded successfully!")

    text1 = file1.read().decode("utf-8", errors="ignore")
    text2 = file2.read().decode("utf-8", errors="ignore")

    df1 = parse_report_text(text1)
    df2 = parse_report_text(text2)

    result = compare(df1, df2)

    # -------------------- RESULT DISPLAY --------------------
    st.subheader("Comparison Result")

    if all(result["Status"] == "MATCH"):
        st.markdown('<div class="status-match">ALL TABLES MATCH</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-notmatch">MISMATCH FOUND</div>', unsafe_allow_html=True)

    st.write("")
    st.dataframe(result, use_container_width=True)

    # -------------------- EXCEL EXPORT --------------------
    notmatch = result[result["Status"] == "NOT MATCH"]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="All_Data", index=False)
        notmatch.to_excel(writer, sheet_name="Differences", index=False)

    excel_bytes = output.getvalue()

    st.download_button(
        label="Download Comparison Excel",
        data=excel_bytes,
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Please upload both BEFORE and AFTER files to begin comparison.")

