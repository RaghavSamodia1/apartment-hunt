# Apartment hunt — Yelahanka & north Bengaluru

Interactive map + shortlist tool for 2 & 3 BHK apartments up to ₹2.5 Cr in and around Yelahanka.

## Open it

Double-click `index.html` (needs internet for the map tiles, Leaflet and the project photos).
Use **one** way of opening it consistently — your shortlist lives in that browser/origin's local storage
(`file://` and `http://localhost` are separate). Use **Export** to back up decisions or move them to another device.

If you prefer a local server: `python3 -m http.server 8765` in this folder, then open http://localhost:8765.

## What's in it

* **Explore** – map (price pins, clusters, street / light / satellite layers) + cards. Click a pin or card for the detail
  drawer: photos, master plan, floors / towers / acres / homes, price by unit, connectivity, RERA, Google Maps links, notes.
* **Triage** – one project at a time, `←` reject, `→` shortlist, `↓` skip, `Enter` details.
* **Shortlist** / **Compare** – side-by-side table of everything you shortlisted.
* Filters: BHK, status, budget, distance from Yelahanka, minimum floors, area, decision, "floors known", "has master plan".
  **+ Budget segment** adds ~155 smaller / cheaper projects that only have basic data.
* Keyboard: `S` shortlist, `X` reject, `↑/↓` move through the list.

## Data

`data/projects.js` is generated — don't edit it by hand. Sources, in order of trust:

1. Squareyards project pages – price, size, units, acres, coordinates (JSON-LD), photos, master plans, RERA.
2. PropNewz / Housiey / PropTimes / PropZilla pages – towers & floors (voted across sources).
3. `data/manual_*.json` – floors / towers looked up per project by web search and cross-checked; each entry records
   its source and a confidence (`high` = two or more sources agree, `medium` = listing pages only, `low` = sources conflict).

Floors is the number above the ground floor (2B+G+14 → 14). Phased townships (Sobha City, Bhartiya City, L&T Raintree,
Godrej Ananda …) mix phases, so those are flagged low-confidence.

Pins were cross-checked against OpenStreetMap; projects whose two sources agree within ~800 m are marked "cross-checked".

### Refreshing / extending

```
tools/sy_parse.py      # parse squareyards project pages from an index of slugs/ids
tools/sy_parse2.py     # 2nd pass: JSON-LD geo + categorised full-size images for the curated list
tools/enrich.py        # try PropNewz / Housiey / PropTimes / PropZilla pages for floors, towers, master plans
tools/geocheck.py      # OpenStreetMap cross-check of map pins
tools/build_data.py    # merge everything + data/manual_*.json → data/projects.js
```

Working files (raw scrapes) are kept outside this folder in the session scratchpad; re-run the scripts to regenerate them.
`data/core_slugs.json` / `ext_slugs.json` list which squareyards projects are in the core / budget-segment sets;
`data/extra_urls.json` holds projects whose squareyards URL has a different pattern.

## Caveats

* Prices are portal asking prices (before GST / registration). Ready-to-move projects show launch-era ranges;
  resale prices differ. "Price on request" = no public price.
* Always verify the RERA registration on https://rera.karnataka.gov.in before paying a token amount.
* Photos are hot-linked from the listing sites and may disappear.
