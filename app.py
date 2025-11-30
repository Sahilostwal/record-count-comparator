import streamlit as st
import re
import pandas as pd
from io import BytesIO

# -------------------- PAGE STYLE --------------------
st.set_page_config(page_title="Table Count Comparator", layout="wide")

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

# -------------------- TITLE --------------------
st.title("Table Count Comparator (Before vs After)")
st.write("Upload two table report text files to compare row counts and detect new or deleted tables.")

# -------------------- PARSER (LINE BASED, BEST ACCURACY) --------------------
def parse_report_text_by_line(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # TRY FORMAT 1: TABLE | name | other | 123
        m = re.search(r'TABLE\s*\|\s*([A-Za-z0-9_]+).*?(\d+)', line, re.IGNORECASE)
        if m:
            rows.append((m.group(1), int(m.group(2))))
            continue

        # TRY FORMAT 2: name | 123
        m2 = re.search(r'^([A-Za-z0-9_]+)\s*\|\s*(\d+)', line)
        if m2:
            rows.append((m2.group(1), int(m2.group(2))))
            continue

        # TRY FORMAT 3: TABLE | name  (count missing)
        m3 = re.search(r'TABLE\s*\|\s*([A-Za-z0-9_]+)', line, re.IGNORECASE)
        if m3:
            rows.append((m3.group(1), 0))
            continue

    return pd.DataFrame(rows, columns=["TableName", "Count"])

# -------------------- COMPARISON LOGIC --------------------
def compare_presence(df_before, df_after):
    df_before = df_before.copy()
    df_after = df_after.copy()

    df_before["key"] = df_before["TableName"].str.lower()
    df_after["key"] = df_after["TableName"].str.lower()

    merged = pd.merge(
        df_before, df_after, on="key", how="outer",
        suffixes=("_before", "_after")
    )

    merged["TableName"] = merged["TableName_before"].combine_first(merged["TableName_after"])
    merged["Count_before"] = merged["Count_before"].fillna(0).astype(int)
    merged["Count_after"] = merged["Count_after"].fillna(0).astype(int)

    merged["Created"] = merged.apply(
        lambda r: "YES" if r["Count_before"] == 0 and r["Count_after"] > 0 else "",
        axis=1
    )
    merged["Deleted"] = merged.apply(
        lambda r: "YES" if r["Count_before"] > 0 and r["Count_after"] == 0 else "",
        axis=1
    )

    merged["Difference"] = merged["Count_before"] - merged["Count_after"]

    def status(r):
        if r["Created"] == "YES": return "NEW TABLE"
        if r["Deleted"] == "YES": return "DELETED TABLE"
        if r["Count_before"] == r["Count_after"]: return "MATCH"
        return "NOT MATCH"

    merged["Status"] = merged.apply(status, axis=1)

    return merged[[
        "TableName", "Count_before", "Count_after",
        "Difference", "Created", "Deleted", "Status"
    ]]

# -------------------- FILE UPLOAD --------------------
st.subheader("Upload Files")

file_before = st.file_uploader("Upload BEFORE file (txt)", type=["txt"])
file_after = st.file_uploader("Upload AFTER file (txt)", type=["txt"])

if file_before and file_after:
    st.success("Files uploaded successfully!")

    text_before = file_before.read().decode("utf-8", errors="ignore")
    text_after = file_after.read().decode("utf-8", errors="ignore")

    df_before = parse_report_text_by_line(text_before)
    df_after = parse_report_text_by_line(text_after)

    merged = compare_presence(df_before, df_after)

    # -------------------- RESULT --------------------
    st.subheader("Comparison Result")

    if all(merged["Status"] == "MATCH"):
        st.markdown('<div class="status-match">ALL TABLES MATCH</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-notmatch">DIFFERENCES FOUND</div>', unsafe_allow_html=True)

    st.dataframe(merged, use_container_width=True)

    new_tables = merged[merged["Created"] == "YES"]
    deleted_tables = merged[merged["Deleted"] == "YES"]
    mismatched = merged[merged["Status"] == "NOT MATCH"]

    # -------------------- EXPORT --------------------
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="All_Results", index=False)
        new_tables.to_excel(writer, sheet_name="New_Tables", index=False)
        deleted_tables.to_excel(writer, sheet_name="Deleted_Tables", index=False)
        mismatched.to_excel(writer, sheet_name="Mismatched", index=False)

    excel_bytes = output.getvalue()

    st.download_button(
        label="Download Excel Result",
        data=excel_bytes,
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Please upload both BEFORE and AFTER files to start comparison.")

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
