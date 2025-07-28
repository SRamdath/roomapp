import streamlit as st
import spacy
import re
import calendar
import dateparser
from dateparser.search import search_dates
from datetime import datetime, timedelta, date
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
    'carpentry':  ['door','window','handle','frame','handrail','ladder'],
    'general':    ['broken','fix','repair','generator']
}

# generic words to drop if something more specific appears
GENERIC_ASSETS = {
    'broken','fix','repair','leak',
    'thing','unit','component','device','fixture',
    'system','apparatus','equipment','object','item',
    'hardware','part'
}

PRIORITY_KEYWORDS = {
    'high':   ['high priority','urgent','asap','immediately','emergency','critical','immediate attention','needs immediate attention'],
    'medium': ['medium priority','normal priority','soon','quick','needs attention'],
    'low':    ['low priority','whenever','no rush','sometime','can wait','minor','not a big deal']
}


### HOLIDAY HELPERS ###

def nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    offset = (weekday - first.weekday() + 7) % 7
    return first + timedelta(days=offset + 7*(n-1))

def last_weekday(year, month, weekday):
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)

def get_holiday_date(name, year):
    nm = name.lower().replace("’","'").replace(".", "").strip()
    nm = re.sub(r"'s$", "", nm)
    if nm == "thanksgiving":
        return nth_weekday(year, 11, 3, 4)
    if nm == "christmas":
        return date(year, 12, 25)
    if nm in ("new year day","new year"):
        return date(year, 1, 1)
    if nm in ("valentine day","valentines day"):
        return date(year, 2, 14)
    if nm == "labor day":
        return nth_weekday(year, 9, 0, 1)
    if nm == "memorial day":
        return last_weekday(year, 5, 0)
    if nm in ("president day","presidents day"):
        return nth_weekday(year, 2, 0, 3)
    if nm == "martin luther king jr day":
        return nth_weekday(year, 1, 0, 3)
    if nm == "columbus day":
        return nth_weekday(year, 10, 0, 2)
    if nm == "veterans day":
        return date(year, 11, 11)
    return None


### FUNCTIONS ###

def extract_location(text):
    lowered   = text.lower()
    bldg      = re.search(r'\b(?:building|bldg\.?)\s*[A-Z]\b', text, re.IGNORECASE)
    room      = re.search(r'\b(room\s*\d+|\d{3})\b',             text, re.IGNORECASE)
    floor     = re.search(r'\b\d+(?:st|nd|rd|th)?\s+floor\b',    text, re.IGNORECASE)
    street    = re.search(
        r'\bon\s+([A-Z][\w]*(?:\s+[A-Z][\w]*)*\s+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?))\b',
        text
    )
    hall      = re.search(r'\bresidence hall\b',                 text, re.IGNORECASE)
    corridor  = re.search(r'\bcorridor\s*(\d+)\b',               lowered)
    wing      = re.search(r'\b(north|south|east|west)\s+wing\b', lowered)
    mezz      = re.search(r'\bmezzanine\b',                      lowered)

    parts = []
    if bldg:     parts.append(bldg.group(0))
    if room:     parts.append(room.group(0))
    if floor:    parts.append(floor.group(0))
    if street:   parts.append(street.group(1))
    if hall:     parts.append('residence hall')
    if corridor: parts.append(f"corridor {corridor.group(1)}")
    if wing:     parts.append(f"{wing.group(1)} wing")
    if mezz:     parts.append('mezzanine')
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
    hits = [
        (m.start(), kw)
        for kw in TASK_CATEGORIES.get(task_type.lower(), [])
        for m in re.finditer(rf'\b{re.escape(kw)}\b', lowered)
    ]
    if len(hits) > 1:
        specific = [h for h in hits if h[1] not in GENERIC_ASSETS]
        if specific:
            hits = specific
    if hits:
        return min(hits, key=lambda x: x[0])[1]

    all_hits = [
        (m.start(), kw)
        for kws in TASK_CATEGORIES.values()
        for kw in kws
        for m in re.finditer(rf'\b{re.escape(kw)}\b', lowered)
    ]
    if len(all_hits) > 1:
        specific = [h for h in all_hits if h[1] not in GENERIC_ASSETS]
        if specific:
            all_hits = specific
    if all_hits:
        return min(all_hits, key=lambda x: x[0])[1]

    doc = nlp(text)
    for tok in doc:
        if tok.pos_ == 'NOUN' and tok.text.lower() not in GENERIC_ASSETS:
            return tok.text
    for tok in doc:
        if tok.pos_ == 'NOUN':
            return tok.text
    return None


def extract_priority(text):
    lowered = text.lower()
    if re.search(r'\b(minor|not a big deal)\b', lowered):
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
    now     = datetime.now()

    # 1) end of this month
    if re.search(r'\bend of (?:this|current) month\b', lowered):
        y, m = now.year, now.month
        last_day = calendar.monthrange(y, m)[1]
        return str(date(y, m, last_day))

    # 2) holiday
    hol = re.search(
        r'\b(next\s+)?(thanksgiving|christmas|new year(?:\'s)? day|new year|'
        r'valentine(?:’s|s) day|labor day|memorial day|president(?:s)? day|'
        r'martin luther king jr\.? day|columbus day|veterans day)\b',
        lowered
    )
    if hol:
        qual = hol.group(1)
        name = hol.group(2)
        yr   = now.year + (1 if qual else 0)
        hd   = get_holiday_date(name, yr)
        if not qual and hd and hd < now.date():
            hd = get_holiday_date(name, now.year+1)
        if hd:
            return str(hd)

    # 3) only if date‑like
    if not re.search(
        r'\b(?:by\s+)?(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|'
        r'thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|'
        r'january|february|month|march|april|may|june|july|august|'
        r'september|october|november|december|next|last|'
        r'tomorrow|yesterday|\d+(?:st|nd|rd|th))\b',
        lowered
    ):
        return None

    # 4) “15th of July”
    mn = [calendar.month_name[i] for i in range(1,13)]
    exp = re.search(
        rf'\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({"|".join(mn)})\b',
        text, re.IGNORECASE
    )
    if exp:
        p = dateparser.parse(exp.group(0), settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if p:
            return str(p.date())

    # 5) “by Wednesday”
    by = re.search(r'\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', lowered)
    if by:
        base = dateparser.parse(by.group(1), settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if base:
            return str(base.date())

    # 6) “after next Wednesday” or “next Wednesday”
    aft = re.search(r'\bafter\s+next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', lowered)
    if aft:
        wd   = aft.group(1)
        base = dateparser.parse(wd, settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if base:
            # interpret “after next Wed” as the Wednesday after upcoming one
            return str((base + timedelta(days=7)).date())

    # 7) “before next/last Friday”
    bf = re.search(
        r'\bbefore\s+(next|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        lowered
    )
    if bf:
        qual, wd = bf.group(1), bf.group(2)
        base     = dateparser.parse(wd, settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if base:
            delta  = timedelta(days=7)
            target = base + delta if qual == 'next' else base - delta
            return str(target.date())

    # 8) SpaCy DATE ents (prefer future)
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == 'DATE' and 'other day' not in ent.text.lower():
            p = dateparser.parse(ent.text, settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
            if p:
                return str(p.date())

    # 9) fuzzy fallback
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
