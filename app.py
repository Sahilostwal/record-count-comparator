import streamlit as st
import re
import pandas as pd
from io import BytesIO

# -------------------- PAGE STYLE --------------------
st.set_page_config(page_title="Table Count Comparator", layout="wide")

# -------------------- BACKGROUND + CSS --------------------
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

.status-new {
    padding: 6px 12px;
    background-color: #d7e8ff;
    color: #0053a6;
    font-weight: bold;
    border-radius: 10px;
    display: inline-block;
}

.status-deleted {
    padding: 6px 12px;
    background-color: #fff3cd;
    color: #8a6d3b;
    font-weight: bold;
    border-radius: 10px;
    display: inline-block;
}

</style>
"""
st.markdown(page_bg, unsafe_allow_html=True)

# -------------------- TITLE --------------------
st.title("Table Count Comparator (Before vs After)")
st.write("Upload two table report text files to compare row counts after deployment, including new and deleted tables.")

# -------------------- LOGIC --------------------
def parse_report_text(text):
    pattern = re.compile(r'\bTABLE\s*\|\s*([^\|]+?)\s*\|.*?\|\s*([\d,]+)\b', re.IGNORECASE)
    rows = []
    for m in pattern.finditer(text):
        table = m.group(1).strip()
        cnt = int(m.group(2).replace(',', ''))
        rows.append((table, cnt))

    if not rows:
        fallback = re.compile(r'([A-Za-z0-9_.\\- ]+?)\\s*\\|\\s*([\\d,]+)')
        for m in fallback.finditer(text):
            table = m.group(1).strip()
            cnt = int(m.group(2).replace(',', ''))
            rows.append((table, cnt))

    return pd.DataFrame(rows, columns=['TableName', 'Count'])


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

    # New table logic
    merged["Created"] = merged.apply(
        lambda r: "YES" if r["Source"] == 0 and r["Target"] > 0 else "",
        axis=1
    )

    # Deleted table logic
    merged["Deleted"] = merged.apply(
        lambda r: "YES" if r["Source"] > 0 and r["Target"] == 0 else "",
        axis=1
    )

    # Status
    def get_status(r):
        if r["Created"] == "YES":
            return "NEW TABLE"
        if r["Deleted"] == "YES":
            return "DELETED TABLE"
        if r["Source"] == r["Target"]:
            return "MATCH"
        return "NOT MATCH"

    merged["Status"] = merged.apply(get_status, axis=1)

    return merged[["TableName", "Source", "Target", "Difference", "Created", "Deleted", "Status"]]

# -------------------- FILE UPLOAD --------------------
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

    # -------------------- RESULT --------------------
    st.subheader("Comparison Result")

    # Summary banner
    if all(result["Status"] == "MATCH"):
        st.markdown('<div class="status-match">ALL TABLES MATCH</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-notmatch">MISMATCH / NEW / DELETED TABLE FOUND</div>',
                    unsafe_allow_html=True)

    st.write("")
    st.dataframe(result, use_container_width=True)

    # -------------------- EXPORT TO EXCEL --------------------
    output = BytesIO()

    new_tables = result[result["Created"] == "YES"]
    deleted_tables = result[result["Deleted"] == "YES"]
    mismatched = result[result["Status"] == "NOT MATCH"]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="All_Data", index=False)
        mismatched.to_excel(writer, sheet_name="Differences", index=False)
        new_tables.to_excel(writer, sheet_name="New_Tables", index=False)
        deleted_tables.to_excel(writer, sheet_name="Deleted_Tables", index=False)

    st.download_button(
        label="Download Comparison Excel",
        data=output.getvalue(),
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Please upload both BEFORE and AFTER files to begin comparison.")

# -------------------- FOOTER --------------------
st.markdown(
    """
    <hr style="margin-top:40px; margin-bottom:10px;">
    <div style='text-align:center; font-size:16px; padding:10px;'>
        Developed by 
        <a href="https://github.com/sahilostwal" target="_blank" style="color:#3b338c; font-weight:bold; text-decoration:none;">
            sahilostwal
        </a>
    </div>
    """,
    unsafe_allow_html=True
)
