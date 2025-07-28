import streamlit as st
import spacy
import re
import calendar
import dateparser
from dateparser.search import search_dates
from datetime import datetime, timedelta, date
import spacy.cli


# load SpaCy model and download if missing
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


# define what kind of tasks we know about and the words that hint at them
TASK_CATEGORIES = {
    'electrical': ['electrical','light','lights','bulb','bulbs','fixture','fixtures','outlet','socket','switch','wire','wiring','cable'],
    'plumbing':   ['leak','pipe','pipes','toilet','sink','sinks','faucet'],
    'hvac':       ['ac','air conditioner','vent','vents','cooling','heater','duct','ductwork'],
    'carpentry':  ['door','window','handle','frame','handrail','ladder'],
    'general':    ['broken','fix','repair','generator']
}

# these are too vague if something more specific is around
GENERIC_ASSETS = {
    'broken','fix','repair','leak','fluorescent',
    'thing','unit','component','device','fixture',
    'system','apparatus','equipment','object','item',
    'hardware','part'
}

PRIORITY_KEYWORDS = {
    'high':   ['high priority','urgent','asap','immediately','emergency','critical','immediate attention','needs immediate attention'],
    'medium': ['medium priority','normal priority','soon','quick','needs attention'],
    'low':    ['low priority','whenever','no rush','sometime','can wait','minor','not a big deal']
}


# helpers for holiday dates, because why not make your deadlines festive
def nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    offset = (weekday - first.weekday() + 7) % 7
    return first + timedelta(days=offset + 7*(n-1))

def last_weekday(year, month, weekday):
    last = calendar.monthrange(year, month)[1]
    d = date(year, month, last)
    return d - timedelta(days=(d.weekday() - weekday) % 7)

def get_holiday_date(name, year):
    nm = name.lower().replace("’","'").replace(".", "").strip()
    nm = re.sub(r"'s$", "", nm)
    if nm == "thanksgiving":            return nth_weekday(year, 11, 3, 4)
    if nm == "christmas":               return date(year, 12, 25)
    if nm in ("new year day","new year"): return date(year, 1, 1)
    if nm in ("valentine day","valentines day"): return date(year, 2, 14)
    if nm == "labor day":               return nth_weekday(year, 9, 0, 1)
    if nm == "memorial day":            return last_weekday(year, 5, 0)
    if nm in ("president day","presidents day"): return nth_weekday(year, 2, 0, 3)
    if nm == "martin luther king jr day": return nth_weekday(year, 1, 0, 3)
    if nm == "columbus day":            return nth_weekday(year, 10, 0, 2)
    if nm == "veterans day":            return date(year, 11, 11)
    return None


def extract_location(text):
    lower = text.lower()
    # pick up building letters, suite/ste numbers, rooms, floors, streets, halls, corridors, wings, walls, lobby
    bldg     = re.search(r'\b(?:building|bldg\.?)\s*[A-Z]\b', text, re.IGNORECASE)
    suite    = re.search(r'\b(?:suite|ste)\s*(\d+)\b',      text, re.IGNORECASE)
    room     = re.search(r'\b(room\s*\d+|\d{3})\b',         text, re.IGNORECASE)
    floor    = re.search(r'\b\d+(?:st|nd|rd|th)?\s+floor\b', text, re.IGNORECASE)
    street   = re.search(r'\bon\s+([A-Z][\w\s]*?(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?))\b', text)
    hall     = re.search(r'\bresidence hall\b',             lower)
    corridor = re.search(r'\bcorridor\s*(\d+)\b',           lower)
    wing     = re.search(r'\b(north|south|east|west)\s+wing\b', lower)
    wall     = re.search(r'\b(north|south|east|west)\s+wall\b', lower)
    lobby    = re.search(r'\blobby\b',                      lower)

    parts = []
    if bldg:     parts.append(bldg.group(0))
    if suite:    parts.append(f"suite {suite.group(1)}")
    if room:     parts.append(room.group(0))
    if floor:    parts.append(floor.group(0))
    if street:   parts.append(street.group(1))
    if hall:     parts.append('residence hall')
    if corridor: parts.append(f"corridor {corridor.group(1)}")
    if wing:     parts.append(f"{wing.group(1)} wing")
    if wall:     parts.append(f"{wall.group(1)} wall")
    if lobby:    parts.append('lobby')

    return " | ".join(parts) if parts else None


def extract_task_type(text):
    txt = text.lower()
    for cat in TASK_CATEGORIES:
        for kw in TASK_CATEGORIES[cat]:
            if re.search(rf'\b{re.escape(kw)}\b', txt):
                return cat.capitalize()
    return "General"


def extract_asset(text, task_type):
    txt = text.lower()
    kws = TASK_CATEGORIES.get(task_type.lower(), [])

    # if "door handle" appears, we want "door handle"
    comp = re.search(r'\b(' + r'|'.join(map(re.escape, kws)) + r')\s+(' + r'|'.join(map(re.escape, kws)) + r')\b', txt)
    if comp:
        return f"{comp.group(1)} {comp.group(2)}"

    # otherwise find the earliest specific keyword (dropping super-generic words)
    hits = [(m.start(), kw) for kw in kws for m in re.finditer(rf'\b{re.escape(kw)}\b', txt)]
    if len(hits) > 1:
        specific = [h for h in hits if h[1] not in GENERIC_ASSETS]
        if specific:
            hits = specific
    if hits:
        return min(hits, key=lambda x: x[0])[1]

    # if still none, scan every category
    all_hits = [(m.start(), kw)
                for cat in TASK_CATEGORIES.values()
                for kw in cat
                for m in re.finditer(rf'\b{re.escape(kw)}\b', txt)]
    if len(all_hits) > 1:
        spec = [h for h in all_hits if h[1] not in GENERIC_ASSETS]
        if spec:
            all_hits = spec
    if all_hits:
        return min(all_hits, key=lambda x: x[0])[1]

    # fallback to first sensible noun
    doc = nlp(text)
    for tok in doc:
        if tok.pos_ == 'NOUN' and tok.text.lower() not in GENERIC_ASSETS:
            return tok.text
    for tok in doc:
        if tok.pos_ == 'NOUN':
            return tok.text

    return None


def extract_priority(text):
    txt = text.lower()
    if re.search(r'\b(minor|not a big deal)\b', txt):
        return "Low"
    if re.search(r'\bnot\s+(?:urgent|high priority|critical)\b', txt):
        return "Low"
    for lvl in PRIORITY_KEYWORDS:
        for kw in PRIORITY_KEYWORDS[lvl]:
            if re.search(rf'\b{re.escape(kw)}\b', txt):
                return lvl.capitalize()
    return "Medium"


def extract_date(text):
    txt = text.lower()
    now = datetime.now()

    # a quick check for “end of this month” deadlines
    if re.search(r'\bend of (?:this|current) month\b', txt):
        y, m = now.year, now.month
        last = calendar.monthrange(y, m)[1]
        return str(date(y, m, last))

    # sprinkle in some holidays for fun
    hol = re.search(r'\b(next\s+)?(thanksgiving|christmas|new year(?:\'s)? day|new year|'
                    r'valentine(?:’s|s) day|labor day|memorial day|president(?:s)? day|'
                    r'martin luther king jr\.? day|columbus day|veterans day)\b', txt)
    if hol:
        qual, name = hol.group(1), hol.group(2)
        yr = now.year + (1 if qual else 0)
        hd = get_holiday_date(name, yr)
        if not qual and hd and hd < now.date():
            hd = get_holiday_date(name, now.year + 1)
        if hd:
            return str(hd)

    # bail if there's zero date-like hints
    if not re.search(r'\b(?:by\s+)?(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|'
                    r'thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|'
                    r'january|february|march|april|may|june|july|august|'
                    r'september|october|november|december|next|last|'
                    r'tomorrow|yesterday|\d+(?:st|nd|rd|th))\b', txt):
        return None

    # handle ordinals & month names
    mn = [calendar.month_name[i] for i in range(1, 13)]
    exp = re.search(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({"|".join(mn)})\b', text, re.IGNORECASE)
    if exp:
        p = dateparser.parse(exp.group(0), settings={'RELATIVE_BASE': now})
        if p:
            return str(p.date())

    # deadlines by weekday
    by = re.search(r'\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', txt)
    if by:
        b = dateparser.parse(by.group(1), settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if b:
            return str(b.date())

    # deadlines after next weekday
    aft = re.search(r'\bafter\s+next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', txt)
    if aft:
        w = dateparser.parse(aft.group(1), settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if w:
            return str((w + timedelta(days=7)).date())

    # deadlines before next/last weekday
    bf = re.search(r'\bbefore\s+(next|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', txt)
    if bf:
        qual, wd = bf.group(1), bf.group(2)
        base = dateparser.parse(wd, settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
        if base:
            delta = timedelta(days=7)
            return str((base + delta if qual=='next' else base - delta).date())

    # let SpaCy NER try if we're still lost
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == 'DATE' and 'other day' not in ent.text.lower():
            p = dateparser.parse(ent.text, settings={'RELATIVE_BASE': now, 'PREFER_DATES_FROM':'future'})
            if p:
                return str(p.date())

    # best effort fuzzy fallback
    results = search_dates(text, settings={'RELATIVE_BASE': now})
    if results:
        for m, dt in results:
            if 'other day' not in m.lower():
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


# main Streamlit interface
st.set_page_config(page_title="🛠️ Maintenance Task Parser", layout="wide")
st.title("🛠️ Maintenance Task Parser")
st.markdown("enter your maintenance notes, one per line:")

user_input = st.text_area("task descriptions", height=300)
if st.button("parse"):
    if not user_input.strip():
        st.warning("hey, please type something!")
    else:
        st.subheader("parsed output:")
        lines = [l.strip() for l in user_input.splitlines() if l.strip()]
        for i, line in enumerate(lines, 1):
            result = parse_form(line)
            st.markdown(f"• **{i}.** `{line}`")
            st.json(result)
