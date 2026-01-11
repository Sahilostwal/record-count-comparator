import streamlit as st
# 🔒 TEMPORARY DECOMMISSION / MAINTENANCE MODE
st.error("🚧 This application is temporarily unavailable due to maintenance.")
st.stop()
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Logical & Physical Table Comparator", layout="wide")

# ---------------------------------------------------------
#                  PAGE THEME / CSS
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

st.title("Logical + Physical Table Comparator")


# ---------------------------------------------------------
#   STRICT LOGICAL PARSER (Your earlier logical comparison)
# ---------------------------------------------------------
def parse_logical(text: str) -> pd.DataFrame:
    rows = []
    for ln in text.splitlines():

        if "TABLE" not in ln.upper():
            continue
        if "|" not in ln:
            continue

        parts = [p.strip() for p in ln.split("|")]

        if len(parts) < 4:
            continue

        try:
            tbl_idx = next(i for i,p in enumerate(parts) if p.upper() == "TABLE")
        except StopIteration:
            continue

        if tbl_idx + 1 >= len(parts):
            continue
        table_name = parts[tbl_idx + 1]

        count_idx = tbl_idx + 3
        if count_idx >= len(parts):
            continue

        m = re.search(r"(\d{1,3}(?:,\d{3})*|\d+)$", parts[count_idx])
        count_val = int(m.group(1).replace(",", "")) if m else None

        rows.append((table_name, count_val))

    df = pd.DataFrame(rows, columns=["TableName", "Count"])
    df = df.drop_duplicates(subset=["TableName"], keep="first")
    return df.reset_index(drop=True)


# ---------------------------------------------------------
#           PHYSICAL PARSER (new for your format)
# ---------------------------------------------------------
def parse_physical(text: str) -> pd.DataFrame:
    rows = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue

        parts = re.split(r"\s+", ln)
        if len(parts) < 2:
            continue

        raw_name = parts[0]

        # strip [dbo].[tablename]
        cleaned = re.sub(r"^\[dbo\]\.\[?", "", raw_name)
        cleaned = cleaned.replace("]", "")
        table_name = cleaned.strip()

        raw_count = parts[-1].replace(",", "")
        try:
            count_val = int(raw_count)
        except:
            continue

        rows.append((table_name, count_val))

    df = pd.DataFrame(rows, columns=["TableName", "Count"])
    df = df.drop_duplicates(subset=["TableName"], keep="first")
    return df.reset_index(drop=True)


# ---------------------------------------------------------
#            GENERIC COMPARISON ENGINE
# ---------------------------------------------------------
def compare_dfs(df_before, df_after):
    df_before["key"] = df_before["TableName"].str.lower().str.strip()
    df_after["key"]  = df_after["TableName"].str.lower().str.strip()

    merged = pd.merge(df_before, df_after, on="key", how="outer",
                      suffixes=("_before", "_after"))

    merged["TableName"] = merged["TableName_after"].combine_first(
                            merged["TableName_before"])

    merged["Count_Before"] = merged["Count_before"]
    merged["Count_After"]  = merged["Count_after"]

    merged["Present_Before"] = merged["TableName_before"].notna()
    merged["Present_After"]  = merged["TableName_after"].notna()

    merged["Created"] = merged.apply(lambda r: "YES" if r["Present_After"] and not r["Present_Before"] else "", axis=1)
    merged["Deleted"] = merged.apply(lambda r: "YES" if r["Present_Before"] and not r["Present_After"] else "", axis=1)

    def diff_val(r):
        if r["Count_Before"] is not None and r["Count_After"] is not None:
            return r["Count_After"] - r["Count_Before"]
        return None

    merged["Difference"] = merged.apply(diff_val, axis=1)

    def status(r):
        if r["Created"] == "YES": return "NEW TABLE"
        if r["Deleted"] == "YES": return "DELETED TABLE"
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
#                  2 TABS (Logical + Physical)
# ---------------------------------------------------------
tab1, tab2 = st.tabs(["🔵 Logical Comparison", "🔴 Physical Comparison"])


# ---------------------------------------------------------
#                     TAB 1 → LOGICAL
# ---------------------------------------------------------
with tab1:
    st.header("Logical Table Comparison (Before vs After)")
    
    file_b = st.file_uploader("Upload BEFORE Logical file", type=["txt"], key="log_before")
    file_a = st.file_uploader("Upload AFTER Logical file", type=["txt"], key="log_after")

    if file_b and file_a:
        dfb = parse_logical(file_b.read().decode(errors="ignore"))
        dfa = parse_logical(file_a.read().decode(errors="ignore"))

        merged = compare_dfs(dfb, dfa)

        st.subheader("Results")
        st.dataframe(merged)

        # Excel export
        out = BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            merged.to_excel(writer, sheet_name="All_Data", index=False)
            merged[merged["Created"]=="YES"].to_excel(writer, sheet_name="New_Tables", index=False)
            merged[merged["Deleted"]=="YES"].to_excel(writer, sheet_name="Deleted_Tables", index=False)
            merged[merged["Status"]=="NOT MATCH"].to_excel(writer, sheet_name="Differences", index=False)

        st.download_button("Download Logical Comparison Excel",
                           data=out.getvalue(),
                           file_name="logical_comparison.xlsx")


# ---------------------------------------------------------
#                     TAB 2 → PHYSICAL
# ---------------------------------------------------------
with tab2:
    st.header("Physical Table Comparison (Before vs After)")

    file_pb = st.file_uploader("Upload BEFORE Physical file", type=["txt"], key="phys_before")
    file_pa = st.file_uploader("Upload AFTER Physical file", type=["txt"], key="phys_after")

    if file_pb and file_pa:
        dfpb = parse_physical(file_pb.read().decode(errors="ignore"))
        dfpa = parse_physical(file_pa.read().decode(errors="ignore"))

        merged2 = compare_dfs(dfpb, dfpa)

        st.subheader("Results")
        st.dataframe(merged2)

        out2 = BytesIO()
        with pd.ExcelWriter(out2, engine="openpyxl") as writer:
            merged2.to_excel(writer, sheet_name="All_Data", index=False)
            merged2[merged2["Created"]=="YES"].to_excel(writer, sheet_name="New_Tables", index=False)
            merged2[merged2["Deleted"]=="YES"].to_excel(writer, sheet_name="Deleted_Tables", index=False)
            merged2[merged2["Status"]=="NOT MATCH"].to_excel(writer, sheet_name="Differences", index=False)

        st.download_button("Download Physical Comparison Excel",
                           data=out2.getvalue(),
                           file_name="physical_comparison.xlsx")


# Footer
st.markdown("""
<hr>
<div style="text-align:center;">
    Developed by <a href="https://github.com/sahilostwal" target="_blank">sahilostwal</a>
</div>
""", unsafe_allow_html=True)

