# app.py
import streamlit as st
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Table Count Comparator", layout="wide")

# UI styling (simple)
st.markdown("""
<style>
body { background: linear-gradient(135deg, #d9c8ff 0%, #f5b6c8 100%); font-family: 'Segoe UI', sans-serif; }
.block-container { background: rgba(255,255,255,0.16); padding: 18px; border-radius:12px; backdrop-filter: blur(6px); }
h1,h2,h3,h4 { color: #3b338c; }
</style>
""", unsafe_allow_html=True)

st.title("Table Count Comparator (Before vs After)")
st.write("Upload BEFORE and AFTER table reports (plain text). This app extracts the table name and the 'Number of Records' column robustly and compares counts.")

# ---------------- robust parser ----------------
_number_re = re.compile(r'(\d{1,3}(?:,\d{3})*|\d+)')

def parse_report_text_by_line_strict(text: str) -> pd.DataFrame:
    """
    Robust parser for the report export lines of the form:
      TABLE | <object> | <description> | <Number of Records> | <Row length> | <Size (MB)> ...
    Strategy:
      - For lines containing 'TABLE' and '|', split on '|' and:
          * table_name = parts[1].strip()
          * count = parts[3] (if present) -> extract integer
      - If the strict approach fails, fallback to a safer regex-based extraction.
    Returns DataFrame columns: TableName, Count
    """
    rows = []
    for raw in text.splitlines():
        ln = raw.rstrip("\n\r")
        if '|' not in ln:
            continue
        # only process lines that include "TABLE" or look like the expected rows
        if 'TABLE' not in ln.upper():
            # sometimes there are rows without TABLE literal; skip here (we focus on TABLE rows)
            continue

        parts = [p.strip() for p in ln.split('|')]
        table_name = None
        count_val = None

        # Strict extraction when parts length is enough (we expect at least 4 parts)
        if len(parts) >= 4:
            # parts[0] should be 'TABLE' (or contain it), parts[1] the object name, parts[3] the number
            # defensively handle trimmed/leading tokens
            # find the index of the token which equals/contains 'TABLE' (case-insensitive)
            table_idx = None
            for i, p in enumerate(parts):
                if p and 'TABLE' in p.upper():
                    table_idx = i
                    break
            # assume object at table_idx + 1
            if table_idx is not None and table_idx + 1 < len(parts):
                table_name_candidate = parts[table_idx + 1]
                if table_name_candidate:
                    table_name = table_name_candidate

            # number is typically two fields after object: parts[table_idx + 3] OR simply parts[3] if table at index 0
            # we try parts[3] first (common format)
            try_count_candidates = []
            if len(parts) > 3:
                try_count_candidates.append(parts[3])
            # if table_idx found, also check relative offsets
            if table_idx is not None:
                for offset in (2,3,4):
                    idx = table_idx + offset
                    if 0 <= idx < len(parts):
                        try_count_candidates.append(parts[idx])

            # attempt to parse the first numeric-looking candidate from try_count_candidates
            for cand in try_count_candidates:
                if not cand:
                    continue
                m = _number_re.search(cand)
                if m:
                    count_val = int(m.group(1).replace(',', ''))
                    break

        # fallback: if strict extraction didn't find table_name or count, use regex fallback
        if table_name is None or count_val is None:
            # fallback name: look for "TABLE | <name>" pattern
            mname = re.search(r'TABLE\s*\|\s*([A-Za-z0-9_.\-]+)', ln, re.IGNORECASE)
            if mname:
                table_name = mname.group(1).strip()
            # fallback count: search for the first numeric token that is not followed by MB/KB (prefer commas)
            # but prefer numeric token that has commas (likely a record count) else choose first numeric
            numeric_tokens = _number_re.findall(ln)
            chosen = None
            if numeric_tokens:
                # prefer tokens containing commas
                with_commas = [t for t in numeric_tokens if ',' in t]
                if with_commas:
                    chosen = with_commas[0]
                else:
                    chosen = numeric_tokens[0]
            if chosen:
                count_val = int(chosen.replace(',', ''))

        # final guard: ensure table_name not empty
        if table_name:
            rows.append((table_name, count_val))

    df = pd.DataFrame(rows, columns=['TableName', 'Count'])
    if df.empty:
        return df
    # remove duplicates keeping first occurrence (report sometimes lists same object multiple times)
    df = df.drop_duplicates(subset=['TableName'], keep='first').reset_index(drop=True)
    return df

# ---------------- compare ----------------
def compare_presence(df_before: pd.DataFrame, df_after: pd.DataFrame) -> pd.DataFrame:
    # normalize keys for matching
    d1 = df_before.copy()
    d2 = df_after.copy()
    d1['key'] = d1['TableName'].str.strip().str.lower()
    d2['key'] = d2['TableName'].str.strip().str.lower()

    merged = pd.merge(d1, d2, on='key', how='outer', suffixes=('_before', '_after'))

    # presentation name
    merged['TableName'] = merged['TableName_after'].combine_first(merged['TableName_before'])

    # presence flags
    merged['Present_Before'] = merged['TableName_before'].notna()
    merged['Present_After']  = merged['TableName_after'].notna()

    # convert counts to integers where possible; missing -> NaN then fill with 0 for numeric comparisons
    merged['Count_Before_raw'] = merged['Count_before']  # keep raw
    merged['Count_After_raw']  = merged['Count_after']

    # try to convert; leave NaN if None
    merged['Count_Before'] = pd.to_numeric(merged['Count_Before_raw'], errors='coerce')
    merged['Count_After']  = pd.to_numeric(merged['Count_After_raw'], errors='coerce')

    # Use fillna(0) for difference calculation (so new/dropped show correct diff)
    merged['Count_Before_for_diff'] = merged['Count_Before'].fillna(0).astype(int)
    merged['Count_After_for_diff']  = merged['Count_After'].fillna(0).astype(int)

    # difference = AFTER - BEFORE
    merged['Difference'] = merged['Count_After_for_diff'] - merged['Count_Before_for_diff']

    # Created / Deleted by presence
    merged['Created'] = merged.apply(lambda r: 'YES' if (r['Present_After'] and not r['Present_Before']) else '', axis=1)
    merged['Deleted'] = merged.apply(lambda r: 'YES' if (r['Present_Before'] and not r['Present_After']) else '', axis=1)

    # Status logic
    def st_status(r):
        if r['Created'] == 'YES':
            return 'NEW TABLE'
        if r['Deleted'] == 'YES':
            return 'DELETED TABLE'
        if r['Present_Before'] and r['Present_After']:
            # if both have counts (not NaN) compare; else say PRESENT IN BOTH
            if pd.notna(r['Count_Before']) and pd.notna(r['Count_After']):
                return 'MATCH' if int(r['Count_Before']) == int(r['Count_After']) else 'NOT MATCH'
            return 'PRESENT IN BOTH (no counts)'
        return 'UNKNOWN'

    merged['Status'] = merged.apply(st_status, axis=1)

    # final tidy output
    out = merged[[
        'TableName', 'key', 'Present_Before', 'Present_After',
        'Count_Before', 'Count_After', 'Difference', 'Created', 'Deleted', 'Status'
    ]].copy()

    # rename and format counts: show integers where available
    out['Count_Before'] = out['Count_Before'].apply(lambda x: int(x) if pd.notna(x) else None)
    out['Count_After']  = out['Count_After'].apply(lambda x: int(x) if pd.notna(x) else None)

    return out

# ---------------- UI ----------------
st.subheader("Upload BEFORE and AFTER report files (plain text)")

file_before = st.file_uploader("BEFORE file (.txt)", type=['txt'], key='bef')
file_after  = st.file_uploader("AFTER file (.txt)", type=['txt'], key='aft')

if file_before and file_after:
    text_before = file_before.read().decode(errors='ignore')
    text_after  = file_after.read().decode(errors='ignore')

    with st.spinner("Parsing BEFORE file..."):
        df_before = parse_report_text_by_line_strict(text_before)
    with st.spinner("Parsing AFTER file..."):
        df_after  = parse_report_text_by_line_strict(text_after)

    # quick sanity: show counts parsed
    st.markdown("**Parsed table counts (first 10)**")
    c1, c2 = st.columns(2)
    with c1:
        st.write("BEFORE (first 10)")
        st.dataframe(df_before.head(10))
    with c2:
        st.write("AFTER (first 10)")
        st.dataframe(df_after.head(10))

    merged = compare_presence(df_before, df_after)

    # summary numbers
    total_before = df_before.shape[0]
    total_after  = df_after.shape[0]
    new_count     = (merged['Created'] == 'YES').sum()
    deleted_count = (merged['Deleted'] == 'YES').sum()
    mismatches    = (merged['Status'] == 'NOT MATCH').sum()

    st.markdown("### Summary")
    st.write(f"- Tables in BEFORE file: **{total_before}**")
    st.write(f"- Tables in AFTER file: **{total_after}**")
    st.write(f"- New tables (present in AFTER only): **{new_count}**")
    st.write(f"- Deleted tables (present in BEFORE only): **{deleted_count}**")
    st.write(f"- Tables present in both but counts differ: **{mismatches}**")

    st.markdown("### New tables")
    new_tables = merged[merged['Created'] == 'YES'][['TableName','Count_After']]
    if new_tables.empty:
        st.info("No new tables detected.")
    else:
        st.dataframe(new_tables.reset_index(drop=True))

    st.markdown("### Deleted tables")
    dropped = merged[merged['Deleted'] == 'YES'][['TableName','Count_Before']]
    if dropped.empty:
        st.info("No deleted tables detected.")
    else:
        st.dataframe(dropped.reset_index(drop=True))

    st.markdown("### All comparison rows (sample)")
    st.dataframe(merged.head(200), use_container_width=True)

    # Export Excel
    out_buf = BytesIO()
    with pd.ExcelWriter(out_buf, engine='openpyxl') as writer:
        merged.to_excel(writer, sheet_name='All_Data', index=False)
        merged[merged['Created']=='YES'][['TableName','Count_After']].to_excel(writer, sheet_name='New_Tables', index=False)
        merged[merged['Deleted']=='YES'][['TableName','Count_Before']].to_excel(writer, sheet_name='Deleted_Tables', index=False)
        merged[merged['Status']=='NOT MATCH'][['TableName','Count_Before','Count_After','Difference']].to_excel(writer, sheet_name='Differences', index=False)

    st.download_button("Download full comparison Excel", data=out_buf.getvalue(),
                       file_name="table_comparison.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Upload both BEFORE and AFTER files to begin.")

# Footer
st.markdown("""
<hr style="margin-top:30px;">
<div style="text-align:center; font-size:14px;">Developed by <a href="https://github.com/sahilostwal" target="_blank">sahilostwal</a></div>
""", unsafe_allow_html=True)
