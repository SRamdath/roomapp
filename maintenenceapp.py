import streamlit as st
import spacy
import re
import calendar
import dateparser
from dateparser.search import search_dates
from datetime import datetime, timedelta
import spacy.cli

# --- load SpaCy ---
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# --- keyword definitions ---
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

# --- helpers ---
WEEKDAYS = {
    'monday':    0,
    'tuesday':   1,
    'wednesday': 2,
    'thursday':  3,
    'friday':    4,
    'saturday':  5,
    'sunday':    6
}

def extract_location(text):
    bldg  = re.search(r'\b(?:building|bldg\.?)\s*[A-Z]\b', text, re.IGNORECASE)
    room  = re.search(r'\b(room\s*\d+|\d{3})\b',        text, re.IGNORECASE)
    floor = re.search(r'\b\d+(?:st|nd|rd|th)?\s+floor\b', text, re.IGNORECASE)
    parts = [m.group(0) for m in (bldg, room, floor) if m]
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
    # in‑category
    for kw in TASK_CATEGORIES.get(task_type.lower(), []):
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return kw
    # any category
    for kws in TASK_CATEGORIES.values():
        for kw in kws:
            if re.search(rf'\b{re.escape(kw)}\b', lowered):
                return kw
    # fallback: first noun
    doc = nlp(text)
    for tok in doc:
        if tok.pos_ == 'NOUN':
            return tok.text
    return None

def extract_priority(text):
    lowered = text.lower()
    # “not urgent” → Low
    if re.search(r'\bnot\s+(?:urgent|high priority|critical)\b', lowered):
        return "Low"
    # explicit Low → Low
    for kw in PRIORITY_KEYWORDS['low']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "Low"
    # explicit High → High
    for kw in PRIORITY_KEYWORDS['high']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "High"
    # explicit Medium → Medium
    for kw in PRIORITY_KEYWORDS['medium']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "Medium"
    # default
    return "Medium"

def extract_date(text):
    lowered = text.lower()
    # only attempt if some date-like token is present
    if not re.search(
        r'\b(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|'
        r'sat(?:urday)?|sun(?:day)?|'
        r'january|february|march|april|may|june|july|august|september|october|november|december|'
        r'next|last|tomorrow|yesterday|\d+(?:st|nd|rd|th))\b',
        lowered
    ):
        return None

    now = datetime.now()

    # 1) explicit “15th of July”
    month_names = [calendar.month_name[i] for i in range(1,13)]
    explicit = re.search(
        rf'\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({"|".join(month_names)})\b',
        text, re.IGNORECASE
    )
    if explicit:
        p = dateparser.parse(explicit.group(0), settings={'RELATIVE_BASE': now})
        if p:
            return str(p.date())

    # 2) “before next Friday” logic
    before_m = re.search(
        r'\bbefore\s+(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        lowered
    )
    if before_m:
        is_next = bool(before_m.group(1))
        weekday = before_m.group(2)
        # find this week's weekday (future)
        base = dateparser.parse(
            weekday,
            settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM': 'future'}
        )
        if base:
            if is_next:
                target = base + timedelta(days=7)
            else:
                target = base - timedelta(days=7)
            return str(target.date())

    # 3) SpaCy DATE ents (skip “other day”)
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "DATE" and 'other day' not in ent.text.lower():
            p = dateparser.parse(ent.text, settings={'RELATIVE_BASE': now})
            if p:
                return str(p.date())

    # 4) fuzzy fallback
    results = search_dates(text, settings={'RELATIVE_BASE': now})
    if results:
        for match, dt in results:
            if 'other day' not in match.lower():
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
        for i, sentence in enumerate([l.strip() for l in user_input.splitlines() if l.strip()], 1):
            parsed = parse_form(sentence)
            st.markdown(f"**Example {i}:** `{sentence}`")
            st.json(parsed)
            parsed = parse_form(sentence)
            st.markdown(f"**Example {i}:** `{sentence}`")
            st.json(parsed)
