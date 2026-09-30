#!/usr/bin/env python3
"""Merge scraped records + manual overrides into data/projects.js (read by index.html)."""
import collections
import datetime
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = "/private/tmp/claude-501/-Users-raghavsamodia-apartment-hunt/f660af02-b948-46eb-8fe7-ebbd60181611/scratchpad/"
CENTER = (13.1005, 77.5963)

AREA_MAP = [
    (r"thanisandra", "Thanisandra"), (r"hennur", "Hennur"), (r"jakkur", "Jakkur"), (r"kogilu", "Kogilu"),
    (r"yelahanka new town", "Yelahanka New Town"), (r"yelahanka", "Yelahanka"), (r"hebbal|rachenahalli|amruthahalli", "Hebbal"),
    (r"bagalur|bagaluru", "Bagalur"), (r"airport", "Airport Road"), (r"devanahalli", "Devanahalli"),
    (r"vidyaranyapura", "Vidyaranyapura"), (r"chikkagubbi|kothanur", "Kothanur"), (r"bellary", "Bellary Road"),
    (r"kannur", "Kannur"), (r"nagavara|nagawara", "Nagavara"), (r"chikkajala", "Chikkajala"), (r"rajanukunte", "Rajanukunte"),
    (r"doddaballap", "Doddaballapur Road"), (r"sampigehalli|sampige", "Sampigehalli"), (r"avalahalli", "Thanisandra"),
    (r"shettigere", "Devanahalli"), (r"hunasamaranahalli", "Bellary Road"), (r"honnenahalli", "Yelahanka"),
]
DOMAIN_LABEL = {"www.propnewz.com": "PropNewz", "housiey.com": "Housiey", "proptimes.org": "PropTimes", "www.propzilla.in": "PropZilla"}


def km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(x))


def area_of(loc):
    for pat, name in AREA_MAP:
        if re.search(pat, (loc or "").lower()):
            return name
    return (loc or "North Bengaluru").strip() or "North Bengaluru"


def floor_int(tok):
    t = tok.upper().replace(" ", "")
    m = re.search(r"\+(\d{1,2})(?:/(\d{1,2}))?$", t)
    if m:
        return int(m.group(2) or m.group(1))
    if re.fullmatch(r"\d{1,2}", t):
        return int(t)
    return None


def tower_int(txt):
    w = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    m = re.search(r"\b(\d{1,2}|" + "|".join(w) + r")\b", txt.lower())
    if not m:
        return None
    v = m.group(1)
    return int(v) if v.isdigit() else w[v]


def consensus(hits):
    """Vote floors / towers across secondary sources (one vote per domain)."""
    fvotes, tvotes, ftext = collections.defaultdict(set), collections.defaultdict(set), {}
    for h in hits:
        dom = h["url"].split("/")[2]
        n = h.get("narrative", {})
        toks = []
        if n.get("floors_text"):  # only the structured template sentence; page-wide mentions pick up "related projects" noise
            toks.append(n["floors_text"].split()[0])
        for t in toks:
            v = floor_int(t)
            if v and 2 <= v <= 60:
                fvotes[v].add(dom)
                ftext.setdefault(v, t.upper())
        tt = n.get("towers_text")
        if tt and re.search(r"tower|block", tt, re.I):
            v = tower_int(tt)
            if v:
                tvotes[v].add(dom)
    out = {}
    if fvotes:
        ranked = sorted(fvotes.items(), key=lambda kv: (-len(kv[1]), -kv[0]))
        top, doms = ranked[0]
        out["floors"], out["floors_text"] = top, ftext[top]
        out["floors_doms"] = sorted(doms)
        second = len(ranked[1][1]) if len(ranked) > 1 else 0
        out["floors_conf"] = "high" if len(doms) >= 2 and second < len(doms) else ("low" if len(ranked) > 1 else "medium")
        if len(ranked) > 1:
            out["floors_alt"] = [f"{ftext[v]} ({', '.join(d)})" for v, d in ranked]
    if tvotes:
        ranked = sorted(tvotes.items(), key=lambda kv: (-len(kv[1]), -kv[0]))
        out["towers"] = ranked[0][0]
        out["towers_conf"] = "high" if len(ranked[0][1]) >= 2 and len(ranked) == 1 else ("low" if len(ranked) > 1 else "medium")
    return out


def parse_acres(t):
    m = re.search(r"([\d.]+)", t or "")
    return round(float(m.group(1)), 2) if m else None


def clean_name(n):
    n = re.sub(r"\s+", " ", n or "").strip()
    n = re.sub(r"^(Prestige|Brigade)\s+", lambda m: m.group(0), n)
    return n


def build_one(slug, sy, enr, man, tier):
    r = {"id": slug, "tier": tier}
    r["name"] = man.get("name") or clean_name(sy.get("name") or slug.replace("-", " ").title())
    r["developer"] = man.get("developer") or sy.get("developer")
    r["locality"] = sy.get("locality")
    geo = man.get("geo") or sy.get("geo") or sy.get("coords")
    r["lat"], r["lng"] = round(geo[0], 6), round(geo[1], 6)
    r["km"] = round(km(CENTER, geo), 1)
    r["area"] = area_of(man.get("area") or sy.get("locality") or sy.get("name"))
    r["status"] = "Ready to Move" if (sy.get("status") or "").lower().startswith(("ready", "partially")) else (sy.get("status") or "Under Construction")
    if (sy.get("status") or "").lower().startswith("partially"):
        r["status"] = "Partially Ready"
    r["possession"] = man.get("possession") or (sy.get("possession") if r["status"] not in ("Ready to Move",) else None)
    r["pmin"], r["pmax"] = man.get("pmin", sy.get("price_min_cr")), man.get("pmax", sy.get("price_max_cr"))
    if r["pmin"] is not None and r["pmax"] is not None and r["pmax"] < r["pmin"]:
        r["pmax"] = r["pmin"]
    r["ppsf"] = (sy.get("ppsf") or "").replace("Per Sq. Ft.", "/ sq ft").replace("₹ ", "₹") or None
    cfg = sy.get("config") or ""
    r["bhk"] = sorted({float(x) for x in re.findall(r"(\d(?:\.5)?)", cfg.split("BHK")[0])})
    r["bhk_text"] = re.sub(r"\s*(Flats?|Apartments?)$", "", cfg).strip() or "—"
    sz = re.findall(r"[\d,]+", sy.get("size") or "")
    r["size"] = f"{sz[0]}–{sz[1]} sq ft" if len(sz) >= 2 else (f"{sz[0]} sq ft" if sz else None)
    r["units_table"] = [{"t": re.sub(r"\s*(Apartment|Flat)$", "", x["type"]), "sqft": x["sqft"], "cr": x["cr"]} for x in sy.get("price_rows", [])]
    r["units"] = sy.get("units")
    r["acres"] = parse_acres(sy.get("acres_text"))
    # floors / towers
    cons = consensus(enr.get("hits", [])) if enr else {}
    for k in ("floors", "floors_text", "floors_conf", "towers", "towers_conf"):
        if k in cons:
            r[k] = cons[k]
    if cons.get("floors_alt"):
        r["floors_alt"] = cons["floors_alt"]
    for k in ("floors", "floors_text", "towers", "towers_note", "units", "acres", "open_pct", "rera", "master_note", "about"):
        if k in man:
            r[k] = man[k]
    if "floors_text" in man or "floors" in man:
        conf = man.get("conf", "medium")
        cf = cons.get("floors")
        if man.get("floors") and cf:
            if man["floors"] == cf:
                conf = conf if conf == "low" else "high"
            else:
                conf = "low"
                r["floors_alt"] = cons.get("floors_alt") or [f"{cons.get('floors_text')} ({', '.join(cons.get('floors_doms', []))})"]
        r["floors_conf"] = conf
        if man.get("src"):
            r["floors_src"] = man["src"]
    if "towers" in man and cons.get("towers") and man["towers"] and cons["towers"] != man["towers"] and not man.get("towers_note"):
        r["towers_note"] = f"another source says {cons['towers']}"
    r.setdefault("floors", None), r.setdefault("towers", None)
    # open space
    if not r.get("open_pct"):
        ops = [h["narrative"].get("open_space_pct") for h in (enr or {}).get("hits", []) if h.get("narrative", {}).get("open_space_pct")]
        if ops:
            r["open_pct"] = ops[0]
        else:
            m = re.search(r"(\d{2})\s?%\s*open", (sy.get("desc") or "") + " " + (sy.get("summary") or ""), re.I)
            if m:
                r["open_pct"] = int(m.group(1))
    r["rera"] = r.get("rera") or sy.get("rera") or next((h["narrative"].get("rera") for h in (enr or {}).get("hits", []) if h.get("narrative", {}).get("rera")), None)
    # images
    im = sy.get("img", {})
    hero = man.get("hero") or im.get("hero")
    master = list(im.get("master", []))
    gallery = list(im.get("gallery", []))
    for h in (enr or {}).get("hits", []):
        for mp in h.get("master", []):
            if mp not in master and len(master) < 3 and not master:
                master.append(mp)
        if not hero and h.get("og"):
            hero = h["og"][0]
    if man.get("master_extra"):
        master += [m for m in man["master_extra"] if m not in master]
    r["img"] = {"hero": hero, "gallery": gallery, "master": master, "floorplans": im.get("floorplans", [])}
    # links
    other = []
    for h in (enr or {}).get("hits", []):
        dom = h["url"].split("/")[2]
        other.append({"label": DOMAIN_LABEL.get(dom, dom), "url": h["url"]})
    for lk in man.get("links", []):
        other.append(lk)
    other.insert(0, {"label": "Squareyards", "url": sy.get("sy_url")})
    r["links"] = {"other": other}
    r["conn"] = sy.get("connectivity", [])
    about = sy.get("summary") or sy.get("desc") or ""
    r["about"] = man.get("about") or re.sub(r"\s+", " ", about)[:420]
    # geo quality: any secondary coordinate within 600 m?
    sec = [h["coords"][0] for h in (enr or {}).get("hits", []) if h.get("coords")]
    osm = GEOCHECK.get(slug)
    if osm and osm[0] is not None and osm[0] < 0.8:
        sec.append((osm[2], osm[3]))
    r["geo_q"] = "verified" if any(km(geo, c) < 0.8 for c in sec) else "single"
    if man.get("geo"):
        r["geo_q"] = "single"
        if man.get("geo_note"):
            r["geo_note"] = man["geo_note"]
    return r


GEOCHECK = {}


def main():
    global GEOCHECK
    gp = SCR + "geocheck.json"
    if os.path.exists(gp):
        GEOCHECK = json.load(open(gp))
    core = json.load(open(os.path.join(ROOT, "data", "core_slugs.json")))
    ext = json.load(open(os.path.join(ROOT, "data", "ext_slugs.json")))
    manual = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if re.fullmatch(r"manual(_\d+)?\.json", fn):
            part = json.load(open(os.path.join(ROOT, "data", fn)))
            for k, v in part.items():
                if k in ("_drop", "_add_core"):
                    manual[k] = manual.get(k, []) + v
                else:
                    manual.setdefault(k, {}).update(v)
    extra = json.load(open(os.path.join(ROOT, "data", "extra_urls.json")))
    drop = set(manual.get("_drop", []))
    add_core = [s for s in manual.get("_add_core", [])]
    out, missing, done = [], [], set()
    for tier, slugs in (("core", list(dict.fromkeys(core + add_core + list(extra)))), ("extended", ext)):
        for s in slugs:
            if s in drop or s in done:
                continue
            done.add(s)
            p = SCR + f"sy2/{s}.json"
            if not os.path.exists(p):
                missing.append(s)
                continue
            sy = json.load(open(p))
            if not (sy.get("geo") or sy.get("coords")):
                missing.append(s)
                continue
            enr = None
            if tier == "core":
                hits, seen = [], set()
                for d in ("enrich2", "enrich"):
                    ep = SCR + f"{d}/{s}.json"
                    if os.path.exists(ep):
                        for h in json.load(open(ep)).get("hits", []):
                            if h["url"] not in seen:
                                seen.add(h["url"]); hits.append(h)
                enr = {"hits": hits}
            if enr:  # drop empty shell pages ("<slug> - housiey") that only echo the URL slug
                enr["hits"] = [h for h in enr.get("hits", []) if not re.fullmatch(r"[a-z0-9\-]+ - housiey", (h.get("title") or "").strip(), re.I)]
            out.append(build_one(s, sy, enr, manual.get(s, {}), tier))
    # drop anything outside the north-Bengaluru belt or unusable
    out = [r for r in out if r["km"] <= 22]
    out.sort(key=lambda r: (r["tier"] != "core", r["km"]))
    meta = {"center": list(CENTER), "budget_cr": 2.5, "area": "Yelahanka & north Bengaluru", "generated": datetime.date.today().isoformat(),
            "core": sum(1 for r in out if r["tier"] == "core"), "extended": sum(1 for r in out if r["tier"] == "extended")}
    with open(os.path.join(ROOT, "data", "projects.js"), "w") as f:
        f.write("window.META = " + json.dumps(meta, ensure_ascii=False) + ";\n")
        f.write("window.PROJECTS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(meta, "missing:", missing)
    fl = sum(1 for r in out if r["tier"] == "core" and r.get("floors"))
    mp = sum(1 for r in out if r["tier"] == "core" and r["img"]["master"])
    print(f"core with floors: {fl}/{meta['core']}   core with master plan: {mp}/{meta['core']}")


if __name__ == "__main__":
    main()
