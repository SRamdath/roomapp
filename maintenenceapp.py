import streamlit as st
import spacy
import re
import dateparser
import datetime
from dateparser.search import search_dates

import spacy.cli
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# Task and priority definitions
TASK_CATEGORIES = {
    'electrical': ['light', 'bulb', 'outlet', 'socket', 'switch'],
    'plumbing': ['leak', 'pipe', 'toilet', 'sink'],
    'hvac': ['ac', 'air conditioner', 'vent', 'cooling', 'heater'],
    'carpentry': ['door', 'window', 'handle', 'frame'],
    'general': ['broken', 'fix', 'repair']
}

PRIORITY_KEYWORDS = {
    'high': ['urgent', 'asap', 'immediately', 'emergency'],
    'medium': ['soon', 'quick', 'needs attention'],
    'low': ['whenever', 'not urgent', 'no rush']
}

# Extraction functions
def extract_location(text):
    building = re.search(r'(building\s+[A-Z])', text, re.IGNORECASE)
    room = re.search(r'(room\s*\d+|\b\d{3,4}\b)', text, re.IGNORECASE)
    parts = []
    if building:
        parts.append(building.group(0))
    if room:
        parts.append(room.group(0))
    return " ".join(parts) if parts else None

def extract_asset(text, task_type):
    lowered = text.lower()
    matched_assets = []
    category_keywords = TASK_CATEGORIES.get(task_type.lower(), [])
    for kw in category_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', lowered):
            matched_assets.append(kw)
    if matched_assets:
        return matched_assets[0]
    for keywords in TASK_CATEGORIES.values():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lowered):
                return kw
    doc = nlp(lowered)
    for token in doc:
        if token.pos_ == 'NOUN':
            return token.text
    return None

def extract_task_type(text):
    lowered = text.lower()
    for category, keywords in TASK_CATEGORIES.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lowered):
                return category.capitalize()
    return "General"

def extract_priority(text):
    lowered = text.lower()
    if 'not urgent' in lowered or 'no rush' in lowered:
        return 'Low'
    for level, keywords in PRIORITY_KEYWORDS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lowered):
                return level.capitalize()
    return "Medium"

def extract_date(text):
    today = datetime.date.today()
    if "this month" in text.lower():
        day_match = re.search(r'\b(\d{1,2})(st|nd|rd|th)?\s+this month\b', text.lower())
        if day_match:
            day = int(day_match.group(1))
            return str(datetime.date(today.year, today.month, day))

    result = search_dates(text, settings={'RELATIVE_BASE': datetime.datetime.now()})
    if result:
        return str(result[0][1].date())

    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "DATE":
            parsed = dateparser.parse(ent.text)
            if parsed:
                return str(parsed.date())

    return None

def parse_form(text):
    task_type = extract_task_type(text)
    return {
        'task_type': task_type,
        'location': extract_location(text),
        'asset': extract_asset(text, task_type),
        'priority': extract_priority(text),
        'date': extract_date(text)
    }

# --- Streamlit Interface ---
st.title("🛠️ Maintenance Task Parser")

st.markdown("Enter one or more maintenance descriptions, one per line:")

user_input = st.text_area("Task Descriptions", height=250)

if st.button("Parse"):
    if not user_input.strip():
        st.warning("Please enter at least one sentence.")
    else:
        st.subheader("Parsed Output:")
        lines = [line.strip() for line in user_input.split('\n') if line.strip()]
        for i, sentence in enumerate(lines, 1):
            parsed = parse_form(sentence)
            st.markdown(f"**Example {i}:** `{sentence}`")
            st.json(parsed)
            parsed = parse_form(sentence)
            st.markdown(f"**Example {i}:** `{sentence}`")
            st.json(parsed)
