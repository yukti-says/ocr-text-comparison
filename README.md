# OCR Text Comparison & Error Detection Tool

A lightweight Streamlit web app for comparing **OCR-extracted text** against a
**correct reference text**, designed for fast, intelligent OCR quality
checking (not just a plain character diff).

---

## Features

- **Two-panel input** — paste OCR text on the left, correct text on the right.
- **Intelligent word-level comparison** using `difflib.SequenceMatcher` for
  alignment plus `RapidFuzz` for fuzzy word similarity.
- **Detects:**
  - Missing words (present in correct text only)
  - Extra words (present in OCR only)
  - Incorrect / replaced words (e.g. `Tahsil` → `Tehsil`)
  - Split words — OCR broke one word into pieces (e.g. `Mad hya Pradesh`)
  - Merged words — OCR joined two words together (e.g. `MadhyaPradesh`)
- **Overall similarity score** as a large metric card.
- **Full statistics panel**: total words, matched, incorrect, missing, extra,
  replacement count, and accuracy %.
- **Detailed difference table** (sortable/filterable pandas DataFrame) with
  color-coded rows.
- **Side-by-side highlighted view** showing both texts with inline color
  highlighting of every difference.
- **Difference Navigator**: search, and jump through differences with
  Previous / Next buttons and a live counter.
- **Configurable ignore options**: case, punctuation, extra spaces, and
  leading/trailing whitespace (all enabled by default).
- **Exports**: CSV, Excel (.xlsx), JSON, and a plain-text report.
- **Copy helpers**: one-click copy of the difference table (CSV) and the
  summary via the built-in copy icon on each code block.

---

## Project Structure

```
.
├── app.py            # Streamlit UI and application flow
├── comparison.py      # Reusable, pure-Python comparison engine (no Streamlit deps)
├── requirements.txt    # Python dependencies
└── README.md
```

`comparison.py` is fully independent of Streamlit, so the comparison engine
can be reused in scripts, notebooks, or tests.

---

## Installation

Requires Python 3.11+.

```bash
# (Optional) create a virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Running the App

```bash
streamlit run app.py
```

Then open the URL Streamlit prints (usually `http://localhost:8501`) in your
browser.

---

## How the Comparison Works

1. **Tokenization** — each text is split into words per line. Punctuation,
   case, and extra whitespace are normalized according to the sidebar
   options (line breaks never block matching, only track "Line Number").
2. **Coarse alignment** — `difflib.SequenceMatcher` aligns the two token
   sequences into `equal`, `replace`, `delete`, and `insert` blocks.
3. **Fine alignment (smart matching)** — inside every `replace` block:
   - If a single OCR word and a single correct word have a RapidFuzz
     similarity ≥ the threshold (default 80%), it's marked **Replacement**.
   - If several adjacent OCR words concatenated match one correct word,
     it's marked **Split Word** (OCR broke a word apart).
   - If one OCR word matches several concatenated correct words, it's
     marked **Merged Word** (OCR joined two words together).
   - Anything left unmatched is reported as independent **Missing** /
     **Extra** words.
4. **`delete` blocks** → words only in OCR → **Extra**.
   **`insert` blocks** → words only in the correct text → **Missing**.

You can tune the fuzzy threshold from the sidebar — lower it to catch more
loose matches as "Replacement", or raise it to be stricter about what counts
as a genuine typo versus an unrelated word pair.

---

## Color Coding

| Type              | Color  | Icon |
|-------------------|--------|------|
| Correct           | Green  | ✅   |
| Replacement       | Orange | 🟠   |
| Missing           | Red    | 🔴   |
| Extra             | Blue   | 🔵   |
| Split / Merged    | Purple | 🟣   |

---

## Notes

- Designed for typical OCR verification workloads of 100–300 words per
  document; comparisons complete instantly.
- All processing happens locally in your browser session — no text is sent
  anywhere besides your own machine running the Streamlit server.
