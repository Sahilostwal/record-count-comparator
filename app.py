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
    background: rgba(255, 255, 255, 0.18);
    padding: 2.2rem 2.5rem;
    border-radius: 16px;
    backdrop-filter: blur(10px);
    box-shadow: 0 0 25px rgba(0,0,0,0.12);
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
st.write("Upload two table report text files to compare row counts after deployment, including NEW and DELETED tables.")

# -------------------- PARSER (FIXED) --------------------
def parse_report_text(text):
    # Powerful regex: catches ALL patterns like:
    # TABLE | pbodb100 | Row Count | 123
    # TABLE | pbodb100 | 123
    pattern = re.compile(
        r'TABLE\s*\|\s*([A-Za-z0-9_]+)\s*\|.*?(\d+)',
        re.IGNORECASE
    )

    rows = []
    for m in pattern.finditer(text):
        table = m.group(1).strip()
        count = int(m.group(2))
        rows.append((table, count))

    # fallback: no counts found
    if not rows:
        fallback = re.compile(r'TABLE\s*\|\s*([A-Za-z0-9_]+)', re.IGNORECASE)
        for m in fallback.finditer(text):
            rows.append((m.group(1).strip(), 0))

    return pd.DataFrame(rows, columns=["TableName", "Count"])


# -------------------- COMPARISON LOGIC (FIXED) --------------------
def compare(df1, df2):
    d1 = df1.copy()
    d2 = df2.copy()

    d1["key"] = d1["TableName"].str.lower().str.strip()
    d2["key"] = d2["TableName"].str.lower().str.strip()

    merged = pd.merge(d1, d2, on="key", how="outer", suffixes=("_before", "_after"))

    merged["TableName"] = merged["TableName_before"].combine_first(merged["TableName_after"])
    merged["Count_before"] = merged["Count_before"].fillna(0).astype(int)
    merged["Count_after"] = merged["Count_after"].fillna(0).astype(int)

    # NEW TABLE created after installation
    merged["Created"] = merged.apply(
        lambda r: "YES" if r["Count_before"] == 0 and r["Count_after"] > 0 else "",
        axis=1
    )

    # DELETED TABLE removed after installation
    merged["Deleted"] = merged.apply(
        lambda r: "YES" if r["Count_before"] > 0 and r["Count_after"] == 0 else "",
        axis=1
    )

    merged["Difference"] = merged["Count_before"] - merged["Count_after"]

    def status(r):
        if r["Created"] == "YES":
            return "NEW TABLE"
        if r["Deleted"] == "YES":
            return "DELETED TABLE"
        if r["Count_before"] == r["Count_after"]:
            return "MATCH"
        return "NOT MATCH"

    merged["Status"] = merged.apply(status, axis=1)

    return merged[[
        "TableName", "Count_before", "Count_after",
        "Difference", "Created", "Deleted", "Status"
    ]]

# -------------------- FILE UPLOAD --------------------
st.subheader("Upload Files")

file1 = st.file_uploader("Upload BEFORE file (txt)", type=["txt"])
file2 = st.file_uploader("Upload AFTER file (txt)", type=["txt"])

# -------------------- MAIN EXECUTION --------------------
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
        st.markdown('<div class="status-notmatch">NEW / DELETED / MISMATCH FOUND</div>',
                    unsafe_allow_html=True)

    st.dataframe(result, use_container_width=True)

    # Prepare subsets
    new_tables = result[result["Created"] == "YES"]
    deleted_tables = result[result["Deleted"] == "YES"]
    mismatched = result[result["Status"] == "NOT MATCH"]

    # -------------------- EXPORT TO EXCEL --------------------
    output = BytesIO()
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
