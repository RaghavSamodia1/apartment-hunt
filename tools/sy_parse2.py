#!/usr/bin/env python3
"""Second squareyards pass for the curated projects: JSON-LD geo + categorised full-size images.

Usage: sy_parse2.py OUTDIR            (reads data/core_slugs.json, data/ext_slugs.json, data/extra_urls.json)
"""
import collections
import concurrent.futures as cf
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import sy_parse  # noqa: E402
from scrape import fetch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = "/private/tmp/claude-501/-Users-raghavsamodia-apartment-hunt/f660af02-b948-46eb-8fe7-ebbd60181611/scratchpad/"
IMG_RE = re.compile(r"https://static\.squareyards\.com/resources/images/bangalore/(project-image|unit-image)/([^\"'\s\\)<>?]+?\.(?:jpg|jpeg|png|webp))", re.I)
GEO_RE = re.compile(r'"geo"\s*:\s*\{\s*"@type"\s*:\s*"GeoCoordinates"\s*,\s*"latitude"\s*:\s*"?(-?\d+\.\d+)"?\s*,\s*"longitude"\s*:\s*"?(-?\d+\.\d+)', re.I)


def images(h):
    found = []
    for m in IMG_RE.finditer(h):
        d, f = m.group(1), m.group(2)
        u = f"https://static.squareyards.com/resources/images/bangalore/{d}/{f}"
        if u not in found:
            found.append(u)
    proj = [u for u in found if "/project-image/" in u]
    prefixes = collections.Counter(u.split("/")[-1].split("-project-")[0] for u in proj if "-project-" in u.split("/")[-1])
    own = prefixes.most_common(1)[0][0] if prefixes else None
    mine = [u for u in proj if own and u.split("/")[-1].startswith(own + "-project-")]
    units = [u for u in found if "/unit-image/" in u]
    out = {"hero": None, "gallery": [], "master": [], "floorplans": []}
    for u in mine:
        f = u.split("/")[-1]
        if re.search(r"master-?plan|site-?plan|layout-?plan", f):
            out["master"].append(u)
        elif "floor-plans" in f:
            out["floorplans"].append(u)
        elif "location" in f:
            continue
        elif "large-image" in f and not out["hero"]:
            out["hero"] = u
        else:
            out["gallery"].append(u)
    if not out["hero"] and out["gallery"]:
        out["hero"] = out["gallery"].pop(0)
    seen = set()
    for u in units:
        key = re.sub(r"-3d-\d+", "", u.split("/")[-1])
        if "-3d-" in u.split("/")[-1] and key in seen:
            continue
        seen.add(key)
        out["floorplans"].append(u)
    out["floorplans"] = out["floorplans"][:8]
    out["gallery"] = out["gallery"][:10]
    return out


def parse_url(slug, url):
    rec = None
    m = re.search(r"/bangalore-residential-property/([^/]+)/(\d+)/project", url)
    # reuse sy_parse for the text fields by temporarily swapping the URL builder
    h_url, h = fetch(url)
    ls = sy_parse.lines_of(h)
    r = {"slug": slug, "sy_url": url, "title": ls[0] if ls else None}
    mm = re.match(r"(.+?),\s*(.+?),\s*Bangalore", r["title"] or "")
    if mm:
        r["name"], r["locality"] = mm.group(1), mm.group(2)
    else:
        t = (r["title"] or slug).split("|")[0].split(",")[0].strip()
        r["name"] = t
        loc = ls[16].split(",")[0] if len(ls) > 16 else None
        r["locality"] = loc
        if loc and t.endswith(" " + loc):
            r["name"] = t[: -len(loc) - 1]
    g = lambda k, n=1: sy_parse.after(ls, k, n)
    r["status"] = (g("Project Status") or [None])[0]
    r["possession"] = (g("Possession Starting From") or [None])[0]
    r["config"] = (g("Unit Config") or [None])[0]
    sz = g("Size", 2)
    r["size"] = " ".join(sz) if sz else None
    u = g("Number of Units")
    r["units"] = int(u[0]) if u and u[0].isdigit() else None
    a = g("Total Area")
    r["acres_text"] = a[0] if a else None
    for l in ls[:60]:
        if l.startswith("₹") and "Per Sq" not in l and "Loan" not in l and "Charges" not in l:
            r["price_text"] = l
            break
    r["ppsf"] = next((l for l in ls[:60] if "Per Sq. Ft" in l and "₹" in l), None)
    v = [sy_parse.to_cr(x.group(0)) for x in re.finditer(r"[\d.,]+\s?(?:Cr|Lac|Lakh|L)\b", r.get("price_text", ""))]
    v = [x for x in v if x]
    r["price_min_cr"], r["price_max_cr"] = (min(v), max(v)) if v else (None, None)
    r["summary"] = next((l for l in ls[10:40] if "project houses" in l or "Under Construction" in l or "Ready to Move" in l or "Ready To Move" in l or " is situated " in l or "brings together" in l), None)
    dev = None
    for l in ls[40:140]:
        d = re.match(r"About .+? by (.+)$", l)
        if d:
            dev = d.group(1)
            break
    if not dev and r.get("summary"):
        d = re.search(r"Developed by ([A-Z][\w&.' -]+?)(?:,|\.| and )", r["summary"])
        dev = d.group(1) if d else None
    r["developer"] = dev
    rows = []
    for i, l in enumerate(ls[:700]):
        q = re.match(r"^(\d(?:\.5)?) BHK (Apartment|Villa|Flat|Penthouse|Duplex)", l)
        if q and i + 3 < len(ls) and re.match(r"^[\d,]+$", ls[i + 1]) and ls[i + 3].startswith("₹"):
            rows.append({"type": l, "sqft": int(ls[i + 1].replace(",", "")), "price": ls[i + 3], "cr": sy_parse.to_cr(ls[i + 3])})
    r["price_rows"] = rows[:12]
    desc = []
    for i, l in enumerate(ls):
        if l.startswith("About ") and " by " in l:
            desc = ls[i + 1:i + 6]
            break
    r["desc"] = " ".join(desc)[:1500]
    conn = []
    for i, l in enumerate(ls):
        if l == "Connectivity Highlights":
            conn = ls[i + 1:i + 9]
            break
    r["connectivity"] = [c for c in conn if re.search(r"km", c, re.I)][:8]
    rr = re.findall(r"PRM/KA/RERA/[\w/ ]+?/PR/\d+/\d+", h)
    r["rera"] = re.sub(r"\s+", "", rr[0]) if rr else None
    geo = GEO_RE.search(h)
    r["geo"] = [float(geo.group(1)), float(geo.group(2))] if geo else None
    r["img"] = images(h)
    if r["geo"]:
        r["km_from_yelahanka"] = round(sy_parse.km(sy_parse.YELAHANKA, r["geo"]), 1)
    # tower hints from the AI-written master-plan section
    tp = [l for l in ls if re.search(r"\btowers?\b", l, re.I) and re.search(r"\b(eight|seven|six|five|four|three|two|nine|ten|\d+)\b", l, re.I) and len(l) < 200]
    r["tower_hint"] = tp[:4]
    return r


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    idx = json.load(open(SCR + "sy_index.json"))
    jobs = {}
    for f in ("core_slugs.json", "ext_slugs.json"):
        for s in json.load(open(os.path.join(ROOT, "data", f))):
            if s in idx:
                jobs[s] = f"https://www.squareyards.com/bangalore-residential-property/{s}/{idx[s][0]}/project"
    extra = os.path.join(ROOT, "data", "extra_urls.json")
    if os.path.exists(extra):
        jobs.update(json.load(open(extra)))
    todo = {s: u for s, u in jobs.items() if not os.path.exists(os.path.join(out, s + ".json"))}
    print("todo", len(todo), flush=True)

    def go(item):
        s, u = item
        for _ in range(2):
            try:
                time.sleep(0.25)
                r = parse_url(s, u)
                json.dump(r, open(os.path.join(out, s + ".json"), "w"), ensure_ascii=False)
                return s, "ok"
            except Exception as ex:  # noqa: BLE001
                err = str(ex)
                time.sleep(2)
        return s, "ERR " + err

    n = 0
    with cf.ThreadPoolExecutor(5) as ex:
        for s, st in ex.map(go, todo.items()):
            n += 1
            if st != "ok":
                print(s, st, flush=True)
            if n % 40 == 0:
                print("done", n, flush=True)


if __name__ == "__main__":
    main()
