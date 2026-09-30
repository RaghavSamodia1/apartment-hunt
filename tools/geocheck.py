#!/usr/bin/env python3
"""Independent geo cross-check against OpenStreetMap Nominatim (1 request/second)."""
import json, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, 'tools')
from build_data import km
S = "/private/tmp/claude-501/-Users-raghavsamodia-apartment-hunt/f660af02-b948-46eb-8fe7-ebbd60181611/scratchpad/"
s = open('data/projects.js').read()
P = json.loads(re.search(r'window\.PROJECTS = (\[.*\]);', s, re.S).group(1))
out = {}
for p in [p for p in P if p['tier'] == 'core']:
    name = re.sub(r"[–—]", "-", p['name']).replace('&', 'and')
    qs = [f"{name}, Bengaluru", f"{name} {p['area']}, Bengaluru"]
    best = None
    for q in qs:
        url = "https://nominatim.openstreetmap.org/search?format=json&limit=3&countrycodes=in&viewbox=77.3,13.3,77.9,12.85&q=" + urllib.parse.quote(q)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "apartment-hunt-personal/1.0"})
            res = json.load(urllib.request.urlopen(req, timeout=20))
        except Exception as e:
            res = []
        time.sleep(1.1)
        toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split() if len(t) > 2 and t not in ("and", "the", "phase")]
        for r in res:
            dn = r['display_name'].lower()
            if sum(1 for t in toks[:3] if t in dn) >= min(2, len(toks)):
                d = km((p['lat'], p['lng']), (float(r['lat']), float(r['lon'])))
                if best is None or d < best[0]:
                    best = (round(d, 2), r['display_name'][:70], float(r['lat']), float(r['lon']))
        if best:
            break
    out[p['id']] = best
    print(p['id'], best, flush=True)
json.dump(out, open(S + 'geocheck.json', 'w'))
