import streamlit as st
import spacy
import re
import calendar
import dateparser
from dateparser.search import search_dates
from datetime import datetime, timedelta
import spacy.cli

# --- load SpaCy model ---
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


# --- keyword lists ---
TASK_CATEGORIES = {
    'electrical': ['electrical','light','lights','bulb','bulbs','outlet','socket','switch','wire','wiring','cable'],
    'plumbing':   ['leak','pipe','pipes','toilet','sink','sinks','faucet'],
    'hvac':       ['ac','air conditioner','vent','vents','cooling','heater','duct','ductwork'],
    'carpentry':  ['door','window','handle','frame','handrail'],
    'general':    ['broken','fix','repair']
}

# too‑generic fallbacks
GENERIC_ASSETS = {
    'broken','fix','repair','leak',
    'thing','unit','component','device','fixture',
    'system','apparatus','equipment','object','item',
    'hardware','part'
}

PRIORITY_KEYWORDS = {
    'high':   ['high priority','urgent','asap','immediately','emergency','critical','immediate attention'],
    'medium': ['medium priority','normal priority','soon','quick','needs attention'],
    'low':    ['low priority','whenever','no rush','sometime','can wait']
}


### FUNCTIONS ###


def extract_location(text):
    lowered   = text.lower()
    bldg      = re.search(r'\b(?:building|bldg\.?)\s*[A-Z]\b', text, re.IGNORECASE)
    room      = re.search(r'\b(room\s*\d+|\d{3})\b',        text, re.IGNORECASE)
    floor     = re.search(r'\b\d+(?:st|nd|rd|th)?\s+floor\b', text, re.IGNORECASE)
    street    = re.search(
        r'\bon\s+([A-Z][\w]*(?:\s+[A-Z][\w]*)*\s+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?))\b',
        text
    )
    hall      = re.search(r'\bresidence hall\b', text, re.IGNORECASE)
    corridor  = re.search(r'\bcorridor\s*(\d+)\b', lowered)

    parts = []
    if bldg:      parts.append(bldg.group(0))
    if room:      parts.append(room.group(0))
    if floor:     parts.append(floor.group(0))
    if street:    parts.append(street.group(1))
    if hall:      parts.append('residence hall')
    if corridor:  parts.append(f"corridor {corridor.group(1)}")

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
    hits    = []
    # 1) in‑category keywords (whole‑word)
    for kw in TASK_CATEGORIES.get(task_type.lower(), []):
        for m in re.finditer(rf'\b{re.escape(kw)}\b', lowered):
            hits.append((m.start(), kw))
    # drop generic if others present
    if len(hits) > 1:
        specific = [h for h in hits if h[1] not in GENERIC_ASSETS]
        if specific:
            hits = specific
    if hits:
        return min(hits, key=lambda x: x[0])[1]

    # 2) any category keyword
    all_hits = []
    for kws in TASK_CATEGORIES.values():
        for kw in kws:
            for m in re.finditer(rf'\b{re.escape(kw)}\b', lowered):
                all_hits.append((m.start(), kw))
    if len(all_hits) > 1:
        specific = [h for h in all_hits if h[1] not in GENERIC_ASSETS]
        if specific:
            all_hits = specific
    if all_hits:
        return min(all_hits, key=lambda x: x[0])[1]

    # 3) fallback: first non‑generic noun
    doc = nlp(text)
    for tok in doc:
        if tok.pos_ == 'NOUN' and tok.text.lower() not in GENERIC_ASSETS:
            return tok.text
    # 4) any noun
    for tok in doc:
        if tok.pos_ == 'NOUN':
            return tok.text
    return None


def extract_priority(text):
    lowered = text.lower()
    if re.search(r'\bminor\b', lowered) or re.search(r'\bnot a big deal\b', lowered):
        return "Low"
    if re.search(r'\bnot\s+(?:urgent|high priority|critical)\b', lowered):
        return "Low"
    for kw in PRIORITY_KEYWORDS['low']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "Low"
    for kw in PRIORITY_KEYWORDS['high']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "High"
    for kw in PRIORITY_KEYWORDS['medium']:
        if re.search(rf'\b{re.escape(kw)}\b', lowered):
            return "Medium"
    return "Medium"


def extract_date(text):
    lowered = text.lower()
    if not re.search(
        r'\b(?:by\s+)?(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|'
        r'fri(?:day)?|sat(?:urday)?|sun(?:day)?|'
        r'january|february|march|april|may|june|july|august|september|october|november|december|'
        r'next|last|tomorrow|yesterday|\d+(?:st|nd|rd|th))\b',
        lowered
    ):
        return None

    now = datetime.now()

    # explicit “15th of July”
    month_names = [calendar.month_name[i] for i in range(1,13)]
    exp_match   = re.search(
        rf'\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({"|".join(month_names)})\b',
        text, re.IGNORECASE
    )
    if exp_match:
        p = dateparser.parse(exp_match.group(0), settings={'RELATIVE_BASE': now})
        if p:
            return str(p.date())

    # by <weekday> → upcoming
    by_match = re.search(r'\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', lowered)
    if by_match:
        wd   = by_match.group(1)
        base = dateparser.parse(wd, settings={'RELATIVE_BASE': now,'PREFER_DATES_FROM':'future'})
        if base:
            return str(base.date())

    # before <next|last> <weekday>
    before_match = re.search(
        r'\bbefore\s+(next|last)\s+'
        r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        lowered
    )
    if before_match:
        qual = before_match.group(1)
        wd   = before_match.group(2)
        base = dateparser.parse(wd, settings={'RELATIVE_BASE': now,'PREFER_DATES_FROM':'future'})
        if base:
            if qual == 'next':
                target = base + timedelta(days=7)
            else:  # 'last'
                target = base - timedelta(days=7)
            return str(target.date())

    # SpaCy DATE ents
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "DATE" and 'other day' not in ent.text.lower():
            p = dateparser.parse(ent.text, settings={'RELATIVE_BASE': now})
            if p:
                return str(p.date())

    # fuzzy fallback
    results = search_dates(text, settings={'RELATIVE_BASE': now})
    if results:
        for match, dt in results:
            if 'other day' not in match.lower():
                return str(dt.date())

    return None


def parse_form(text):
    t = extract_task_type(text)
    return {
        'task_type': t,
        'location':  extract_location(text),
        'asset':     extract_asset(text, t),
        'priority':  extract_priority(text),
        'date':      extract_date(text)
    }


### MAIN ###

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
            result = parse_form(sentence)
            st.markdown(f"**Example {i}:** `{sentence}`")
            st.json(result)
