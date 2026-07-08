"""
app.py
------
OCR Text Comparison & Error Detection Tool

A Streamlit web app that intelligently compares OCR-extracted text against a
correct reference text, highlighting missing / extra / replaced / split /
merged words, with statistics, a detailed diff table, and export options.

Run with:
    streamlit run app.py
"""

import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from comparison import (
    CORRECT,
    DIFF_COLORS,
    DIFF_ICONS,
    EXTRA,
    MERGED_WORD,
    MISSING,
    REPLACEMENT,
    SPLIT_WORD,
    build_side_by_side,
    compare_tokens,
    compute_stats,
    overall_similarity,
    tokenize_text,
)

# =============================================================================
# Page configuration & global styling
# =============================================================================

st.set_page_config(
    page_title="OCR Text Comparison Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Metric-style cards */
    .metric-card {
        background: linear-gradient(135deg, rgba(46,204,113,0.12), rgba(46,204,113,0.03));
        border: 1px solid rgba(46,204,113,0.35);
        border-radius: 14px;
        padding: 1.4rem 1rem;
        text-align: center;
    }
    .metric-card h1 {
        font-size: 2.6rem;
        margin: 0;
        color: #2ecc71;
    }
    .metric-card p {
        margin: 0.2rem 0 0 0;
        opacity: 0.75;
        font-size: 0.95rem;
    }
    .stat-box {
        border-radius: 10px;
        padding: 0.8rem 0.6rem;
        text-align: center;
        border: 1px solid rgba(128,128,128,0.25);
    }
    .stat-box h3 { margin: 0; font-size: 1.6rem; }
    .stat-box p { margin: 0.15rem 0 0 0; font-size: 0.8rem; opacity: 0.7; }

    .diff-panel {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 10px;
        padding: 1rem;
        line-height: 2.1;
        font-size: 1.02rem;
        max-height: 480px;
        overflow-y: auto;
    }
    .legend-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# Session state initialization
# =============================================================================

if "compared" not in st.session_state:
    st.session_state.compared = False
if "current_diff_idx" not in st.session_state:
    st.session_state.current_diff_idx = 0

# =============================================================================
# Sidebar - options
# =============================================================================

st.sidebar.title("⚙️ Comparison Options")

ignore_case = st.sidebar.checkbox("Ignore Case", value=True)
ignore_punct = st.sidebar.checkbox("Ignore Punctuation", value=True)
ignore_spaces = st.sidebar.checkbox("Ignore Extra Spaces", value=True)
trim_spaces = st.sidebar.checkbox("Trim Leading/Trailing Spaces", value=True)

st.sidebar.markdown("---")
fuzzy_threshold = st.sidebar.slider(
    "Fuzzy Match Threshold (%)",
    min_value=50,
    max_value=100,
    value=80,
    step=1,
    help="Word pairs scoring above this RapidFuzz similarity are treated as "
    "a 'Replacement' rather than an unrelated Missing/Extra pair.",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Legend**\n\n"
    f"<span class='legend-badge' style='background:{DIFF_COLORS[CORRECT]}33;color:{DIFF_COLORS[CORRECT]}'>✅ Correct</span><br><br>"
    f"<span class='legend-badge' style='background:{DIFF_COLORS[REPLACEMENT]}33;color:{DIFF_COLORS[REPLACEMENT]}'>🟠 Replacement</span><br><br>"
    f"<span class='legend-badge' style='background:{DIFF_COLORS[MISSING]}33;color:{DIFF_COLORS[MISSING]}'>🔴 Missing</span><br><br>"
    f"<span class='legend-badge' style='background:{DIFF_COLORS[EXTRA]}33;color:{DIFF_COLORS[EXTRA]}'>🔵 Extra</span><br><br>"
    f"<span class='legend-badge' style='background:{DIFF_COLORS[SPLIT_WORD]}33;color:{DIFF_COLORS[SPLIT_WORD]}'>🟣 Split/Merged</span>",
    unsafe_allow_html=True,
)

# =============================================================================
# Header
# =============================================================================

st.title("🔍 OCR Text Comparison & Error Detection")
st.caption(
    "Paste your OCR-extracted text and the correct reference text below, then "
    "click **Compare Text** for an intelligent, word-level quality check."
)

# =============================================================================
# Input columns
# =============================================================================

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("OCR Extracted Text")
    ocr_text = st.text_area(
        "OCR Extracted Text",
        height=280,
        placeholder="Paste OCR text here...",
        label_visibility="collapsed",
        key="ocr_input",
    )

with col_right:
    st.subheader("Correct Reference Text")
    correct_text = st.text_area(
        "Correct Reference Text",
        height=280,
        placeholder="Paste correct text here...",
        label_visibility="collapsed",
        key="correct_input",
    )

_, btn_col, _ = st.columns([1, 2, 1])
with btn_col:
    compare_clicked = st.button("🔎 Compare Text", use_container_width=True, type="primary")

# =============================================================================
# Run comparison
# =============================================================================

if compare_clicked:
    if not ocr_text.strip() or not correct_text.strip():
        st.warning("Please paste text into both boxes before comparing.")
        st.session_state.compared = False
    else:
        ocr_tokens = tokenize_text(
            ocr_text, ignore_case, ignore_punct, ignore_spaces, trim_spaces
        )
        correct_tokens = tokenize_text(
            correct_text, ignore_case, ignore_punct, ignore_spaces, trim_spaces
        )
        records = compare_tokens(ocr_tokens, correct_tokens, fuzzy_threshold)
        stats = compute_stats(records, ocr_tokens, correct_tokens)
        similarity = overall_similarity(ocr_tokens, correct_tokens)
        ocr_html, correct_html = build_side_by_side(ocr_tokens, correct_tokens, records)

        st.session_state.compared = True
        st.session_state.records = records
        st.session_state.stats = stats
        st.session_state.similarity = similarity
        st.session_state.ocr_html = ocr_html
        st.session_state.correct_html = correct_html
        st.session_state.current_diff_idx = 0

# =============================================================================
# Results
# =============================================================================

if st.session_state.compared:
    records = st.session_state.records
    stats = st.session_state.stats
    similarity = st.session_state.similarity

    st.markdown("---")

    # ---- Similarity metric card --------------------------------------------
    st.markdown(
        f"""
        <div class="metric-card">
            <p>OVERALL SIMILARITY</p>
            <h1>{similarity:.1f}%</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    # ---- Statistics grid ----------------------------------------------------
    stat_cols = st.columns(4)
    stat_items = list(stats.items())
    stat_colors = {
        "Total OCR Words": "#7f8c8d",
        "Correct Words": "#7f8c8d",
        "Matched Words": DIFF_COLORS[CORRECT],
        "Incorrect Words": DIFF_COLORS[REPLACEMENT],
        "Missing Words": DIFF_COLORS[MISSING],
        "Extra Words": DIFF_COLORS[EXTRA],
        "Replacement Count": DIFF_COLORS[REPLACEMENT],
        "Accuracy %": DIFF_COLORS[CORRECT],
    }
    for i, (label, value) in enumerate(stat_items):
        color = stat_colors.get(label, "#7f8c8d")
        with stat_cols[i % 4]:
            display_val = f"{value}%" if label == "Accuracy %" else value
            st.markdown(
                f"""
                <div class="stat-box" style="border-color:{color}66;">
                    <h3 style="color:{color};">{display_val}</h3>
                    <p>{label}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if (i + 1) % 4 == 0 and i != len(stat_items) - 1:
            st.write("")

    st.markdown("---")

    # ---- Side-by-side highlighted view --------------------------------------
    st.subheader("📄 Side-by-Side Highlighted View")
    hl_left, hl_right = st.columns(2)
    with hl_left:
        st.markdown("**OCR Extracted Text**")
        st.markdown(
            f'<div class="diff-panel">{st.session_state.ocr_html}</div>',
            unsafe_allow_html=True,
        )
    with hl_right:
        st.markdown("**Correct Reference Text**")
        st.markdown(
            f'<div class="diff-panel">{st.session_state.correct_html}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ---- Difference navigator (bonus: search / jump / prev-next) ------------
    st.subheader("🧭 Difference Navigator")

    diff_records = [r for r in records if r["diff_type"] != CORRECT]
    total_diffs = len(diff_records)

    search_term = st.text_input(
        "🔎 Search Difference (matches OCR or Correct word)", value=""
    )

    filtered = diff_records
    if search_term.strip():
        term = search_term.strip().lower()
        filtered = [
            r
            for r in diff_records
            if term in r["ocr_word"].lower() or term in r["correct_word"].lower()
        ]

    if total_diffs == 0:
        st.success("🎉 No differences found — texts match perfectly!")
    elif not filtered:
        st.info("No differences match your search term.")
    else:
        max_idx = len(filtered) - 1
        if st.session_state.current_diff_idx > max_idx:
            st.session_state.current_diff_idx = 0

        nav_prev, nav_counter, nav_next = st.columns([1, 2, 1])
        with nav_prev:
            if st.button("⬅️ Previous", use_container_width=True):
                st.session_state.current_diff_idx = (
                    st.session_state.current_diff_idx - 1
                ) % len(filtered)
        with nav_counter:
            st.markdown(
                f"<div style='text-align:center; padding-top:8px;'>"
                f"Difference <b>{st.session_state.current_diff_idx + 1}</b> of <b>{len(filtered)}</b> "
                f"(Total diffs: {total_diffs})</div>",
                unsafe_allow_html=True,
            )
        with nav_next:
            if st.button("Next ➡️", use_container_width=True):
                st.session_state.current_diff_idx = (
                    st.session_state.current_diff_idx + 1
                ) % len(filtered)

        current = filtered[st.session_state.current_diff_idx]
        color = DIFF_COLORS.get(current["diff_type"], "#999999")
        icon = DIFF_ICONS.get(current["diff_type"], "")
        st.markdown(
            f"""
            <div class="stat-box" style="border-color:{color}66; text-align:left; padding:1rem;">
                <p style="margin-bottom:6px;">{icon} <b>{current['diff_type']}</b>
                &nbsp;|&nbsp; Line {current['line'] if current['line'] else '-'}
                &nbsp;|&nbsp; Similarity: {current['similarity']}%</p>
                <p style="margin:0;">OCR: <code>{current['ocr_word']}</code>
                &nbsp;&nbsp;→&nbsp;&nbsp; Correct: <code>{current['correct_word']}</code></p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ---- Detailed difference table ------------------------------------------
    st.subheader("📊 Detailed Difference Table")

    df = pd.DataFrame(
        [
            {
                "Line Number": r["line"],
                "OCR Word": r["ocr_word"],
                "Correct Word": r["correct_word"],
                "Difference Type": r["diff_type"],
                "Status": f"{DIFF_ICONS.get(r['diff_type'], '')} {r['diff_type']}",
                "Similarity %": r["similarity"],
            }
            for r in records
        ]
    )

    show_only_diffs = st.checkbox("Show only differences (hide Correct rows)", value=True)
    table_df = df[df["Difference Type"] != CORRECT] if show_only_diffs else df

    def _highlight_row(row):
        color = DIFF_COLORS.get(row["Difference Type"], "#999999")
        return [f"background-color: {color}22"] * len(row)

    st.dataframe(
        table_df.style.apply(_highlight_row, axis=1),
        use_container_width=True,
        height=380,
    )

    st.markdown("---")

    # ---- Export options -------------------------------------------------------
    st.subheader("💾 Export Results")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    exp1, exp2, exp3, exp4 = st.columns(4)

    with exp1:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ CSV",
            data=csv_bytes,
            file_name=f"ocr_diff_{timestamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with exp2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Differences")
            pd.DataFrame([stats]).to_excel(writer, index=False, sheet_name="Summary")
        st.download_button(
            "⬇️ Excel",
            data=excel_buffer.getvalue(),
            file_name=f"ocr_diff_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with exp3:
        json_payload = json.dumps(
            {"similarity": similarity, "stats": stats, "differences": records},
            indent=2,
            ensure_ascii=False,
        )
        st.download_button(
            "⬇️ JSON",
            data=json_payload.encode("utf-8"),
            file_name=f"ocr_diff_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
        )

    with exp4:
        report_lines = [
            "OCR TEXT COMPARISON REPORT",
            "=" * 40,
            f"Generated: {datetime.now().isoformat(timespec='seconds')}",
            f"Overall Similarity: {similarity:.1f}%",
            "",
            "SUMMARY",
            "-" * 40,
        ]
        for k, v in stats.items():
            report_lines.append(f"{k}: {v}")
        report_lines += ["", "DIFFERENCES", "-" * 40]
        for r in diff_records:
            report_lines.append(
                f"[{r['diff_type']}] Line {r['line']}: "
                f"OCR='{r['ocr_word']}' -> Correct='{r['correct_word']}' "
                f"(similarity={r['similarity']}%)"
            )
        report_text = "\n".join(report_lines)
        st.download_button(
            "⬇️ TXT Report",
            data=report_text.encode("utf-8"),
            file_name=f"ocr_diff_report_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("---")

    # ---- Copy results ---------------------------------------------------------
    st.subheader("📋 Copy Results")
    st.caption("Use the copy icon in the top-right corner of each box below.")

    copy_col1, copy_col2 = st.columns(2)
    with copy_col1:
        st.markdown("**Copy Difference Table (CSV)**")
        st.code(df.to_csv(index=False), language="text")

    with copy_col2:
        st.markdown("**Copy Summary**")
        summary_text = "\n".join(f"{k}: {v}" for k, v in stats.items())
        summary_text = f"Overall Similarity: {similarity:.1f}%\n" + summary_text
        st.code(summary_text, language="text")

else:
    st.info(
        "👆 Paste OCR text and the correct reference text above, then click "
        "**Compare Text** to see the analysis."
    )
