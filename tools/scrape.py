#!/usr/bin/env python3
"""Fetch project pages and extract images, coordinates and fact snippets.

Usage: scrape.py URL [URL ...]
Prints a compact JSON report per URL so the data can be reviewed by hand
before it goes into data/projects.json.
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

FACT_RE = re.compile(
    r"(\d+\s*(?:acres?|towers?|units?|floors?|storeys?|stories)\b|"
    r"\b(?:B|G|S|P|\d+B)\+(?:G|\d)[\w+]*|RERA|PRM/KA|possession|"
    r"\d[\d,]*\s*(?:sq\.?\s*ft|sqft))", re.I)
MASTER_RE = re.compile(r"master|site[-_ ]?plan|layout|sitemap|site[-_ ]?layout", re.I)
SKIP_IMG = re.compile(r"logo|icon|sprite|favicon|avatar|flag|pixel|banner-?ad|whatsapp|"
                      r"facebook|instagram|twitter|youtube|qr|rera-?qr|\.svg|\.gif|blank|"
                      r"loader|arrow|thumb|cursor|payment|badge", re.I)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get_content_charset() or "utf-8"
        return r.geturl(), raw.decode(ctype, errors="ignore")


def absolutize(base, u):
    u = html.unescape(u.strip())
    if u.startswith("//"):
        return "https:" + u
    return urllib.parse.urljoin(base, u)


def extract(url):
    final, h = fetch(url)
    out = {"url": url, "final_url": final, "len": len(h)}
    t = re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I)
    out["title"] = html.unescape(t.group(1).strip())[:140] if t else None
    og = re.findall(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', h, re.I)
    og += re.findall(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)["\']', h, re.I)
    out["og_image"] = [absolutize(final, x) for x in dict.fromkeys(og)][:2]

    imgs = []
    for m in re.finditer(r'<img[^>]+>', h, re.I):
        tag = m.group(0)
        src = re.search(r'(?:data-src|data-lazy-src|data-original|src)=["\']([^"\']+)["\']', tag, re.I)
        if not src:
            continue
        alt = re.search(r'alt=["\']([^"\']*)["\']', tag, re.I)
        u = absolutize(final, src.group(1))
        if u.startswith("data:"):
            continue
        imgs.append((u, html.unescape(alt.group(1)) if alt else ""))
    # background images and raw image URLs in inline css / json
    for u in re.findall(r'url\(["\']?([^)"\']+\.(?:jpe?g|png|webp))', h, re.I):
        imgs.append((absolutize(final, u), ""))
    seen, master, gallery = set(), [], []
    for u, alt in imgs:
        if u in seen or SKIP_IMG.search(u):
            continue
        seen.add(u)
        if MASTER_RE.search(u) or MASTER_RE.search(alt):
            master.append((u, alt[:60]))
        elif re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I):
            gallery.append((u, alt[:60]))
    out["master_plan_imgs"] = master[:6]
    out["gallery_imgs"] = gallery[:8]

    # coordinates: google maps embed / links / json-ld
    coords = []
    for m in re.finditer(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)", h):
        coords.append((float(m.group(2)), float(m.group(1))))
    for m in re.finditer(r"@(-?\d{1,2}\.\d{3,}),(-?\d{2,3}\.\d{3,})", h):
        coords.append((float(m.group(1)), float(m.group(2))))
    for m in re.finditer(r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?\s*,\s*"longitude"\s*:\s*"?(-?\d+\.\d+)', h):
        coords.append((float(m.group(1)), float(m.group(2))))
    for m in re.finditer(r"[?&]q=(-?\d{1,2}\.\d{3,}),(-?\d{2,3}\.\d{3,})", h):
        coords.append((float(m.group(1)), float(m.group(2))))
    out["coords"] = [c for c in dict.fromkeys(coords) if 12.5 < c[0] < 13.6 and 77.2 < c[1] < 78.0][:4]

    # visible text -> fact snippets
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", "\n", body)
    body = html.unescape(body)
    lines = [re.sub(r"\s+", " ", l).strip() for l in body.split("\n")]
    facts = []
    for l in lines:
        if 6 < len(l) < 260 and FACT_RE.search(l) and l not in facts:
            facts.append(l)
    out["facts"] = facts[:40]
    return out


if __name__ == "__main__":
    for u in sys.argv[1:]:
        try:
            print(json.dumps(extract(u), indent=1, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"url": u, "error": str(e)}))
