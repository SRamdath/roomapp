import streamlit as st
import spacy
import re
import dateparser
from dateparser.search import search_dates
from datetime import datetime
import spacy.cli
import calendar
# --- load SpaCy model ---
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# --- definitions ---
TASK_CATEGORIES = {
    'electrical': ['light', 'bulb', 'outlet', 'socket', 'switch'],
    'plumbing':  ['leak', 'pipe', 'toilet', 'sink', 'faucet'],
    'hvac':      ['ac', 'air conditioner', 'vent', 'cooling', 'heater'],
    'carpentry': ['door', 'window', 'handle', 'frame'],
    'general':   ['broken', 'fix', 'repair']
}

PRIORITY_KEYWORDS = {
    'high':   ['high priority', 'urgent', 'asap', 'immediately', 'emergency', 'critical'],
    'medium': ['medium priority', 'normal priority', 'soon', 'quick', 'needs attention'],
    'low':    ['low priority', 'whenever', 'no rush', 'sometime', 'can wait']
}

# --- extraction helpers ---
def extract_location(text):
    bldg = re.search(r'\b(?:building|bldg\.?)\s*[A-Z]\b', text, re.IGNORECASE)
    room = re.search(r'\b(room\s*\d+|\d{3})\b', text, re.IGNORECASE)
    floor = re.search(r'\b\d+(?:st|nd|rd|th)?\s+floor\b', text, re.IGNORECASE)
    parts = []
    for m in (bldg, room, floor):
        if m:
            parts.append(m.group(0))
    return " | ".join(parts) if parts else None

def extract_task_type(text):
    lowered = text.lower()
    for cat in ['hvac','electrical','plumbing','carpentry','general']:
        for kw in TASK_CATEGORIES[cat]:
            if re.search(rf'\b{re.escape(kw)}\b', lowered):
                return cat.capitalize()
    return "General"

def extract_asset(text, task_type):
    lowered = text.lower()
    # first look in the task_type’s own keywords
    for kw in TASK_CATEGORIES.get(task_type.lower(), []):
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return kw
    # then any category keyword
    for kws in TASK_CATEGORIES.values():
        for kw in kws:
            if re.search(rf'\b{re.escape(kw)}\b', lowered):
                return kw
    # fallback: first noun found
    doc = nlp(text)
    for tok in doc:
        if tok.pos_ == 'NOUN':
            return tok.text
    return None

def extract_priority(text):
    lowered = text.lower()
    # 1) explicit low
    for kw in PRIORITY_KEYWORDS['low']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "Low"
    # 2) explicit high
    for kw in PRIORITY_KEYWORDS['high']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "High"
    # 3) explicit medium
    for kw in PRIORITY_KEYWORDS['medium']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "Medium"
    # default
    return "Medium"

def extract_date(text):
    # 1) explicit “4th of July” style
    month_names = [m for m in dateparser.parser.Parser().locale.month_names.values() if m]
    explicit = re.search(
        rf'\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({"|".join(month_names)})\b',
        text, re.IGNORECASE
    )
    if explicit:
        p = dateparser.parse(explicit.group(0), settings={'RELATIVE_BASE': datetime.now()})
        if p:
            return str(p.date())

    # 2) SpaCy DATE ents (skip “other day”)
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "DATE" and not re.search(r'\bother day\b', ent.text.lower()):
            p = dateparser.parse(ent.text, settings={'RELATIVE_BASE': datetime.now()})
            if p:
                return str(p.date())

    # 3) fuzzy search_dates (again skip very vague)
    results = search_dates(text, settings={'RELATIVE_BASE': datetime.now()})
    if results:
        for match, dt in results:
            if not re.search(r'\bother day\b', match.lower()):
                return str(dt.date())

    return None

def parse_form(text):
    ttype = extract_task_type(text)
    return {
        'task_type': ttype,
        'location':  extract_location(text),
        'asset':     extract_asset(text, ttype),
        'priority':  extract_priority(text),
        'date':      extract_date(text)
    }

# --- Streamlit UI ---
st.set_page_config(page_title="🛠️ Maintenance Task Parser", layout="wide")
st.title("🛠️ Maintenance Task Parser")
st.markdown("Enter one or more maintenance descriptions, one per line:")

user_input = st.text_area("Task Descriptions", height=300)

if st.button("Parse"):
    if not user_input.strip():
        st.warning("Please enter at least one sentence.")
    else:
        st.subheader("Parsed Output:")
        lines = [l.strip() for l in user_input.splitlines() if l.strip()]
        for i, sentence in enumerate(lines, 1):
            parsed = parse_form(sentence)
            st.markdown(f"**Example {i}:** `{sentence}`")
            st.json(parsed)
