# app.py
import streamlit as st
import re
import pandas as pd
from io import BytesIO
from typing import Optional, Tuple, List

st.set_page_config(page_title="Table Count Comparator (robust parser)", layout="wide")

# ---------------- UI STYLE (minimal) ----------------
st.markdown("""
<style>
body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg,#f0e8ff 0%, #fff0f4 100%); }
.summary { padding:12px; border-radius:10px; background: rgba(255,255,255,0.85); box-shadow:0 6px 18px rgba(0,0,0,0.06); }
.small { font-size:13px; color:#444; }
</style>
""", unsafe_allow_html=True)

st.title("Table Count Comparator — Robust Parser")
st.write("Uploads: BEFORE (pre-install) and AFTER (post-install). Parser uses heuristics to extract table name & record count reliably.")

# ---------------- Helpers: parsing heuristics ----------------
_num_re = re.compile(r'(\d{1,3}(?:,\d{3})*|\d+)(?!\.\d)')  # whole integers, allow comma groups
table_label_re = re.compile(r'\bTABLE\b', re.IGNORECASE)

def extract_tokens_from_line(line: str) -> Tuple[Optional[str], List[str]]:
    """
    Split a line into 'parts' by '|' and return cleaned parts and an indicator whether it contains 'TABLE'.
    """
    parts = [p.strip() for p in line.split('|')]
    return parts

def find_table_name(parts: List[str], line: str) -> Optional[str]:
    """
    Heuristic to locate the table/object name in the parts list.
    Typical formats:
      - TABLE | object | description | 12345 | ...
      - ... | TABLE | object | ...
      - object | 12345
    Strategy:
      1. If 'TABLE' token present, return next non-empty part after it.
      2. Else, consider first alphanumeric token that looks like an object name (letters/digits/_).
    """
    # 1) find explicit TABLE token in parts
    for i, p in enumerate(parts):
        if table_label_re.search(p):
            # pick the next part that looks like an object name
            for j in range(i+1, min(i+4, len(parts))):
                candidate = parts[j].strip()
                if candidate:
                    # strip punctuation
                    candidate_clean = re.sub(r'^[^\w]+|[^\w]+$', '', candidate)
                    if candidate_clean:
                        return candidate_clean
    # 2) fallback: pick first part that looks like object token (letters/digits/underscore, not numeric only)
    for p in parts:
        p_clean = p.strip()
        if p_clean and not _num_re.fullmatch(p_clean.replace(',', '')):
            # ensure it's not header-like ('Description' etc)
            if re.search(r'[A-Za-z]', p_clean):
                # avoid words like 'ROW LENGTH' or 'SIZE' as table names
                if not re.search(r'\b(row|length|size|mb|bytes|type|desc|description|count|records)\b', p_clean, re.IGNORECASE):
                    # return cleaned token
                    return re.sub(r'^[^\w]+|[^\w]+$', '', p_clean)
    # 3) absolute fallback: try to capture a token after 'TABLE' in the raw line via regex
    m = re.search(r'TABLE\s*\|\s*([A-Za-z0-9_\-\.]+)', line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def candidate_numbers_from_parts(parts: List[str], line: str) -> List[Tuple[int,str,int]]:
    """
    Return list of candidate numeric tokens with basic scoring:
    returns list of tuples (score, raw_token, int_value)
    Higher score means more likely to be record count.
    Heuristics:
      - tokens containing commas are preferred (score +20)
      - tokens appearing earlier near the object name get higher score (proximity)
      - larger reasonable size preferred (score by log10(value))
      - tokens followed/preceded by 'records' or 'count' get high boost
    """
    candidates = []
    # find all numeric tokens in parts and in the raw line
    # use regex to find all integer-like tokens
    for m in _num_re.finditer(line):
        raw = m.group(1)
        try:
            val = int(raw.replace(',', ''))
        except:
            continue
        score = 0
        # comma boost
        if ',' in raw:
            score += 20
        # magnitude boost (prefer > 10)
        if val > 1000000000:
            score -= 50  # extremely large suspicious
        else:
            # small boost roughly proportional to log
            import math
            score += int(math.log10(val+1) * 2) if val>0 else 0
        # token context: look +/- 20 chars for 'records' 'count'
        span_start, span_end = m.span()
        ctx = line[max(0, span_start-20):min(len(line), span_end+20)].lower()
        if 'record' in ctx or 'count' in ctx or 'rows' in ctx:
            score += 30
        # also penalize if followed by 'MB' or 'KB' (size)
        if re.search(r'\b' + re.escape(raw) + r'\s*(MB|KB|GB)\b', line, re.IGNORECASE):
            score -= 25
        # proximity to 'TABLE' or to object name is handled outside using part positions
        candidates.append((score, raw, val))
    # collapse duplicates (same val) keeping max score
    by_val = {}
    for score, raw, val in candidates:
        if val not in by_val or score > by_val[val][0]:
            by_val[val] = (score, raw)
    out = [(s, r, v) for v, (s, r) in by_val.items()]
    # sort by score desc
    out.sort(reverse=True, key=lambda x: x[0])
    return out

def pick_best_count(parts: List[str], table_name: Optional[str], line: str) -> Tuple[Optional[int], str]:
    """
    Choose the best candidate numeric token as record count and provide reason text.
    Returns (count_or_None, reason)
    """
    # if parts length has expected layout, try direct indices (most robust)
    # typical layout we observed: parts = ['TABLE', '<obj>', '<desc>', '<count>', ...]
    reason = ""
    # normalized parts for searching
    if table_name:
        # attempt to find the part index where table_name is located
        for idx, p in enumerate(parts):
            if p and table_name.lower() in p.lower():
                # prefer numeric token 2 positions after table name (desc then count)
                cand_idx = idx + 2
                if cand_idx < len(parts):
                    if _num_re.search(parts[cand_idx]):
                        num_m = _num_re.search(parts[cand_idx])
                        val = int(num_m.group(1).replace(',', ''))
                        return val, f"picked from parts[{cand_idx}] (near table name)"
                # else try next two positions forward
                for j in range(idx+1, min(len(parts), idx+5)):
                    if _num_re.search(parts[j]):
                        num_m = _num_re.search(parts[j])
                        val = int(num_m.group(1).replace(',', ''))
                        return val, f"picked from parts[{j}] (first numeric after table name)"
                break
    # if nothing found by index heuristics, score all numeric candidates in line
    candidates = candidate_numbers_from_parts(parts, line)
    if candidates:
        chosen = candidates[0]
        return chosen[2], f"picked by scoring (best candidate raw='{chosen[1]}', score={chosen[0]})"
    # no numeric found
    return None, "no numeric candidate found"

# ---------------- Parsing function that returns dataframe with diagnostics ----------------
def parse_text_to_df(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if 'TABLE' not in line.upper() and '|' not in line:
            # sometimes files have lines without TABLE keyword but with object|count; still try
            if not _num_re.search(line):
                continue
        parts = extract_tokens_from_line(line)
        table_name = find_table_name(parts, line)
        count, reason = pick_best_count(parts, table_name, line)
        rows.append({
            "raw_line": line,
            "TableName": table_name or "",
            "Count": int(count) if count is not None else None,
            "parse_reason": reason
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # normalize keys for matching: lower-case stripped table name
    df["key"] = df["TableName"].str.strip().str.lower()
    # drop rows lacking table name
    df = df[df["TableName"].str.strip() != ""].copy()
    # dedupe on key keeping first parsed line
    df = df.drop_duplicates(subset="key", keep="first").reset_index(drop=True)
    return df

# ---------------- Compare logic ----------------
def compare_dfs(df_before: pd.DataFrame, df_after: pd.DataFrame) -> pd.DataFrame:
    a = df_before[["key", "TableName", "Count"]].rename(columns={"TableName":"TableName_Before","Count":"Before_Count"})
    b = df_after[["key", "TableName", "Count"]].rename(columns={"TableName":"TableName_After","Count":"After_Count"})
    merged = pd.merge(a, b, on="key", how="outer")
    # display name prefer After then Before else key
    merged["TableName"] = merged["TableName_After"].combine_first(merged["TableName_Before"]).fillna(merged["key"])
    # counts normalized (None->NaN->we'll keep None semantics)
    merged["Before_Count"] = merged["Before_Count"].where(pd.notna(merged["Before_Count"]), None)
    merged["After_Count"]  = merged["After_Count"].where(pd.notna(merged["After_Count"]), None)
    # flags for presence
    merged["Present_Before"] = merged["Before_Count"].notna()
    merged["Present_After"]  = merged["After_Count"].notna()
    # Created/Deleted based on presence
    merged["Created"] = merged.apply(lambda r: "YES" if (r["Present_After"] and not r["Present_Before"]) else "", axis=1)
    merged["Deleted"] = merged.apply(lambda r: "YES" if (r["Present_Before"] and not r["Present_After"]) else "", axis=1)
    # Difference only when both counts present
    def diff_val(r):
        if (r["Before_Count"] is not None) and (r["After_Count"] is not None):
            return int(r["After_Count"]) - int(r["Before_Count"])
        return None
    merged["Difference"] = merged.apply(diff_val, axis=1)
    def status_row(r):
        if r["Created"] == "YES": return "NEW TABLE"
        if r["Deleted"] == "YES": return "DELETED TABLE"
        if (r["Before_Count"] is not None) and (r["After_Count"] is not None):
            return "MATCH" if r["Before_Count"] == r["After_Count"] else "MISMATCH"
        # present in both but counts missing in one or both
        if r["Present_Before"] and r["Present_After"]:
            return "PRESENT (no counts)" 
        return "UNKNOWN"
    merged["Status"] = merged.apply(status_row, axis=1)
    # order columns
    out = merged[["TableName", "Before_Count", "After_Count", "Difference", "Created", "Deleted", "Status", "key"]].copy()
    return out

# ---------------- UI controls ----------------
st.subheader("Upload BEFORE and AFTER report files (plain text)")
c1, c2 = st.columns(2)
with c1:
    f_before = st.file_uploader("BEFORE file", type=["txt"], key="bef_fp")
with c2:
    f_after = st.file_uploader("AFTER file", type=["txt"], key="aft_fp")

debug_mode = st.checkbox("Show parse diagnostics (debug)", value=False)

if f_before and f_after:
    raw_before = f_before.read().decode("utf-8", errors="ignore")
    raw_after  = f_after.read().decode("utf-8", errors="ignore")
    with st.spinner("Parsing BEFORE file..."):
        df_before = parse_text_to_df(raw_before)
    with st.spinner("Parsing AFTER file..."):
        df_after = parse_text_to_df(raw_after)

    if df_before.empty:
        st.warning("No table rows parsed from BEFORE file. Check format.")
    if df_after.empty:
        st.warning("No table rows parsed from AFTER file. Check format.")

    result = compare_dfs(df_before, df_after)

    # summary
    total_before = len(df_before)
    total_after  = len(df_after)
    new_cnt = (result["Created"] == "YES").sum()
    del_cnt = (result["Deleted"] == "YES").sum()
    mism_cnt = (result["Status"] == "MISMATCH").sum()
    st.markdown(f"**Summary** — BEFORE: **{total_before}**  AFTER: **{total_after}**  NEW: **{new_cnt}**  DELETED: **{del_cnt}**  MISMATCH: **{mism_cnt}**")

    st.markdown("### Comparison result")
    st.dataframe(result.drop(columns=["key"]), use_container_width=True)

    if debug_mode:
        st.markdown("### Parse diagnostics — BEFORE (rows with missing or suspicious counts)")
        if not df_before.empty:
            # show parse reasons
            df_b_dbg = df_before[df_before["Count"].isna() | (df_before["Count"] == 0)].copy()
            st.dataframe(df_b_dbg[["TableName","Count","parse_reason","raw_line"]], use_container_width=True)
        st.markdown("### Parse diagnostics — AFTER (rows with missing or suspicious counts)")
        if not df_after.empty:
            df_a_dbg = df_after[df_after["Count"].isna() | (df_after["Count"] == 0)].copy()
            st.dataframe(df_a_dbg[["TableName","Count","parse_reason","raw_line"]], use_container_width=True)

    # Export Excel with sheets
    out_buf = BytesIO()
    with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
        result.to_excel(writer, sheet_name="All_Comparison", index=False)
        result[result["Status"]=="MISMATCH"].to_excel(writer, sheet_name="Mismatches", index=False)
        result[result["Created"]=="YES"].to_excel(writer, sheet_name="New_Tables", index=False)
        result[result["Deleted"]=="YES"].to_excel(writer, sheet_name="Deleted_Tables", index=False)
        if debug_mode:
            df_before.to_excel(writer, sheet_name="Parse_BEFORE", index=False)
            df_after.to_excel(writer, sheet_name="Parse_AFTER", index=False)
    out_val = out_buf.getvalue()

    st.download_button("Download full comparison Excel", data=out_val, file_name="table_comparison.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.info("Upload both BEFORE and AFTER text files to start comparison.")

st.markdown("<hr style='margin-top:20px'/>", unsafe_allow_html=True)
st.markdown("Developed by [sahilostwal](https://github.com/sahilostwal)")

