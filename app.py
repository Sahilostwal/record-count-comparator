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
.status-new {
    padding: 6px 12px;
    background-color: #d0e7ff;
    color: #0056b3;
    font-weight: bold;
    border-radius: 10px;
    display: inline-block;
}
.status-dropped {
    padding: 6px 12px;
    background-color: #fff0b3;
    color: #a67c00;
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


# -------------------- PARSER --------------------
def parse_report_text(text):
    """
    Extract table names + counts from the raw text file.
    Matches patterns like: TABLE | name | ... | 12345
    """

    pattern = re.compile(r'\bTABLE\s*\|\s*([^\|]+?)\s*\|.*?\|\s*([\d,]+)\b', re.IGNORECASE)
    rows = []

    for m in pattern.finditer(text):
        table = m.group(1).strip()
        cnt = int(m.group(2).replace(',', ''))
        rows.append((table, cnt))

    # fallback pattern for lines like "tablename | 123"
    if not rows:
        fallback = re.compile(r'([A-Za-z0-9_.\- ]+?)\s*\|\s*([\d,]+)')
        for m in fallback.finditer(text):
            table = m.group(1).strip()
            cnt = int(m.group(2).replace(',', ''))
            rows.append((table, cnt))

    return pd.DataFrame(rows, columns=['TableName', 'Count'])


# -------------------- COMPARISON ENGINE --------------------
def compare_dfs(df_before, df_after):

    df_before["key"] = df_before["TableName"].str.lower().str.strip()
    df_after["key"] = df_after["TableName"].str.lower().str.strip()

    merged = pd.merge(df_before, df_after, on="key", how="outer",
                      suffixes=("_before", "_after"))

    merged["TableName"] = merged["TableName_before"].combine_first(
                          merged["TableName_after"])

    merged["Count_before"] = merged["Count_before"].fillna(0).astype(int)
    merged["Count_after"] = merged["Count_after"].fillna(0).astype(int)

    merged["Difference"] = merged["Count_after"] - merged["Count_before"]

    # status logic
    def get_status(row):
        if row["Count_before"] == 0 and row["Count_after"] > 0:
            return "NEW TABLE CREATED"
        if row["Count_before"] > 0 and row["Count_after"] == 0:
            return "TABLE DROPPED"
        if row["Count_before"] == row["Count_after"]:
            return "MATCH"
        return "NOT MATCH"

    merged["Status"] = merged.apply(get_status, axis=1)

    return merged[["TableName", "Count_before", "Count_after", "Difference", "Status"]]


# -------------------- FILE UPLOAD --------------------
st.subheader("Upload BEFORE & AFTER Files")

file1 = st.file_uploader("Upload BEFORE file (.txt)", type=["txt"])
file2 = st.file_uploader("Upload AFTER file (.txt)", type=["txt"])

if file1 and file2:

    text1 = file1.read().decode("utf-8", errors="ignore")
    text2 = file2.read().decode("utf-8", errors="ignore")

    df_before = parse_report_text(text1)
    df_after = parse_report_text(text2)

    result = compare_dfs(df_before, df_after)

    # -------------------- RESULT --------------------
    st.subheader("Final Comparison Result")

    # summary status banner
    if all(result["Status"] == "MATCH"):
        st.markdown('<div class="status-match">ALL TABLES MATCH ✔</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-notmatch">DIFFERENCES FOUND ⚠</div>', unsafe_allow_html=True)

    st.dataframe(result, use_container_width=True)

    # -------------------- EXPORT TO EXCEL --------------------
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="Full_Comparison", index=False)
        result[result["Status"] == "NEW TABLE CREATED"].to_excel(writer, "New_Tables", index=False)
        result[result["Status"] == "TABLE DROPPED"].to_excel(writer, "Dropped_Tables", index=False)
        result[result["Status"] == "NOT MATCH"].to_excel(writer, "Mismatched_Tables", index=False)

    st.download_button(
        label="Download Comparison Excel",
        data=output.getvalue(),
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Please upload BOTH files to continue.")


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
