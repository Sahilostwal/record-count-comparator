# app.py
import re
import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Table Record Count Comparator", layout="centered")
st.title("📊 Table Record Count Comparator")
st.write("Upload two raw report files (text / CSV / Excel). The app parses table names and record counts, compares them and produces an Excel report you can download.")

def parse_report_text(text: str):
    rows = []
    pattern1 = re.compile(r'\bTABLE\s*\|\s*([^\|]+?)\s*\|.*?\|\s*([\d,]+)\b', re.IGNORECASE)
    for m in pattern1.finditer(text):
        table = m.group(1).strip()
        cnt = int(m.group(2).replace(',', ''))
        rows.append((table, cnt))
    if not rows:
        pattern2 = re.compile(r'([A-Za-z0-9_.\-\s]+?)\s*\|\s*([\d,]+)')
        for m in pattern2.finditer(text):
            table = m.group(1).strip()
            cnt = int(m.group(2).replace(',', ''))
            rows.append((table, cnt))
    if not rows:
        pattern3 = re.compile(r'([A-Za-z0-9_.\-\s]+?)\s*[:\-]\s*([\d,]+)')
        for m in pattern3.finditer(text):
            table = m.group(1).strip()
            cnt = int(m.group(2).replace(',', ''))
            rows.append((table, cnt))
    df = pd.DataFrame(rows, columns=['TableName', 'Count'])
    return df

def read_uploaded_file(uploaded_file):
    name = uploaded_file.name.lower()
    content = uploaded_file.read()
    if name.endswith(('.xls', '.xlsx')):
        try:
            d = pd.read_excel(io.BytesIO(content))
        except Exception:
            text = content.decode(errors='ignore')
            return parse_report_text(text)
        cols = {c.lower(): c for c in d.columns}
        name_col = cols.get('object') or cols.get('tablename') or cols.get('table') or cols.get('table name') or cols.get('table_name')
        count_col = cols.get('number of records') or cols.get('records') or cols.get('count') or cols.get('number_of_records')
        if name_col and count_col:
            df = d[[name_col, count_col]].copy()
            df.columns = ['TableName', 'Count']
            df['Count'] = df['Count'].astype(str).str.replace(',', '').astype(int)
            return df
        text = d.astype(str).to_csv(index=False)
        return parse_report_text(text)

    if name.endswith('.csv'):
        try:
            d = pd.read_csv(io.StringIO(content.decode()))
            cols = {c.lower(): c for c in d.columns}
            name_col = cols.get('object') or cols.get('tablename') or cols.get('table') or cols.get('table name') or cols.get('table_name')
            count_col = cols.get('number of records') or cols.get('records') or cols.get('count') or cols.get('number_of_records')
            if name_col and count_col:
                df = d[[name_col, count_col]].copy()
                df.columns = ['TableName', 'Count']
                df['Count'] = df['Count'].astype(str).str.replace(',', '').astype(int)
                return df
            return parse_report_text(content.decode(errors='ignore'))
        except Exception:
            return parse_report_text(content.decode(errors='ignore'))

    text = content.decode(errors='ignore')
    return parse_report_text(text)

def normalize_df(df):
    df = df.copy()
    df['TableKey'] = df['TableName'].str.strip().str.lower()
    return df

def compare_dfs(df1, df2, name1='Source', name2='Target'):
    d1 = normalize_df(df1).rename(columns={'Count': f'{name1}Count'})
    d2 = normalize_df(df2).rename(columns={'Count': f'{name2}Count'})
    merged = pd.merge(d1, d2, on='TableKey', how='outer', suffixes=('_s', '_t'))
    merged['TableName'] = merged['TableName_s'].combine_first(merged['TableName_t'])
    merged[f'{name1}Count'] = merged[f'{name1}Count'].fillna(0).astype(int)
    merged[f'{name2}Count'] = merged[f'{name2}Count'].fillna(0).astype(int)
    merged['Difference'] = merged[f'{name1}Count'] - merged[f'{name2}Count']
    def status(row):
        if (row[f'{name1}Count'] == 0) and (row[f'{name2}Count'] == 0):
            return 'Both Zero'
        if row[f'{name1}Count'] == 0:
            return f'Missing in {name1}'
        if row[f'{name2}Count'] == 0:
            return f'Missing in {name2}'
        return 'Match' if row['Difference'] == 0 else 'Count Changed'
    merged['Status'] = merged.apply(status, axis=1)
    merged = merged[['TableName', f'{name1}Count', f'{name2}Count', 'Difference', 'Status']]
    return merged

def make_excel_bytes(merged_df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        total = len(merged_df)
        matches = (merged_df['Status'] == 'Match').sum()
        changed = (merged_df['Status'] == 'Count Changed').sum()
        missing_src = (merged_df['Status'] == 'Missing in Source').sum()
        missing_tgt = (merged_df['Status'] == 'Missing in Target').sum()
        summary = pd.DataFrame([
            ['Total Tables Compared', total],
            ['Matches', matches],
            ['Count Changed', changed],
            ['Missing in Source', missing_src],
            ['Missing in Target', missing_tgt]
        ], columns=['Metric', 'Value'])
        summary.to_excel(writer, sheet_name='Summary', index=False)
        merged_df.to_excel(writer, sheet_name='All', index=False)
        merged_df[merged_df['Status'] != 'Match'].to_excel(writer, sheet_name='Differences', index=False)
        writer.save()
    output.seek(0)
    return output

# UI
st.sidebar.header("Settings")
sheet_name_prefix = st.sidebar.text_input("Output filename prefix", value="Record_Comparison")
show_raw_preview = st.sidebar.checkbox("Show parsed preview", value=True)

st.markdown("### 1) Upload source and target files")
col1, col2 = st.columns(2)
with col1:
    src_file = st.file_uploader("Upload Source file", type=['txt','csv','xls','xlsx'], key="src")
with col2:
    tgt_file = st.file_uploader("Upload Target file", type=['txt','csv','xls','xlsx'], key="tgt")

st.markdown("---")
st.write("When both files are uploaded, click **Compare**.")
if st.button("Compare"):
    if not src_file or not tgt_file:
        st.error("Please upload both Source and Target files before comparing.")
    else:
        try:
            df_src = read_uploaded_file(src_file)
            df_tgt = read_uploaded_file(tgt_file)
            if df_src.empty:
                st.warning("No rows parsed from Source file. Check file format or upload a different file.")
            if df_tgt.empty:
                st.warning("No rows parsed from Target file. Check file format or upload a different file.")
            if show_raw_preview:
                st.subheader("Parsed preview — Source (top 10)")
                st.dataframe(df_src.head(10))
                st.subheader("Parsed preview — Target (top 10)")
                st.dataframe(df_tgt.head(10))
            merged = compare_dfs(df_src, df_tgt, name1='Source', name2='Target')
            st.success("Comparison complete.")
            st.subheader("Summary")
            st.write(f"- Total tables compared: **{len(merged)}**")
            st.write(f"- Matches: **{(merged['Status']=='Match').sum()}**")
            st.write(f"- Count changed: **{(merged['Status']=='Count Changed').sum()}**")
            st.write(f"- Missing in Source: **{(merged['Status']=='Missing in Source').sum()}**")
            st.write(f"- Missing in Target: **{(merged['Status']=='Missing in Target').sum()}**")
            st.subheader("Differences (non-matching rows)")
            diffs = merged[merged['Status'] != 'Match'].copy()
            if diffs.empty:
                st.info("All rows match — no differences found.")
            else:
                st.dataframe(diffs)
            excel_bytes = make_excel_bytes(merged)
            out_name = f"{sheet_name_prefix}.xlsx"
            st.download_button(
                label="📥 Download comparison Excel",
                data=excel_bytes,
                file_name=out_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.exception(f"Error during processing: {e}")

st.caption("Uploads are processed in-memory. No files are saved on server disk.")
