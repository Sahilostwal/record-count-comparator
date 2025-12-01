# app.py
import streamlit as st
import pandas as pd
import re
from io import BytesIO

# ------- Page config -------
st.set_page_config(page_title="Table Count Comparator", layout="wide")

# ------- CSS / styling -------
page_bg_css = """
<style>
/* page background gradient */
body {
    background: linear-gradient(135deg, #e6dbff 0%, #ffdcea 100%);
    font-family: 'Segoe UI', Tahoma, sans-serif;
}

/* translucent panel for Streamlit's main container */
[data-testid="stAppViewContainer"] > .main {
    padding-top: 1.5rem;
}
.report-card {
    background: rgba(255,255,255,0.85);
    padding: 20px;
    border-radius: 14px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.06);
}

/* headings */
h1, h2, h3 { color: #3b2f9b; }

/* status badges */
.status-match {
    padding: 6px 12px;
    background-color: #dff6ea;
    color: #0b7a4d;
    font-weight: 700;
    border-radius: 10px;
    display: inline-block;
}
.status-diff {
    padding: 6px 12px;
    background-color: #fff3cd;
    color: #7a5a00;
    font-weight: 700;
    border-radius: 10px;
    display: inline-block;
}
.status-new {
    padding: 6px 12px;
    background-color: #e8f0ff;
    color: #1e49a0;
    font-weight: 700;
    border-radius: 10px;
    display: inline-block;
}
.status-miss {
    padding: 6px 12px;
    background-color: #ffe6e6;
    color: #a10000;
    font-weight: 700;
    border-radius: 10px;
    display: inline-block;
}

/* footer */
.app-footer {
    margin-top: 30px;
    text-align: center;
    font-size: 14px;
    color: #333;
}
.app-footer a { color: #3b338c; font-weight: 700; text-decoration: none; }
</style>
"""
st.markdown(page_bg_css, unsafe_allow_html=True)

# ------- helpers -------
def parse_report_text_textfile(text: str) -> pd.DataFrame:
    """
    Parse a plain text report file that contains lines like:
    TABLE | tcibd001      | Parts Master  |     16907  |  2807 |  45.26 | ...
    We split on '|' and pick columns robustly. Returns DataFrame with TableName and Count (int).
    """
    rows = []
    for line in text.splitlines():
        if 'TABLE' not in line:
            continue
        # attempt to split by '|' and pick expected columns
        parts = [p for p in line.split('|')]
        # remove empty parts and trim spaces if some leading/trailing pipe present
        parts = [p.strip() for p in parts]
        # we expect at least 5 parts: ['TABLE', '<object>', '<desc>', '<count>', '<rowlen>', ...]
        if len(parts) >= 5:
            try:
                # parts[1] might be 'TABLE' label; find where object name actually is
                # find the index of the object token (first token that looks like an object name: letters+digits+underscore)
                # typically parts[1] == 'TABLE' so object will be parts[2]
                # but do robust check:
                obj_idx = None
                for idx in range(len(parts)):
                    # skip pure 'TABLE' or 'Type'
                    if parts[idx].upper().startswith('TABLE') and idx+1 < len(parts):
                        obj_idx = idx + 1
                        break
                if obj_idx is None:
                    obj_idx = 1  # fallback

                table_name = parts[obj_idx].strip()
                # usually count is two positions after the object (object, description, count) -> index obj_idx + 2
                cnt_idx = obj_idx + 2
                # fallback: find first numeric-looking column after object
                if cnt_idx >= len(parts) or not re.search(r'\d', parts[cnt_idx]):
                    # search forward for first numeric token
                    found = None
                    for j in range(obj_idx+1, min(len(parts), obj_idx+6)):
                        if re.search(r'\d', parts[j]):
                            found = j
                            break
                    if found is not None:
                        cnt_idx = found
                count_str = parts[cnt_idx] if cnt_idx < len(parts) else ""
                # sanitize number, remove commas/spaces
                m = re.search(r'([\d,]+)', count_str)
                if m:
                    cnt = int(m.group(1).replace(',', ''))
                else:
                    cnt = 0
                if table_name:
                    rows.append((table_name.lower(), table_name, cnt))
            except Exception:
                # skip malformed line
                continue
    df = pd.DataFrame(rows, columns=["key", "TableName", "Count"])
    # drop duplicates using key keeping first (if file includes same table multiple times)
    if not df.empty:
        df = df.drop_duplicates(subset="key", keep="first").reset_index(drop=True)
    return df

def compare_tables(df_before: pd.DataFrame, df_after: pd.DataFrame) -> pd.DataFrame:
    """
    Compare two parsed dataframes and produce final report.
    """
    d1 = df_before.set_index("key")[["TableName", "Count"]].rename(columns={"Count":"Before_Count", "TableName":"TableName_Before"})
    d2 = df_after.set_index("key")[["TableName", "Count"]].rename(columns={"Count":"After_Count", "TableName":"TableName_After"})
    merged = d1.join(d2, how="outer")
    merged = merged.reset_index().rename(columns={"index":"key"})
    # pick display TableName: prefer After then Before
    def pick_name(row):
        if pd.notna(row.get("TableName_After")) and row["TableName_After"]:
            return row["TableName_After"]
        return row.get("TableName_Before") or row["key"]
    merged["TableName"] = merged.apply(pick_name, axis=1)
    merged["Before_Count"] = merged["Before_Count"].fillna(0).astype(int)
    merged["After_Count"] = merged["After_Count"].fillna(0).astype(int)
    merged["Difference"] = merged["After_Count"] - merged["Before_Count"]
    def row_status(r):
        if r["Before_Count"] == 0 and r["After_Count"] > 0:
            return "NEW TABLE"
        if r["Before_Count"] > 0 and r["After_Count"] == 0:
            return "MISSING"
        if r["Before_Count"] == r["After_Count"]:
            return "MATCH"
        return "DIFFER"
    merged["Status"] = merged.apply(row_status, axis=1)
    # order columns
    merged = merged[["TableName", "Before_Count", "After_Count", "Difference", "Status"]].sort_values(by=["Status","TableName"], ascending=[True, True])
    return merged

# ------- UI -------
st.title("Table Count Comparator — (Before vs After)")
st.write("Upload two FSL/eXtend text report files (BEFORE and AFTER). The app will parse table names and counts, compare them, and generate a downloadable Excel with details.")

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    file_before = st.file_uploader("Upload BEFORE file (txt)", type=["txt"], key="before")
with col2:
    file_after = st.file_uploader("Upload AFTER file (txt)", type=["txt"], key="after")

if file_before and file_after:
    try:
        txt_before = file_before.read().decode("utf-8", errors="ignore")
    except Exception:
        txt_before = file_before.read().decode("latin-1", errors="ignore")
    try:
        txt_after = file_after.read().decode("utf-8", errors="ignore")
    except Exception:
        txt_after = file_after.read().decode("latin-1", errors="ignore")

    st.info("Parsing files...")

    df_before = parse_report_text_textfile(txt_before)
    df_after = parse_report_text_textfile(txt_after)

    if df_before.empty:
        st.warning("Warning: No table rows parsed from BEFORE file. Check file format.")
    if df_after.empty:
        st.warning("Warning: No table rows parsed from AFTER file. Check file format.")

    result = compare_tables(df_before, df_after)

    # Summary badges
    total = len(result)
    new_count = (result["Status"]=="NEW TABLE").sum()
    missing_count = (result["Status"]=="MISSING").sum()
    diff_count = (result["Status"]=="DIFFER").sum()
    match_count = (result["Status"]=="MATCH").sum()

    st.markdown("<div class='report-card'>", unsafe_allow_html=True)
    st.subheader("Summary")
    cols = st.columns(5)
    cols[0].metric("Total tables compared", total)
    cols[1].metric("MATCH", match_count)
    cols[2].metric("DIFFER", diff_count)
    cols[3].metric("NEW TABLE", new_count)
    cols[4].metric("MISSING", missing_count)

    st.write("")  # spacing

    # Show result table (no sample 10 preview - show full but paged by streamlit)
    st.subheader("Comparison table")
    st.dataframe(result, use_container_width=True)

    # Provide small counts preview boxes per status for quick triage
    st.write("")
    st.write("Quick status legend:")
    st.markdown('<span class="status-match">MATCH</span>  &nbsp; <span class="status-diff">DIFFER</span>  &nbsp; <span class="status-new">NEW TABLE</span>  &nbsp; <span class="status-miss">MISSING</span>', unsafe_allow_html=True)

    # EXCEL export
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="All_Data", index=False)
        result[result["Status"]=="DIFFER"].to_excel(writer, sheet_name="Differences", index=False)
        result[result["Status"]=="NEW TABLE"].to_excel(writer, sheet_name="New_Tables", index=False)
        result[result["Status"]=="MISSING"].to_excel(writer, sheet_name="Missing_Tables", index=False)
    excel_bytes = output.getvalue()

    st.download_button(
        label="📥 Download Comparison Excel",
        data=excel_bytes,
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("Please upload both BEFORE and AFTER files to begin comparison.")

# ------- footer with your name/link -------
st.markdown(
    """
    <div class="app-footer">
        <hr style="margin-top:30px; margin-bottom:10px;">
        Developed by 
        <a href="https://github.com/sahilostwal" target="_blank">sahilostwal</a>
    </div>
    """,
    unsafe_allow_html=True
)
