import streamlit as st
import pandas as pd
from io import BytesIO

st.title("Record Count Comparator")

file1 = st.file_uploader("Upload First Notepad File", type=["txt"])
file2 = st.file_uploader("Upload Second Notepad File", type=["txt"])

if file1 and file2:
    # Read files
    df1 = pd.read_csv(file1, delimiter="\t", header=None, names=["Record"])
    df2 = pd.read_csv(file2, delimiter="\t", header=None, names=["Record"])

    # Remove blank lines
    df1 = df1[df1["Record"].notna()]
    df2 = df2[df2["Record"].notna()]

    count1 = len(df1)
    count2 = len(df2)

    # Create comparison result
    result = pd.DataFrame({
        "File": ["File 1", "File 2"],
        "Record Count": [count1, count2]
    })

    if count1 == count2:
        status = "Matched ✔"
    else:
        status = "Not Matched ❌"

    st.subheader("Comparison Result")
    st.write(result)
    st.write("Status:", status)

    # Prepare Excel in memory (THIS FIXES YOUR ERROR)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result.to_excel(writer, index=False, sheet_name="Comparison")

    excel_data = output.getvalue()

    st.download_button(
        label="Download Comparison Excel",
        data=excel_data,
        file_name="Record_Comparison.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
