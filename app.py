import streamlit as st
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Table Count Comparator", layout="wide")

# ---------------------------------------------------------
#                  PAGE THEME / STYLING
# ---------------------------------------------------------
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #d9c8ff 0%, #f5b6c8 100%);
    font-family: 'Segoe UI', sans-serif;
}
.block-container {
    background: rgba(255,255,255,0.15);
    padding: 20px;
    border-radius: 12px;
    backdrop-filter: blur(6px);
}
h1,h2,h3,h4 { color: #3b338c; }
</style>
""", unsafe_allow_html=True)

st.title("Table Count Comparator (Before vs After)")
st.write("Upload BEFORE and AFTER report files — detect new tables, deleted tables, mismatches, and correct record counts.")


# ---------------------------------------------------------
#                  STRICT PARSER (MAIN FIX)
# ---------------------------------------------------------
def parse_report_text_by_line_strict(text: str) -> pd.DataFrame:
    """
    Extracts exact TableName + RecordCount using COLUMN POSITION,
    so it never picks wrong numbers like 16907 or random integers.
    """
    rows = []

    for ln in text.splitlines():

        # skip non-table lines
        if "TABLE" not in ln.upper():
            continue
        if "|" not in ln:
            continue

        parts = [p.strip() for p in ln.split("|")]

        # Require at least 4 fields (TABLE | name | desc | count)
        if len(parts) < 4:
            continue

        # Find index containing "TABLE"
        try:
            tbl_idx = next(i for i,p in enumerate(parts) if "TABLE" == p.upper())
        except StopIteration:
            continue

        # TABLE NAME = next column
        if tbl_idx + 1 >= len(parts):
            continue
        table_name = parts[tbl_idx + 1]

        # COUNT = 2 columns after TABLE (TABLE | NAME | DESC | COUNT)
        count_idx = tbl_idx + 3
        if count_idx >= len(parts):
            continue

        raw_count_field = parts[count_idx]

        # Extract only integer from that specific column
        m = re.search(r"(\d{1,3}(?:,\d{3})*|\d+)$", raw_count_field)
        if m:
            count_val = int(m.group(1).replace(",", ""))
        else:
            count_val = None

        rows.append((table_name, count_val))

    df = pd.DataFrame(rows, columns=["TableName", "Count"])
    df = df.drop_duplicates(subset=["TableName"], keep="first").reset_index(drop=True)
    return df


# ---------------------------------------------------------
#               COMPARISON LOGIC
# ---------------------------------------------------------
def compare_presence(df_before, df_after):
    d1 = df_before.copy()
    d2 = df_after.copy()

    d1["key"] = d1["TableName"].str.strip().str.lower()
    d2["key"] = d2["TableName"].str.strip().str.lower()

    merged = pd.merge(d1, d2, how="outer", on="key", suffixes=("_before","_after"))

    merged["TableName"] = merged["TableName_after"].combine_first(merged["TableName_before"])

    merged["Present_Before"] = merged["TableName_before"].notna()
    merged["Present_After"]  = merged["TableName_after"].notna()

    merged["Count_Before"] = merged["Count_before"]
    merged["Count_After"]  = merged["Count_after"]

    # Created or Deleted tables
    merged["Created"] = merged.apply(lambda r: "YES" if (r["Present_After"] and not r["Present_Before"]) else "", axis=1)
    merged["Deleted"] = merged.apply(lambda r: "YES" if (r["Present_Before"] and not r["Present_After"]) else "", axis=1)

    # Difference (when both counts exist)
    def diff_val(r):
        if r["Count_Before"] is not None and r["Count_After"] is not None:
            return r["Count_After"] - r["Count_Before"]
        return None

    merged["Difference"] = merged.apply(diff_val, axis=1)

    # Status
    def status(r):
        if r["Created"] == "YES":
            return "NEW TABLE"
        if r["Deleted"] == "YES":
            return "DELETED TABLE"
        if r["Present_Before"] and r["Present_After"]:
            if r["Count_Before"] is None or r["Count_After"] is None:
                return "PRESENT IN BOTH"
            return "MATCH" if r["Count_Before"] == r["Count_After"] else "NOT MATCH"
        return "UNKNOWN"

    merged["Status"] = merged.apply(status, axis=1)

    return merged[[
        "TableName", "Present_Before", "Present_After",
        "Count_Before", "Count_After", "Difference",
        "Created", "Deleted", "Status"
    ]]


# ---------------------------------------------------------
#                  FILE UPLOAD UI
# ---------------------------------------------------------
st.subheader("Upload BEFORE and AFTER Files (TXT Format)")

file_before = st.file_uploader("Upload BEFORE File", type=["txt"])
file_after  = st.file_uploader("Upload AFTER File", type=["txt"])

if file_before and file_after:

    text_before = file_before.read().decode(errors="ignore")
    text_after  = file_after.read().decode(errors="ignore")

    with st.spinner("Reading files..."):
        df_before = parse_report_text_by_line_strict(text_before)
        df_after  = parse_report_text_by_line_strict(text_after)

    st.success("Files processed successfully!")

    merged = compare_presence(df_before, df_after)

    # Summary
    st.markdown("### Summary")
    st.write(f"Tables BEFORE: **{df_before.shape[0]}**")
    st.write(f"Tables AFTER: **{df_after.shape[0]}**")
    st.write(f"New Tables: **{(merged['Created']=='YES').sum()}**")
    st.write(f"Deleted Tables: **{(merged['Deleted']=='YES').sum()}**")
    st.write(f"Mismatched Tables: **{(merged['Status']=='NOT MATCH').sum()}**")

    # Display
    st.markdown("### New Tables")
    st.dataframe(merged[merged["Created"]=="YES"][["TableName","Count_After"]])

    st.markdown("### Deleted Tables")
    st.dataframe(merged[merged["Deleted"]=="YES"][["TableName","Count_Before"]])

    st.markdown("### Mismatched Tables")
    st.dataframe(merged[merged["Status"]=="NOT MATCH"])

    st.markdown("### Full Table")
    st.dataframe(merged)

    # Export Excel
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="All_Data", index=False)
        merged[merged["Created"]=="YES"].to_excel(writer, sheet_name="New_Tables", index=False)
        merged[merged["Deleted"]=="YES"].to_excel(writer, sheet_name="Deleted_Tables", index=False)
        merged[merged["Status"]=="NOT MATCH"].to_excel(writer, sheet_name="Differences", index=False)

    st.download_button(
        "Download Results Excel",
        data=out.getvalue(),
        file_name="table_comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Upload both BEFORE and AFTER files to begin.")


# Footer
st.markdown("""
<hr>
<div style="text-align:center;">
    Developed by <a href="https://github.com/sahilostwal" target="_blank">sahilostwal</a>
</div>
""", unsafe_allow_html=True)
