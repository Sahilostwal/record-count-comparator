import streamlit as st
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Table Count Comparator", layout="wide")

# Simple clean CSS (keeps your gradient look)
st.markdown("""
<style>
body { background: linear-gradient(135deg, #d9c8ff 0%, #f5b6c8 100%); font-family: 'Segoe UI', sans-serif; }
.block-container { background: rgba(255,255,255,0.16); padding: 18px; border-radius:12px; backdrop-filter: blur(6px); }
h1,h2,h3,h4 { color: #3b338c; }
</style>
""", unsafe_allow_html=True)

st.title("Table Count Comparator (Before vs After)")
# ---------------- parser ----------------
def parse_report_text_by_line(text):
    """
    Parse the text file line-by-line to extract TableName and optional Count.
    Returns a DataFrame with columns: TableName, Count (int or None)
    """
    lines = text.splitlines()
    rows = []
    # Patterns:
    # capture table name after 'TABLE |' until next '|' or end-of-line
    name_regex = re.compile(r'TABLE\s*\|\s*([^\|\n\r]+?)\s*(?:\||$)', re.IGNORECASE)
    # capture first integer count in the line (digits and optional commas)
    count_regex = re.compile(r'(\d{1,3}(?:,\d{3})*|\d+)')
    for ln in lines:
        if 'TABLE' not in ln.upper():
            continue
        m = name_regex.search(ln)
        if not m:
            continue
        raw_name = m.group(1).strip()
        # normalize name (remove extra spaces)
        table_name = re.sub(r'\s+', ' ', raw_name)
        # try to find a count on same line
        mc = count_regex.search(ln)
        cnt = int(mc.group(1).replace(',', '')) if mc else None
        rows.append((table_name, cnt))
    # if nothing found, return empty df
    if not rows:
        return pd.DataFrame(columns=["TableName", "Count"])
    df = pd.DataFrame(rows, columns=["TableName", "Count"])
    # deduplicate keeping first occurrence (if multiple lines for same table)
    df = df.drop_duplicates(subset=["TableName"], keep="first").reset_index(drop=True)
    return df

# ---------------- compare ----------------
def compare_presence(df_before, df_after):
    """
    Compare by presence (and counts when available).
    Returns merged dataframe with flags: has_before, has_after, Created, Deleted, Status
    """
    d1 = df_before.copy()
    d2 = df_after.copy()

    # create normalized keys for matching
    d1['key'] = d1['TableName'].str.strip().str.lower()
    d2['key'] = d2['TableName'].str.strip().str.lower()

    merged = pd.merge(d1, d2, on='key', how='outer', suffixes=('_before', '_after'))

    # Choose a good display name (prefer the after-name then before-name)
    merged['TableName'] = merged['TableName_after'].combine_first(merged['TableName_before'])

    # presence flags
    merged['has_before'] = merged['TableName_before'].notna()
    merged['has_after'] = merged['TableName_after'].notna()

    # counts: replace NaN with None for clarity, but convert to int where possible
    merged['Count_before'] = merged['Count_before'].apply(lambda x: int(x) if pd.notna(x) else None)
    merged['Count_after']  = merged['Count_after'].apply(lambda x: int(x) if pd.notna(x) else None)

    # Created / Deleted based purely on presence
    merged['Created'] = merged.apply(lambda r: 'YES' if (r['has_after'] and not r['has_before']) else '', axis=1)
    merged['Deleted'] = merged.apply(lambda r: 'YES' if (r['has_before'] and not r['has_after']) else '', axis=1)

    # Difference when both counts are available (else None)
    def diff_val(r):
        if (r['Count_before'] is not None) and (r['Count_after'] is not None):
            return r['Count_before'] - r['Count_after']
        return None
    merged['Difference'] = merged.apply(diff_val, axis=1)

    # Status logic: CREATED / DELETED (by presence) take precedence.
    def status(r):
        if r['Created'] == 'YES':
            return 'NEW TABLE'
        if r['Deleted'] == 'YES':
            return 'DELETED TABLE'
        # both present
        if r['has_before'] and r['has_after']:
            if (r['Count_before'] is not None) and (r['Count_after'] is not None):
                return 'MATCH' if r['Count_before'] == r['Count_after'] else 'NOT MATCH'
            # counts not available for one or both -> presence only
            return 'PRESENT IN BOTH'
        return 'UNKNOWN'  # should not reach
    merged['Status'] = merged.apply(status, axis=1)

    # final column order for display
    out = merged[[
        'TableName', 'key', 'has_before', 'has_after',
        'Count_before', 'Count_after', 'Difference',
        'Created', 'Deleted', 'Status'
    ]].copy()

    # rename presence flags for readability
    out = out.rename(columns={'has_before':'Present_Before', 'has_after':'Present_After',
                              'Count_before':'Count_Before','Count_after':'Count_After'})

    return out

# ---------------- UI ----------------
st.subheader("Upload your BEFORE and AFTER report files (plain text)")

file_before = st.file_uploader("Choose BEFORE file (before installation)", type=['txt'], key='bef')
file_after  = st.file_uploader("Choose AFTER file (after installation)", type=['txt'], key='aft')

if file_before and file_after:
    text_before = file_before.read().decode(errors='ignore')
    text_after  = file_after.read().decode(errors='ignore')

    with st.spinner("Parsing files..."):
        df_before = parse_report_text_by_line(text_before)
        df_after  = parse_report_text_by_line(text_after)

    st.markdown("**Parsed table counts (sample)**")
    col1, col2 = st.columns(2)
    with col1:
        st.write("BEFORE (first 10)")
        st.dataframe(df_before.head(10))
    with col2:
        st.write("AFTER (first 10)")
        st.dataframe(df_after.head(10))

    merged = compare_presence(df_before, df_after)

    # Summary counts
    total_before = df_before.shape[0]
    total_after = df_after.shape[0]
    new_count = (merged['Created'] == 'YES').sum()
    deleted_count = (merged['Deleted'] == 'YES').sum()
    mismatches = merged[merged['Status'] == 'NOT MATCH'].shape[0]

    st.markdown("### Summary")
    st.write(f"- Tables in BEFORE file: **{total_before}**")
    st.write(f"- Tables in AFTER file: **{total_after}**")
    st.write(f"- New tables (present in AFTER only): **{new_count}**")
    st.write(f"- Deleted tables (present in BEFORE only): **{deleted_count}**")
    st.write(f"- Tables present in both but counts differ: **{mismatches}**")

    st.markdown("### New Tables (present in AFTER but not in BEFORE)")
    new_tables = merged[merged['Created'] == 'YES'][['TableName','Count_After']]
    if new_tables.empty:
        st.info("No new tables detected.")
    else:
        st.dataframe(new_tables.reset_index(drop=True))

    st.markdown("### Deleted Tables (present in BEFORE but not in AFTER)")
    deleted_tables = merged[merged['Deleted'] == 'YES'][['TableName','Count_Before']]
    if deleted_tables.empty:
        st.info("No deleted tables detected.")
    else:
        st.dataframe(deleted_tables.reset_index(drop=True))

    st.markdown("### All comparison rows (sample)")
    st.dataframe(merged.head(200))

    # Export Excel with sheets: All_Data, New_Tables, Deleted_Tables, Differences
    out_buf = BytesIO()
    with pd.ExcelWriter(out_buf, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='All_Data', index=False)
        merged[merged['Created']=='YES'][['TableName','Count_After']].to_excel(writer, sheet_name='New_Tables', index=False)
        merged[merged['Deleted']=='YES'][['TableName','Count_Before']].to_excel(writer, sheet_name='Deleted_Tables', index=False)
        merged[merged['Status']=='NOT MATCH'][['TableName','Count_Before','Count_After','Difference']].to_excel(writer, sheet_name='Differences', index=False)
    st.download_button("Download full comparison Excel", data=out_buf.getvalue(), file_name="table_comparison.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Upload both files to start comparison.")

# Footer
st.markdown("""
<hr style="margin-top:30px;">
<div style="text-align:center; font-size:14px;">Developed by <a href="https://record-count-comparator-8ws3zka8lkrpb9a8g4umez.streamlit.app" target="_blank">sahilostwal</a></div>
""", unsafe_allow_html=True)

