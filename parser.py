import re

def clean(s):
    return re.sub(r'\\s+', ' ', s or '').strip()

def to_float(s):
    if s is None:
        return None
    m = re.search(r'-?\\d+(?:[.,]\\d+)?', clean(s))
    return float(m.group().replace(',', '.')) if m else None

def norm(s):
    return re.sub(r'[^a-z0-9]+', '', clean(s).lower())

def parse_table(headers, rows):
    hs = [norm(h) for h in headers]
    idx = {h:i for i,h in enumerate(hs)}
    market = 'handicap' if 'handicap' in idx else ('total' if any(x in idx for x in ('total','over','under','ou')) else None)
    if not market or not rows:
        return []
    row = rows[0]
    def cell(name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None
    if market == 'handicap':
        line = to_float(cell('handicap'))
        home = to_float(cell('home'))
        away = to_float(cell('away'))
        out=[]
        if line is not None and home is not None:
            out.append({'selection':'Home','line':line,'price':home})
        if line is not None and away is not None:
            out.append({'selection':'Away','line':-line,'price':away})
        return out
    total = to_float(cell('total'))
    over = to_float(cell('over'))
    under = to_float(cell('under'))
    out=[]
    if total is not None and over is not None:
        out.append({'selection':'Over','line':total,'price':over})
    if total is not None and under is not None:
        out.append({'selection':'Under','line':total,'price':under})
    return out
