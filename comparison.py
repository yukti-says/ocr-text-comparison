"""
comparison.py
-------------
Reusable, pure-Python comparison engine for the OCR Text Comparison tool.

This module contains no Streamlit-specific code so it can be unit-tested
or reused in other contexts (CLI, batch jobs, notebooks, etc).

Core pipeline:
    1. tokenize_text()      -> turns raw text into a list of token dicts
    2. compare_tokens()     -> aligns two token lists into DiffRecords
    3. compute_stats()      -> summarizes DiffRecords into headline numbers
    4. build_highlight_html() -> renders side-by-side colored HTML views
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

# Anything that is not a "word" character or whitespace is considered punctuation.
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Diff type labels used throughout the app.
CORRECT = "Correct"
REPLACEMENT = "Replacement"
MISSING = "Missing"
EXTRA = "Extra"
SPLIT_WORD = "Split Word"
MERGED_WORD = "Merged Word"

# Colors (also mirrored in app.py CSS) - kept here so exports can reuse them.
DIFF_COLORS = {
    CORRECT: "#2ecc71",      # green
    REPLACEMENT: "#f39c12",  # orange
    MISSING: "#e74c3c",      # red
    EXTRA: "#3498db",        # blue
    SPLIT_WORD: "#9b59b6",   # purple
    MERGED_WORD: "#9b59b6",  # purple
}

DIFF_ICONS = {
    CORRECT: "✅",
    REPLACEMENT: "🟠",
    MISSING: "🔴",
    EXTRA: "🔵",
    SPLIT_WORD: "🟣",
    MERGED_WORD: "🟣",
}


# ----------------------------------------------------------------------------
# Tokenization
# ----------------------------------------------------------------------------

def normalize_token(word: str, ignore_case: bool, ignore_punct: bool) -> str:
    """Normalize a single word token for comparison purposes."""
    w = word
    if ignore_punct:
        w = _PUNCT_RE.sub("", w)
    if ignore_case:
        w = w.lower()
    return w


def tokenize_text(
    text: str,
    ignore_case: bool = True,
    ignore_punct: bool = True,
    ignore_spaces: bool = True,
    trim: bool = True,
) -> List[Dict]:
    """
    Convert raw text into an ordered list of token dicts:
        {"orig": <original word>, "norm": <normalized word>,
         "line": <1-based line number>, "idx": <0-based global index>}

    Line breaks are only used to remember *where* a word came from
    (for the "Line Number" column); they never block matching across lines,
    per the requirement to "ignore line breaks" during comparison.
    """
    if trim:
        text = text.strip()

    tokens: List[Dict] = []
    idx = 0
    lines = text.split("\n") if text else [""]

    for line_no, line in enumerate(lines, start=1):
        if ignore_spaces:
            words = line.split()
        else:
            # Still need *some* splitting; fall back to whitespace split
            # but preserve empty-string-free behaviour.
            words = [w for w in line.split(" ") if w != ""]

        for w in words:
            norm = normalize_token(w, ignore_case, ignore_punct)
            if norm == "":
                # Word was pure punctuation and punctuation is ignored -> skip
                continue
            tokens.append({"orig": w, "norm": norm, "line": line_no, "idx": idx})
            idx += 1

    return tokens


# ----------------------------------------------------------------------------
# Diff record helper
# ----------------------------------------------------------------------------

def _make_record(
    diff_type: str,
    ocr_group: List[Dict],
    correct_group: List[Dict],
    similarity: float,
) -> Dict:
    """Build a single diff record from groups of source tokens on each side."""
    ocr_word = " ".join(t["orig"] for t in ocr_group) if ocr_group else "--"
    correct_word = " ".join(t["orig"] for t in correct_group) if correct_group else "--"

    if ocr_group:
        line = ocr_group[0]["line"]
    elif correct_group:
        line = correct_group[0]["line"]
    else:
        line = None

    return {
        "line": line,
        "ocr_word": ocr_word,
        "correct_word": correct_word,
        "diff_type": diff_type,
        "similarity": round(similarity, 1),
        "ocr_idxs": [t["idx"] for t in ocr_group],
        "correct_idxs": [t["idx"] for t in correct_group],
    }


# ----------------------------------------------------------------------------
# Smart alignment for "replace" blocks (handles split / merged OCR words)
# ----------------------------------------------------------------------------

def _smart_align_replace(
    ocr_sub: List[Dict],
    correct_sub: List[Dict],
    threshold: int,
    max_merge_window: int = 4,
) -> List[Dict]:
    """
    Align a mismatched block of OCR tokens against a mismatched block of
    Correct tokens. Handles three cases in priority order:
        1. 1-to-1 fuzzy match (typo / misread word)
        2. many-OCR-tokens -> 1-correct-token (OCR split a word apart)
        3. 1-OCR-token -> many-correct-tokens (OCR merged words together)
    Anything left over is reported as independent Missing / Extra.
    """
    records: List[Dict] = []
    i, j = 0, 0
    n, m = len(ocr_sub), len(correct_sub)

    while i < n and j < m:
        o = ocr_sub[i]
        c = correct_sub[j]
        ratio = fuzz.ratio(o["norm"], c["norm"])

        if ratio >= threshold:
            diff_type = CORRECT if ratio >= 99.9 else REPLACEMENT
            records.append(_make_record(diff_type, [o], [c], ratio))
            i += 1
            j += 1
            continue

        # --- Case 2: OCR split one word into several tokens ---------------
        best_split: Optional[Tuple[int, float]] = None
        for w in range(2, min(max_merge_window, n - i) + 1):
            merged = "".join(t["norm"] for t in ocr_sub[i : i + w])
            r = fuzz.ratio(merged, c["norm"])
            if r >= threshold and (best_split is None or r > best_split[1]):
                best_split = (w, r)

        if best_split is not None:
            w, r = best_split
            records.append(_make_record(SPLIT_WORD, ocr_sub[i : i + w], [c], r))
            i += w
            j += 1
            continue

        # --- Case 3: OCR merged several correct words into one token ------
        best_merge: Optional[Tuple[int, float]] = None
        for w in range(2, min(max_merge_window, m - j) + 1):
            merged = "".join(t["norm"] for t in correct_sub[j : j + w])
            r = fuzz.ratio(o["norm"], merged)
            if r >= threshold and (best_merge is None or r > best_merge[1]):
                best_merge = (w, r)

        if best_merge is not None:
            w, r = best_merge
            records.append(_make_record(MERGED_WORD, [o], correct_sub[j : j + w], r))
            i += 1
            j += w
            continue

        # --- No good alignment: report both sides independently -----------
        records.append(_make_record(EXTRA, [o], [], 0))
        records.append(_make_record(MISSING, [], [c], 0))
        i += 1
        j += 1

    # Leftover OCR tokens with no correct counterpart -> Extra
    while i < n:
        records.append(_make_record(EXTRA, [ocr_sub[i]], [], 0))
        i += 1

    # Leftover Correct tokens with no OCR counterpart -> Missing
    while j < m:
        records.append(_make_record(MISSING, [], [correct_sub[j]], 0))
        j += 1

    return records


# ----------------------------------------------------------------------------
# Main comparison entry point
# ----------------------------------------------------------------------------

def compare_tokens(
    ocr_tokens: List[Dict],
    correct_tokens: List[Dict],
    fuzzy_threshold: int = 80,
) -> List[Dict]:
    """
    Align two token lists using difflib's SequenceMatcher for the coarse
    alignment, then refine "replace" blocks with fuzzy / split / merge logic.
    Returns an ordered list of diff records.
    """
    ocr_norms = [t["norm"] for t in ocr_tokens]
    correct_norms = [t["norm"] for t in correct_tokens]

    sm = SequenceMatcher(None, ocr_norms, correct_norms, autojunk=False)
    records: List[Dict] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                o = ocr_tokens[i1 + k]
                c = correct_tokens[j1 + k]
                records.append(_make_record(CORRECT, [o], [c], 100.0))

        elif tag == "replace":
            records.extend(
                _smart_align_replace(
                    ocr_tokens[i1:i2], correct_tokens[j1:j2], fuzzy_threshold
                )
            )

        elif tag == "delete":
            # Present in OCR only
            for k in range(i1, i2):
                records.append(_make_record(EXTRA, [ocr_tokens[k]], [], 0))

        elif tag == "insert":
            # Present in Correct only
            for k in range(j1, j2):
                records.append(_make_record(MISSING, [], [correct_tokens[k]], 0))

    return records


def overall_similarity(ocr_tokens: List[Dict], correct_tokens: List[Dict]) -> float:
    """Overall SequenceMatcher similarity ratio (0-100) across normalized tokens."""
    ocr_norms = [t["norm"] for t in ocr_tokens]
    correct_norms = [t["norm"] for t in correct_tokens]
    ratio = SequenceMatcher(None, ocr_norms, correct_norms, autojunk=False).ratio()
    return round(ratio * 100, 2)


# ----------------------------------------------------------------------------
# Stats
# ----------------------------------------------------------------------------

def compute_stats(
    records: List[Dict], ocr_tokens: List[Dict], correct_tokens: List[Dict]
) -> Dict:
    """Compute headline statistics from the diff records."""
    matched = sum(1 for r in records if r["diff_type"] == CORRECT)
    incorrect = sum(
        1 for r in records if r["diff_type"] in (REPLACEMENT, SPLIT_WORD, MERGED_WORD)
    )
    missing = sum(1 for r in records if r["diff_type"] == MISSING)
    extra = sum(1 for r in records if r["diff_type"] == EXTRA)
    replacement_count = incorrect  # every "incorrect" record is a replacement of some kind

    total_correct_words = len(correct_tokens)
    accuracy = (matched / total_correct_words * 100) if total_correct_words else 100.0

    return {
        "Total OCR Words": len(ocr_tokens),
        "Correct Words": len(correct_tokens),
        "Matched Words": matched,
        "Incorrect Words": incorrect,
        "Missing Words": missing,
        "Extra Words": extra,
        "Replacement Count": replacement_count,
        "Accuracy %": round(accuracy, 2),
    }


# ----------------------------------------------------------------------------
# Highlighted side-by-side HTML view
# ----------------------------------------------------------------------------

def _status_maps(records: List[Dict]) -> Tuple[Dict[int, str], Dict[int, str]]:
    """Build idx -> diff_type maps for the OCR side and the Correct side."""
    ocr_status: Dict[int, str] = {}
    correct_status: Dict[int, str] = {}
    for r in records:
        for idx in r["ocr_idxs"]:
            ocr_status[idx] = r["diff_type"]
        for idx in r["correct_idxs"]:
            correct_status[idx] = r["diff_type"]
    return ocr_status, correct_status


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_highlight_html(
    tokens: List[Dict], status_map: Dict[int, str], side: str
) -> str:
    """
    Render a token list back into HTML, wrapping every non-"Correct" token
    in a colored <span>. `side` is "ocr" or "correct", used only to decide
    default coloring (all Correct tokens render as plain text).
    """
    if not tokens:
        return "<em>(empty)</em>"

    lines: Dict[int, List[str]] = {}
    for t in tokens:
        status = status_map.get(t["idx"], CORRECT)
        word = _escape(t["orig"])
        if status != CORRECT:
            color = DIFF_COLORS.get(status, "#999999")
            span = (
                f'<span title="{status}" '
                f'style="background:{color}22;color:{color};'
                f'border-bottom:2px solid {color};font-weight:600;'
                f'padding:1px 3px;border-radius:4px;">{word}</span>'
            )
        else:
            span = word
        lines.setdefault(t["line"], []).append(span)

    rendered_lines = [" ".join(words) for _, words in sorted(lines.items())]
    return "<br>".join(rendered_lines)


def build_side_by_side(
    ocr_tokens: List[Dict], correct_tokens: List[Dict], records: List[Dict]
) -> Tuple[str, str]:
    """Convenience wrapper returning (ocr_html, correct_html)."""
    ocr_status, correct_status = _status_maps(records)
    ocr_html = build_highlight_html(ocr_tokens, ocr_status, "ocr")
    correct_html = build_highlight_html(correct_tokens, correct_status, "correct")
    return ocr_html, correct_html
