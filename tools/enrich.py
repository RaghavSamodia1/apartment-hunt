#!/usr/bin/env python3
"""Enrich core projects with floors/towers/master-plan info from secondary sources.

Usage: enrich.py OUTDIR [slug ...]
Reads data/core_slugs.json and the squareyards records; for each project tries
propnewz / housiey / proptimes / propzilla URLs built from the name and stores
every floor/tower mention it finds together with the source URL.
"""
import concurrent.futures as cf
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scrape import extract, fetch  # noqa: E402
from pipeline import page_text, parse_narrative, slugify  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = "/private/tmp/claude-501/-Users-raghavsamodia-apartment-hunt/f660af02-b948-46eb-8fe7-ebbd60181611/scratchpad/"

FLOOR_PATS = [
    # 2B+G+14 / B+G+14 / 3B+G+33/34 / G+14 / B+S+21 / 2B+G+14 floors
    re.compile(r"\b((?:\d\s?)?(?:B|LG|S|P)\s?\+\s?(?:G|S|P)\s?\+\s?\d{1,2}(?:\s?/\s?\d{1,2})?)\b", re.I),
    re.compile(r"\b(G\s?\+\s?\d{1,2}(?:\s?/\s?\d{1,2})?)\b"),
    re.compile(r"\b(\d{1,2})\s?(?:-\s?)?(?:floors?|storeys?|stories|storey)\b", re.I),
]
TOWER_PAT = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:high[- ]rise\s+|residential\s+|iconic\s+)?(?:towers?|blocks?|wings?)\b", re.I)


def mentions(txt):
    fl, tw = [], []
    for sent in re.split(r"(?<=[.!?])\s+|\s{2,}", txt):
        if len(sent) > 400:
            continue
        for p in FLOOR_PATS:
            for m in p.finditer(sent):
                fl.append((m.group(1).replace(" ", ""), sent.strip()[:160]))
        for m in TOWER_PAT.finditer(sent):
            tw.append((m.group(1).lower(), sent.strip()[:160]))
    # keep unique tokens, first 8
    seen, out_f = set(), []
    for t, s in fl:
        if t not in seen:
            seen.add(t); out_f.append((t, s))
    seen, out_t = set(), []
    for t, s in tw:
        if t not in seen:
            seen.add(t); out_t.append((t, s))
    return out_f[:8], out_t[:6]


LOC_WORDS = r"(thanisandra|main|road|yelahanka|new|town|kogilu|hebbal|hennur|jakkur|sathnur|bagalur|devanahalli|airport|bellary|rachenahalli|kothanur|vidyaranyapura)"


def name_variants(name):
    names = [name]
    stripped = re.sub(r"(\s+" + LOC_WORDS + r")+$", "", name, flags=re.I).strip()
    names.append(stripped)
    names.append(re.sub(r"\(.*?\)", "", stripped).strip())
    v = []
    for n in names:
        base = slugify(n)
        v += [base, base.replace("-and-", "-"), re.sub(r"^l-t-", "lnt-", base), base.replace("codename-", "")]
    return list(dict.fromkeys(x for x in v if x))


def build_urls(rec, extra, manual_name=None):
    names = (name_variants(manual_name) if manual_name else []) + name_variants(rec["name"]) + [slugify(x) for x in extra]
    names = list(dict.fromkeys(names))
    loc = slugify(rec.get("locality") or "yelahanka")
    urls = []
    for s in names:
        urls += [f"https://www.propnewz.com/project/{s}", f"https://housiey.com/projects/{s}",
                 f"https://proptimes.org/property/{s}/", f"https://proptimes.org/property/{s}-2/"]
        for l in dict.fromkeys([loc, "yelahanka"]):
            urls.append(f"https://www.propzilla.in/property/{s}-in-{l}-bangalore")
    return urls


def title_ok(title, name):
    if not title:
        return False
    t = re.sub(r"[^a-z0-9 ]", "", title.lower().replace("&", "and"))
    toks = [w for w in re.sub(r"[^a-z0-9 ]", "", name.lower().replace("&", "and")).split() if len(w) > 2 and w not in ("the", "and")]
    return sum(1 for w in toks[:3] if w in t) >= min(2, len(toks))


def run_one(slug):
    recs = SY[slug]
    extra = MANUAL.get(slug, {}).get("slugs", [])
    out = {"slug": slug, "name": recs["name"], "hits": []}
    tried, domains_hit = set(), set()
    for url in build_urls(recs, extra, MANUAL.get(slug, {}).get("name")):
        dom = url.split("/")[2]
        if dom in domains_hit:
            continue
        try:
            final, h = fetch(url, timeout=12)
        except Exception:
            continue
        m = re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        if len(h) < 15000 or not title_ok(title, recs["name"]):
            continue
        domains_hit.add(dom)
        txt = page_text(h)
        fl, tw = mentions(txt)
        e = extract(url)
        hit = {"url": url, "title": title[:100], "narrative": parse_narrative(txt), "floors": fl, "towers": tw,
               "master": [x[0] for x in e["master_plan_imgs"]][:3], "og": e["og_image"][:1], "coords": e["coords"][:1]}
        out["hits"].append(hit)
    return out


def main():
    global SY, MANUAL
    outdir = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(outdir, exist_ok=True)
    allrecs = json.load(open(SCR + "sy_all.json"))
    SY = {r["slug"]: r for r in allrecs}
    MANUAL = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if re.fullmatch(r"manual(_\d+)?\.json", fn):
            for k, v in json.load(open(os.path.join(ROOT, "data", fn))).items():
                if isinstance(v, dict):
                    MANUAL.setdefault(k, {}).update(v)
    slugs = json.load(open(os.path.join(ROOT, "data", "core_slugs.json")))
    SY2 = {}
    for f in os.listdir(SCR + "sy2"):
        r = json.load(open(SCR + "sy2/" + f))
        SY2[r["slug"]] = r
    for k, v in SY2.items():
        SY.setdefault(k, v)
    slugs = list(dict.fromkeys(slugs + list(json.load(open(os.path.join(ROOT, "data", "extra_urls.json"))))))
    todo = [s for s in slugs if (not only or s in only) and (only or not os.path.exists(os.path.join(outdir, s + ".json")))]
    print("todo", len(todo), flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        for res in ex.map(run_one, todo):
            json.dump(res, open(os.path.join(outdir, res["slug"] + ".json"), "w"), ensure_ascii=False)
            print(res["slug"], [h["url"].split("/")[2] for h in res["hits"]], flush=True)


if __name__ == "__main__":
    main()
