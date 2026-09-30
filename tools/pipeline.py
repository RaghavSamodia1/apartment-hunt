#!/usr/bin/env python3
"""Scrape candidate projects from propnewz + housiey (+ any extra URLs in the seed).

Reads  data/seed.json   -> list of {id, name, developer, area, urls?: [..], slugs?: [..]}
Writes <out>/<id>.json  -> raw extraction per project (kept outside the project dir)
Prints a one-line status per project.
"""
import concurrent.futures as cf
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scrape import extract, fetch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slugify(s):
    s = s.lower().replace("&", " ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def slug_variants(name, extra):
    base = slugify(name)
    v = [base, base.replace("-and-", "-"), base.replace("codename-", "")]
    v += [slugify(x) for x in extra]
    return list(dict.fromkeys(x for x in v if x))


def clean(s):
    return re.sub(r"\s+", " ", s).strip(" ,.-")


def page_text(h):
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(body))


def parse_narrative(txt):
    """Pull structured facts out of propnewz / housiey template sentences."""
    d = {}
    m = re.search(r"covers an impressive ([\d.]+) acres", txt, re.I) or \
        re.search(r"constructed on ([\d.]+) acres", txt, re.I) or \
        re.search(r"spread (?:across|over) (?:an area of )?([\d.]+) acres", txt, re.I)
    if m:
        d["acres"] = float(m.group(1))
    m = re.search(r"contains a total of ([\d,]+) units, distributed across (.{1,60}?),? each standing tall with (\S+?) floors", txt, re.I)
    if m:
        d["units"] = int(m.group(1).replace(",", ""))
        d["towers_text"] = clean(m.group(2))
        d["floors_text"] = clean(m.group(3))
    else:
        m = re.search(r"contains a total of ([\d,]+) units", txt, re.I)
        if m:
            d["units"] = int(m.group(1).replace(",", ""))
    m = re.search(r"constructed on [\d.]+ acres of land parcel,? (.{1,60}?) with (.{1,40}?) having (.{1,80}?) (?:premium|luxury|residences)", txt, re.I)
    if m:
        d["towers_text"] = d.get("towers_text") or clean(m.group(1))
        d["floors_text"] = d.get("floors_text") or clean(m.group(2))
        d["configs_text"] = clean(m.group(3))
    m = re.search(r"ready for occupancy by (.{3,30}?)(?:,| Casagrand|\.)", txt, re.I)
    if m:
        d["possession"] = clean(m.group(1))
    m = re.search(r"(?:Target Possession|Possession Date|Rera Possession)\s*[-:]?\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?,? ?\d{4})", txt, re.I)
    if m and "possession" not in d:
        d["possession"] = clean(m.group(1))
    m = re.search(r"(PRM/KA/RERA/[\w/]+)", txt)
    if m:
        d["rera"] = m.group(1)
    m = re.search(r"\b(\d{2,3})\s?%\s*(?:open|of the (?:land|area))", txt, re.I)
    if m:
        d["open_space_pct"] = int(m.group(1))
    prices = re.findall(r"(?:₹|Rs\.?)\s?[\d.,]+\s?(?:Cr|Crore|Lakh|L)\w*\.?", txt)
    if prices:
        d["price_mentions"] = list(dict.fromkeys(clean(p) for p in prices))[:6]
    return d


def try_site(tmpl, slugs):
    last = None
    for s in slugs:
        url = tmpl.format(slug=s)
        try:
            final, h = fetch(url, timeout=25)
        except Exception as e:  # noqa: BLE001
            last = str(e)
            continue
        if len(h) < 20000:
            last = "tiny page"
            continue
        return url, h
    return None, last


def run_one(p):
    out = {"id": p["id"], "name": p["name"], "sources": []}
    slugs = slug_variants(p["name"], p.get("slugs", []))
    sites = [("propnewz", "https://www.propnewz.com/project/{slug}"),
             ("housiey", "https://housiey.com/projects/{slug}")]
    urls = []
    for label, tmpl in sites:
        url, h = try_site(tmpl, slugs)
        if url:
            urls.append(url)
    urls += p.get("urls", [])
    for url in urls:
        try:
            e = extract(url)
            _, h = fetch(url)
            e["narrative"] = parse_narrative(page_text(h))
            out["sources"].append(e)
        except Exception as ex:  # noqa: BLE001
            out["sources"].append({"url": url, "error": str(ex)})
    return out


def main():
    seed = json.load(open(os.path.join(ROOT, "data", "seed.json")))
    outdir = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(outdir, exist_ok=True)
    todo = [p for p in seed if not only or p["id"] in only]
    with cf.ThreadPoolExecutor(6) as ex:
        for res in ex.map(run_one, todo):
            json.dump(res, open(os.path.join(outdir, res["id"] + ".json"), "w"), indent=1, ensure_ascii=False)
            ok = [s["url"].split("/")[2] for s in res["sources"] if "error" not in s]
            nar = {}
            for s in res["sources"]:
                nar.update({k: v for k, v in s.get("narrative", {}).items() if k != "price_mentions"})
            print(res["id"], "|", ",".join(ok) or "NONE", "|", json.dumps(nar, ensure_ascii=False)[:230], flush=True)


if __name__ == "__main__":
    main()
