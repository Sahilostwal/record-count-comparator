# app.py
import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Record-by-Record Comparator", layout="wide")
st.title("Record-by-Record Comparator")

st.write("Upload two plain text files (one record per line). The app compares records and produces an Excel report.")

file1 = st.file_uploader("Upload First Notepad File (File 1)", type=["txt"], key="f1")
file2 = st.file_uploader("Upload Second Notepad File (File 2)", type=["txt"], key="f2")

def read_text_lines(uploaded_file, max_lines=None):
    """
    Read uploaded file as text and return list of stripped non-empty lines.
    max_lines: optional limit to read for memory safety (None = read all)
    """
    raw = uploaded_file.read()
    # decode best-effort
    try:
        text = raw.decode("utf-8")
    except Exception:
        try:
            text = raw.decode("latin-1")
        except Exception:
            text = raw.decode("utf-8", errors="ignore")
    # split into lines and clean
    lines = text.splitlines()
    cleaned = []
    for i, line in enumerate(lines):
        if max_lines and i >= max_lines:
            break
        s = line.strip()
        if s:
            cleaned.append(s)
    return cleaned

def make_excel_bytes(df_summary, df_matched, df_miss1, df_miss2):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="Summary", index=False)
        df_matched.to_excel(writer, sheet_name="Matched", index=False)
        df_miss1.to_excel(writer, sheet_name="Missing_in_File1", index=False)
        df_miss2.to_excel(writer, sheet_name="Missing_in_File2", index=False)
    output.seek(0)
    return output.getvalue()

if file1 and file2:
    # read lines safely
    with st.spinner("Reading files..."):
        list1 = read_text_lines(file1)
        list2 = read_text_lines(file2)

    # quick UI summary
    st.subheader("Quick counts (raw lines read)")
    st.write(f"- File 1 raw lines: **{len(list1)}**")
    st.write(f"- File 2 raw lines: **{len(list2)}**")

    # convert to sets for comparison (unique values)
    set1 = set(list1)
    set2 = set(list2)

    matched = sorted(set1 & set2)
    missing_in_file2 = sorted(set1 - set2)   # present in file1, missing in file2
    missing_in_file1 = sorted(set2 - set1)   # present in file2, missing in file1

    # Prepare DataFrames
    df_summary = pd.DataFrame({
        "File": ["File 1", "File 2"],
        "Record Count (lines)": [len(list1), len(list2)],
        "Unique Records": [len(set1), len(set2)]
    })

    df_matched = pd.DataFrame(matched, columns=["Matched Records"])
    df_missing2 = pd.DataFrame(missing_in_file2, columns=["Missing in File 2"])
    df_missing1 = pd.DataFrame(missing_in_file1, columns=["Missing in File 1"])

    # Show summary and status
    st.subheader("Summary")
    st.dataframe(df_summary, height=120)

    if not missing_in_file1 and not missing_in_file2:
        st.success("All records MATCH ✔")
    else:
        st.error("Records do NOT match ❌")

    # Show small previews (first 20)
    st.subheader("Preview - matched / missing (first 20)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Matched (top 20)**")
        st.write(df_matched.head(20))
    with col2:
        st.markdown("**Missing in File 2 (top 20)**")
        st.write(df_missing2.head(20))
    with col3:
        st.markdown("**Missing in File 1 (top 20)**")
        st.write(df_missing1.head(20))

    # Build and provide Excel download
    excel_bytes = make_excel_bytes(df_summary, df_matched, df_missing1, df_missing2)
    st.download_button(
        label="📥 Download Full Comparison Excel",
        data=excel_bytes,
        file_name="Record_Level_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Optional: show counts
    st.markdown("---")
    st.write(f"Matched: **{len(matched)}** | Missing in File2: **{len(missing_in_file2)}** | Missing in File1: **{len(missing_in_file1)}**")

else:
    st.info("Please upload both files (File 1 and File 2) to start comparison.")
