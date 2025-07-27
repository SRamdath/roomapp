import streamlit as st
import spacy
import re
import dateparser
from dateparser.search import search_dates
import datetime

import spacy.cli
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

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
    
    # Match "room 205" or standalone numbers like "in 205" or "205" if no confusion
    room = re.search(r'\b(room\s*\d+|\b\d{3}\b)', text, re.IGNORECASE)

    parts = []
    if building:
        parts.append(building.group(0))
    if room:
        # Remove "room" prefix if needed for uniformity
        room_number = re.search(r'\d{3}', room.group(0))
        if room_number:
            parts.append(f"Room {room_number.group(0)}")
    return " ".join(parts) if parts else None

def extract_asset(text, task_type):
    lowered = text.lower()
    
    # Avoid numbers-only being picked up as asset
    if lowered.strip().isdigit():
        return None

    matched_assets = []
    category_keywords = TASK_CATEGORIES.get(task_type.lower(), [])
    for kw in category_keywords:
        if kw in lowered:
            matched_assets.append(kw)
    if matched_assets:
        return matched_assets[0]

    for keywords in TASK_CATEGORIES.values():
        for kw in keywords:
            if kw in lowered:
                return kw

    doc = nlp(lowered)
    for token in doc:
        if token.pos_ == 'NOUN' and not token.text.isdigit():
            return token.text
    return None

def extract_task_type(text):
    lowered = text.lower()
    priority_order = ['hvac', 'electrical', 'plumbing', 'carpentry', 'general']
    for category in priority_order:
        if any(kw in lowered for kw in TASK_CATEGORIES[category]):
            return category.capitalize()
    return "General"

def extract_priority(text):
    lowered = text.lower()
    for level, keywords in PRIORITY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return level.capitalize()
    return "Medium"

def extract_date(text):
    text = text.strip()
    today = datetime.date.today()
    
    # First try: find relative clues
    result = search_dates(text, settings={'RELATIVE_BASE': datetime.datetime.now()})
    if result:
        for matched_text, parsed_dt in result:
            if matched_text.lower() in ['wednesday', 'monday', 'tuesday', 'thursday', 'friday', 'saturday', 'sunday']:
                # Default to previous weekday if ambiguous
                weekday_num = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].index(matched_text.lower())
                days_ago = (today.weekday() - weekday_num) % 7 or 7
                resolved_date = today - datetime.timedelta(days=days_ago)
                return str(resolved_date)
            else:
                return str(parsed_dt.date())
    
    # Fallback: spaCy NER (less reliable for weekdays)
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
