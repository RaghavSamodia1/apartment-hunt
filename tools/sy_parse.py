#!/usr/bin/env python3
"""Parse a squareyards project page into a compact record.

Usage: sy_parse.py INDEX.json OUTDIR     (INDEX: {slug: [id, label]})
"""
import concurrent.futures as cf
import html
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from scrape import extract, fetch  # noqa: E402

YELAHANKA = (13.1005, 77.5963)


def km(a, b):
    r = 6371
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def to_cr(s):
    m = re.search(r"([\d.,]+)\s*(Cr|Lac|Lakh|L)\b", s or "", re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return round(v if m.group(2).lower() == "cr" else v / 100, 3)


def lines_of(h):
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", "\n", body)
    body = html.unescape(body)
    ls = [re.sub(r"\s+", " ", l).strip() for l in body.split("\n")]
    return [l for l in ls if l]


def after(ls, key, n=1, start=0):
    for i in range(start, min(len(ls), 400)):
        if ls[i] == key:
            return ls[i + 1:i + 1 + n]
    return []


def parse(slug, pid):
    url = f"https://www.squareyards.com/bangalore-residential-property/{slug}/{pid}/project"
    e = extract(url)
    _, h = fetch(url)
    ls = lines_of(h)
    r = {"slug": slug, "sy_id": pid, "sy_url": url, "title": ls[0] if ls else e["title"]}
    m = re.match(r"(.+?),\s*(.+?),\s*Bangalore", r["title"] or "")
    if m:
        r["name"], r["locality"] = m.group(1), m.group(2)
    else:
        r["name"] = (r["title"] or slug).split(" Yelahanka")[0].split(",")[0]
    r["status"] = (after(ls, "Project Status") or [None])[0]
    r["possession"] = (after(ls, "Possession Starting From") or [None])[0]
    r["config"] = (after(ls, "Unit Config") or [None])[0]
    sz = after(ls, "Size", 2)
    r["size"] = " ".join(sz) if sz else None
    u = after(ls, "Number of Units")
    r["units"] = int(u[0]) if u and u[0].isdigit() else None
    a = after(ls, "Total Area")
    r["acres_text"] = a[0] if a else None
    for l in ls[:60]:
        if l.startswith("₹") and "Per Sq" not in l and "Loan" not in l and "Charges" not in l:
            r["price_text"] = l
            break
    r["ppsf"] = next((l for l in ls[:60] if "Per Sq. Ft" in l and "₹" in l), None)
    pr = re.findall(r"₹\s?[\d.,]+\s?(?:Cr|Lac|Lakh|L)", r.get("price_text", ""))
    r["price_min_cr"] = to_cr(pr[0]) if pr else None
    r["price_max_cr"] = to_cr(pr[-1]) if pr else None
    r["summary"] = next((l for l in ls[10:40] if l.startswith("The project houses") or " is Under Construction" in l or "Ready to Move" in l or "Ready To Move" in l), None)
    # developer
    dev = None
    for l in ls[40:120]:
        mm = re.match(r"About .+? by (.+)$", l)
        if mm:
            dev = mm.group(1)
            break
    r["developer"] = dev
    # price list rows
    rows = []
    for i, l in enumerate(ls[:700]):
        mm = re.match(r"^(\d(?:\.5)?) BHK (Apartment|Villa|Flat|Penthouse|Duplex)", l) or re.match(r"^(Studio|Plot|Villa)", l)
        if mm and i + 3 < len(ls) and re.match(r"^[\d,]+$", ls[i + 1]) and ls[i + 3].startswith("₹"):
            rows.append({"type": l, "sqft": int(ls[i + 1].replace(",", "")), "price": ls[i + 3], "cr": to_cr(ls[i + 3])})
    r["price_rows"] = rows[:12]
    # description
    desc = []
    for i, l in enumerate(ls):
        if l.startswith("About ") and " by " in l:
            desc = ls[i + 1:i + 7]
            break
    r["desc"] = " ".join(desc)[:1200]
    # connectivity
    conn = []
    for i, l in enumerate(ls):
        if l == "Connectivity Highlights":
            conn = ls[i + 1:i + 9]
            break
    r["connectivity"] = [c for c in conn if re.search(r"km|Km", c)][:8]
    r["rera"] = next(iter(re.findall(r"PRM/KA/RERA/[\w/ ]+?/PR/\d+/\d+", h)), None)
    r["og_image"] = e["og_image"]
    r["master_plan_imgs"] = [x[0] for x in e["master_plan_imgs"]]
    r["gallery_imgs"] = [x[0] for x in e["gallery_imgs"]]
    r["coords"] = e["coords"][0] if e["coords"] else None
    if r["coords"]:
        r["km_from_yelahanka"] = round(km(YELAHANKA, r["coords"]), 1)
    return r


def main():
    idx = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    todo = [(s, v[0]) for s, v in idx.items() if not os.path.exists(os.path.join(out, s + ".json"))]
    print("todo", len(todo), flush=True)

    def go(t):
        s, i = t
        for attempt in range(2):
            try:
                time.sleep(0.3)
                r = parse(s, i)
                json.dump(r, open(os.path.join(out, s + ".json"), "w"), ensure_ascii=False)
                return s, "ok"
            except Exception as ex:  # noqa: BLE001
                err = str(ex)
                time.sleep(2)
        return s, "ERR " + err

    done = 0
    with cf.ThreadPoolExecutor(5) as ex:
        for s, st in ex.map(go, todo):
            done += 1
            if st != "ok":
                print(s, st, flush=True)
            if done % 50 == 0:
                print("done", done, flush=True)


if __name__ == "__main__":
    main()
