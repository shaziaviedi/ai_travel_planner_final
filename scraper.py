"""
pull wikivoyage listing-style rows (names + blurbs) into a small csv for the planner.
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

#wikimedia wants a clear user-agent; tweak the string if you publish this widely
HEADERS = {
    "User-Agent": "AITravelPlannerScraper/0.2 (educational project; Python requests)",
    "Accept-Language": "en",
}

BASE = "https://en.wikivoyage.org/wiki/"
RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
OUT_CSV = RAW_DIR / "wikivoyage_raw.csv"

#(canonical city label in the app, one or more english wikivoyage article titles to merge into it)
#los angeles hub page mostly points at districts; we pull core districts so see/do/eat/sleep still populate
DESTINATION_SCRAPES: list[tuple[str, tuple[str, ...]]] = [
    ("Tokyo", ("Tokyo",)),
    ("Kyoto", ("Kyoto",)),
    ("Osaka", ("Osaka",)),
    ("Seoul", ("Seoul",)),
    ("Singapore", ("Singapore",)),
    ("Jakarta", ("Jakarta",)),
    ("Bangkok", ("Bangkok",)),
    ("Bali", ("Bali",)),
    ("Paris", ("Paris",)),
    ("London", ("London",)),
    ("Rome", ("Rome",)),
    ("Barcelona", ("Barcelona",)),
    ("Amsterdam", ("Amsterdam",)),
    ("New York City", ("New York City",)),
    (
        "Los Angeles",
        ("Los Angeles", "Hollywood", "Santa Monica", "Downtown Los Angeles"),
    ),
    ("San Francisco", ("San Francisco",)),
    ("Istanbul", ("Istanbul",)),
    ("Dubai", ("Dubai",)),
    ("Sydney", ("Sydney",)),
    ("Cape Town", ("Cape Town",)),
]

DESTINATIONS: list[str] = [name for name, _ in DESTINATION_SCRAPES]
SECTIONS = ["See", "Do", "Eat", "Drink", "Sleep"]

#when main sleep is thin, follow at most this many district articles for sleep-only scrapes
MAX_DISTRICT_SLEEP_FETCH = 8

#sleep is "weak" if we should try district pages (heuristic)
SLEEP_WEAK_MAX_ROWS = 4
SLEEP_WEAK_AVG_DESC_LEN = 45
SLEEP_WEAK_AVG_DESC_ROWS_CAP = 10

#sleep: lodging-ish tokens in title or start of blurb (not exhaustive, just a nudge)
LODGING_VOCAB = (
    "hotel",
    "motel",
    "hostel",
    "inn",
    "lodge",
    "resort",
    "suite",
    "suites",
    "residence",
    "guesthouse",
    "guest house",
    "ryokan",
    "b&b",
    "b and b",
    "pension",
    "aparthotel",
    "apartment hotel",
    "serviced apartment",
    "capsule",
    "boutique hotel",
    "boutique ",
    "palace hotel",
    "tower hotel",
    "plaza hotel",
    "lodging",
    "accommodation",
)

_SLEEP_GUIDE_OPENERS = re.compile(
    r"^(visitors\s+|the\s+city\s+|many\s+(of\s+)?the\s+|there\s+are\s+|you\s+can\s+|if\s+you\s+|"
    r"for\s+accommodation|accommodation\s+in\s+the|sleeping\s+options|places\s+to\s+stay\s+(can|may)|"
    r"lodging\s+is\s+mostly|hotels\s+tend\s+to|the\s+area\s+has\s+many|options\s+range\s+from)",
    re.I,
)

_INFER_TITLE_BAD_STARTS = (
    "the ",
    "see ",
    "for ",
    "visit ",
    "many ",
    "there ",
    "visitors ",
    "if you",
    "accommodation",
    "hotels in",
    "hotel options",
    "sleeping ",
    "options ",
    "most ",
    "some ",
)

_BAD_WIKI_NS = frozenset(
    {
        "file",
        "template",
        "category",
        "special",
        "help",
        "wikivoyage",
        "mediawiki",
        "user",
    }
)

#wikivoyage boilerplate we never want in a recommendation csv
SKIP_SUBSTRINGS = (
    "please add places",
    "please add listings",
    "please add",
    "individual listings can be found",
    "individual listings",
    "listings can be found in",
    "listings are in",
    "listing can be found",
    "see the district",
    "see the city",
    "for up-to-date listings",
    "this page contains",
    "this article is",
    "help wikivoyage",
    "wikivoyage is not",
    "may be found in",
    "more information on",
    "the main article on",
    "see the main",
    "redirected from",
    "template:",
    "mw:extension",
    "please add places to sleep",
    "please add places",
    "accommodation options in",
    "sleeping options",
    "places to stay can",
    "listings have been moved",
)

#h3-style subsection labels that are not real place names
GENERIC_TITLES = frozenset(
    {
        "budget",
        "mid-range",
        "mid range",
        "splurge",
        "see",
        "do",
        "eat",
        "drink",
        "sleep",
        "get in",
        "get around",
        "understand",
        "stay safe",
        "connect",
        "cope",
        "go next",
        "other districts",
        "learn",
        "work",
        "buy",
    }
)

MIN_TITLE_LEN = 2
MAX_TITLE_LEN = 120
MIN_DESC_LEN = 12


def page_url(title: str) -> str:
    slug = title.replace(" ", "_")
    return BASE + quote(slug, safe="/_:()")


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_edit_markers(text: str) -> str:
    return re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I).strip()


def heading_block(h2: Tag) -> Tag:
    p = h2.parent
    if p and isinstance(p, Tag) and "mw-heading" in (p.get("class") or []):
        return p
    return h2


def is_next_top_section(node: Tag) -> bool:
    if node.name == "h2":
        return True
    if node.name == "div" and "mw-heading2" in (node.get("class") or []):
        return bool(node.find("h2"))
    return False


def main_parser_output(soup: BeautifulSoup) -> Tag | None:
    candidates = soup.find_all("div", class_="mw-parser-output")
    if not candidates:
        return None
    return max(candidates, key=lambda d: len(d.find_all("h2")))


def _in_skipped_container(tag: Tag) -> bool:
    for p in tag.parents:
        tokens = {c.lower() for c in (p.get("class") or []) if isinstance(c, str)}
        if "navbox" in tokens or "vertical-navbox" in tokens:
            return True
        if "toc" in tokens or "toccolours" in tokens:
            return True
        if "infobox" in tokens or "sidebar" in tokens:
            return True
    return False


def _is_vcard(tag: Tag | None) -> bool:
    if not tag or not isinstance(tag, Tag):
        return False
    if tag.name not in ("bdi", "div", "span"):
        return False
    cls = tag.get("class") or []
    return "vcard" in cls


def _parse_vcard(node: Tag) -> tuple[str, str] | None:
    if _in_skipped_container(node):
        return None
    name_el = node.select_one(".listing-name, .fn.org, .fn.org.listing-name")
    note_el = node.select_one(".listing-content, span.note.listing-content, .note.listing-content")
    title = clean_ws(strip_edit_markers(name_el.get_text(" ", strip=True))) if name_el else ""
    desc = clean_ws(strip_edit_markers(note_el.get_text(" ", strip=True))) if note_el else ""
    if not desc:
        full = clean_ws(strip_edit_markers(node.get_text(" ", strip=True)))
        if title and full.lower().startswith(title.lower()):
            desc = clean_ws(full[len(title) :]).lstrip("—:–-• ")
        else:
            desc = full
    if not title:
        return None
    desc = re.sub(r"\(\s*updated[^)]{0,80}\)\s*$", "", desc, flags=re.I).strip()
    return title, desc


def _vcards_between_headings(h2: Tag) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    n: Tag | NavigableString | None = h2
    while True:
        n = n.find_next(["bdi", "div", "span", "h2"])
        if n is None:
            break
        if not isinstance(n, Tag):
            continue
        if n.name == "h2":
            break
        if not _is_vcard(n):
            continue
        parsed = _parse_vcard(n)
        if parsed:
            rows.append(parsed)
    return rows


def _first_bold_or_strong(li: Tag) -> Tag | None:
    for child in li.children:
        if isinstance(child, Tag) and child.name in ("b", "strong"):
            return child
        if isinstance(child, Tag) and child.name in ("a", "i", "span"):
            inner = child.find(["b", "strong"], recursive=False)
            if inner:
                return inner
    return li.find(["b", "strong"])


def _parse_li_listing(li: Tag) -> tuple[str, str] | None:
    if _in_skipped_container(li):
        return None
    b = _first_bold_or_strong(li)
    title = ""
    if b:
        title = clean_ws(strip_edit_markers(b.get_text(" ", strip=True)))
    full = clean_ws(strip_edit_markers(li.get_text(" ", strip=True)))
    if not full or len(full) < 20:
        return None
    if not title and "," in full:
        #lots of wikivoyage bullets look like "name (japanese), rest of the sentence…"
        head, tail = full.split(",", 1)
        head = head.strip()
        tail = tail.strip()
        if 3 <= len(head) <= 90 and not head.lower().startswith(("the ", "see ", "for ", "visit ")):
            title, desc = head, tail
        else:
            return None
    elif title:
        desc = full
        if full.lower().startswith(title.lower()):
            desc = clean_ws(full[len(title) :]).lstrip("—:–-• ")
    else:
        return None
    if not title or len(title) > MAX_TITLE_LEN:
        return None
    if not desc:
        return None
    return title, desc


def _uls_from_sibling(sib: Tag) -> list[Tag]:
    #find_all skips the node itself, so a bare <ul> sibling would vanish without this
    out: list[Tag] = []
    if sib.name == "ul":
        out.append(sib)
    out.extend(sib.find_all("ul"))
    return out


def _fallback_ul_between_section(h2: Tag) -> list[tuple[str, str]]:
    #some city pages skip the listing template; grab plain wikitext bullets instead
    start = heading_block(h2)
    out: list[tuple[str, str]] = []
    for sib in start.next_siblings:
        if isinstance(sib, Tag) and is_next_top_section(sib):
            break
        if not isinstance(sib, Tag):
            continue
        for ul in _uls_from_sibling(sib):
            if ul.find_parent("ul"):
                continue
            if _in_skipped_container(ul):
                continue
            cls = " ".join(ul.get("class") or []).lower()
            if "gallery" in cls:
                continue
            for li in ul.find_all("li", recursive=False):
                parsed = _parse_li_listing(li)
                if parsed:
                    out.append(parsed)
    return out


def _has_boilerplate(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in SKIP_SUBSTRINGS)


def _is_generic_title(title: str) -> bool:
    t = strip_edit_markers(title).lower()
    t = re.sub(r"[^a-z0-9\s-]", "", t).strip()
    return t in GENERIC_TITLES or len(t) <= 1


def _row_is_useful(title: str, desc: str) -> bool:
    title = strip_edit_markers(title)
    desc = strip_edit_markers(desc)
    if not title:
        return False
    if len(title) < MIN_TITLE_LEN or len(title) > MAX_TITLE_LEN:
        return False
    if _is_generic_title(title):
        return False
    if len(desc) < MIN_DESC_LEN:
        return False
    if _has_boilerplate(title) or _has_boilerplate(desc):
        return False
    if desc.lower() == title.lower():
        return False
    #drop one-liners that are basically a label with almost no detail
    if len(desc.split()) < 3 and "¥" not in desc and "$" not in desc and "http" not in desc.lower():
        return False
    return True


def _infer_sleep_title(title: str, desc: str) -> str:
    #wikivoyage sometimes leaves sleep bullets with no bold name; grab a short head phrase
    t = clean_ws(strip_edit_markers(title))
    if len(t) >= MIN_TITLE_LEN:
        return t
    d = clean_ws(strip_edit_markers(desc))
    if len(d) < 24:
        return t

    def _bad_start(chunk: str) -> bool:
        low = chunk.lower().strip()
        return any(low.startswith(p) for p in _INFER_TITLE_BAD_STARTS)

    for sep in (".", "—", "–", "\n"):
        if sep in d[:180]:
            chunk = d.split(sep, 1)[0].strip()
            if MIN_TITLE_LEN <= len(chunk) <= MAX_TITLE_LEN and not _bad_start(chunk):
                return chunk
    m = re.match(r"^([^,]{5,80}),\s", d)
    if m:
        chunk = m.group(1).strip()
        if MIN_TITLE_LEN <= len(chunk) <= MAX_TITLE_LEN and not _bad_start(chunk):
            return chunk
    words = d.split()
    if len(words) >= 3:
        head = " ".join(words[:5]).strip(" ,;—")
        if MIN_TITLE_LEN <= len(head) <= MAX_TITLE_LEN and head[:1].isalpha() and head[0].isupper():
            if not _bad_start(head):
                return head
    return t


def _sleep_practical_signal(desc: str) -> bool:
    d = desc.lower()
    return any(
        x in d
        for x in (
            "http",
            "www.",
            ".com",
            "tel",
            "phone",
            "+",
            "/night",
            " per night",
            " a night",
            " usd",
            "$",
            "¥",
            "€",
            "฿",
            "★",
            " stars",
            " star ",
        )
    )


def _sleep_lodging_vocab_signal(title: str, desc: str) -> bool:
    blob = (title + " " + desc[:240]).lower()
    return any(tok in blob for tok in LODGING_VOCAB)


def _sleep_is_editorial_summary(title: str, desc: str) -> bool:
    d = desc.strip()
    lt = len(title.strip())
    ld = len(d)
    if ld > 520 and lt < 22:
        return True
    if ld > 720:
        return True
    if _SLEEP_GUIDE_OPENERS.match(d):
        return True
    if lt < 14 and ld > 220 and not _sleep_lodging_vocab_signal(title, desc):
        return True
    return False


def _sleep_likely_place_listing(title: str, desc: str) -> bool:
    if _sleep_is_editorial_summary(title, desc):
        return False
    if _has_boilerplate(title) or _has_boilerplate(desc):
        return False
    words = len(desc.split())
    if words < 5:
        return False
    if _sleep_lodging_vocab_signal(title, desc):
        return True
    if _sleep_practical_signal(desc) and len(title.strip()) >= 5:
        return True
    return False


def _sleep_usable_for_stay_raw(likely: bool, title: str, desc: str) -> bool:
    #scraper-side gate; build_dataset still applies content_score + stay signals
    if not likely:
        return False
    if len(desc.strip()) < 28:
        return False
    return True


def _wiki_title_from_href(href: str) -> str | None:
    if not href or not isinstance(href, str):
        return None
    href = href.strip()
    if href.startswith("#"):
        return None
    if href.startswith("//"):
        href = "https:" + href
    if "wikivoyage.org/wiki/" in href:
        path = href.split("wikivoyage.org/wiki/", 1)[1]
    elif href.startswith("/wiki/"):
        path = href.split("/wiki/", 1)[1]
    else:
        return None
    path = path.split("#")[0].split("?")[0]
    if not path:
        return None
    parts = path.split("/")
    head = unquote(parts[0].replace("_", " "))
    if ":" in head:
        ns = head.split(":", 1)[0].strip().lower()
        if ns in _BAD_WIKI_NS:
            return None
    title = "/".join(unquote(p).replace("_", " ") for p in parts)
    t = title.strip()
    return t or None


def sleep_rows_weak(rows: list[dict[str, str]]) -> bool:
    sleep = [r for r in rows if r.get("section") == "Sleep"]
    likely_sleep = [r for r in sleep if int(str(r.get("likely_place_listing", "0") or "0")) == 1]
    nl = len(likely_sleep)
    if nl < SLEEP_WEAK_MAX_ROWS:
        return True
    if nl < SLEEP_WEAK_AVG_DESC_ROWS_CAP:
        avg = sum(len(r.get("description", "")) for r in likely_sleep) / max(1, nl)
        if avg < SLEEP_WEAK_AVG_DESC_LEN:
            return True
    return False


def _districts_h2(content: Tag) -> Tag | None:
    h = content.find("h2", id="Districts")
    if h:
        return h
    for h in content.find_all("h2"):
        if clean_ws(strip_edit_markers(h.get_text(" ", strip=True))) == "Districts":
            return h
    return None


def _districts_section_wiki_links(h2: Tag) -> list[str]:
    out: list[str] = []
    start = heading_block(h2)
    for sib in start.next_siblings:
        if isinstance(sib, Tag) and is_next_top_section(sib):
            break
        if not isinstance(sib, Tag):
            continue
        for a in sib.find_all("a", href=True):
            t = _wiki_title_from_href(str(a.get("href") or ""))
            if t:
                out.append(t)
    return out


def _subpage_titles_under_main(content: Tag, main_title: str) -> list[str]:
    slug_prefix = "/wiki/" + main_title.replace(" ", "_") + "/"
    seen: set[str] = set()
    out: list[str] = []
    for a in content.find_all("a", href=True):
        href = str(a.get("href") or "")
        if not href.startswith(slug_prefix):
            continue
        t = _wiki_title_from_href(href)
        if not t or t == main_title:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def discover_district_titles(main_title: str, soup: BeautifulSoup) -> list[str]:
    #districts h2 links first, then any City/Subpage hrefs in the parser output
    content = main_parser_output(soup)
    if not content:
        return []
    ordered: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        if not t or t in seen:
            return
        seen.add(t)
        ordered.append(t)

    h2d = _districts_h2(content)
    if h2d:
        for t in _districts_section_wiki_links(h2d):
            add(t)
    for t in _subpage_titles_under_main(content, main_title):
        add(t)
    return ordered


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, str]] = []
    for r in rows:
        key = (
            str(r.get("destination", "")).strip().casefold(),
            str(r.get("section", "")).strip(),
            str(r.get("title", "")).strip().casefold(),
            str(r.get("description", ""))[:200].strip().casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def extract_section_rows(
    content: Tag,
    source_url: str,
    destination: str,
    section_id: str,
    *,
    source_page_title: str,
    page_type: str,
) -> list[dict[str, str]]:
    h2 = content.find("h2", id=section_id)
    if not h2:
        h2 = next(
            (h for h in content.find_all("h2") if h.get_text(strip=True) == section_id),
            None,
        )
    if not h2:
        return []

    pairs = _vcards_between_headings(h2)
    if not pairs:
        pairs = _fallback_ul_between_section(h2)

    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for title, desc in pairs:
        title = strip_edit_markers(clean_ws(title))
        desc = strip_edit_markers(clean_ws(desc))
        if section_id == "Sleep":
            title = _infer_sleep_title(title, desc)
        if not title or len(title.strip()) < MIN_TITLE_LEN:
            continue
        if not _row_is_useful(title, desc):
            continue
        likely_flag = 0
        usable_flag = 0
        if section_id == "Sleep":
            likely_b = _sleep_likely_place_listing(title, desc)
            likely_flag = 1 if likely_b else 0
            usable_flag = 1 if _sleep_usable_for_stay_raw(likely_b, title, desc) else 0
        key = (title.lower(), desc[:160].lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "destination": destination,
                "source_page_title": source_page_title,
                "page_type": page_type,
                "section": section_id,
                "title": title,
                "description": desc,
                "likely_place_listing": str(likely_flag),
                "usable_for_stay": str(usable_flag),
                "source_url": source_url,
            }
        )
    return rows


def extract_page(
    html: str,
    source_url: str,
    destination: str,
    *,
    source_page_title: str,
    page_type: str,
    sections: list[str] | None = None,
) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    content = main_parser_output(soup)
    if not content:
        return []
    out: list[dict[str, str]] = []
    sec_list = sections if sections is not None else SECTIONS
    for sec in sec_list:
        out.extend(
            extract_section_rows(
                content,
                source_url,
                destination,
                sec,
                source_page_title=source_page_title,
                page_type=page_type,
            )
        )
    return out


def scrape_all() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, str]] = []

    for canonical, wiki_titles in DESTINATION_SCRAPES:
        if not wiki_titles:
            continue
        primary = wiki_titles[0]
        extras = list(wiki_titles[1:])
        extras_cf = {x.casefold() for x in extras}

        time.sleep(1.0)
        primary_url = page_url(primary)
        primary_html = fetch_html(primary_url)
        primary_soup = BeautifulSoup(primary_html, "lxml")

        primary_rows = extract_page(
            primary_html,
            primary_url,
            canonical,
            source_page_title=primary,
            page_type="main_city_page",
        )
        all_rows.extend(primary_rows)

        if sleep_rows_weak(primary_rows):
            candidates = discover_district_titles(primary, primary_soup)
            fetched = 0
            for dt in candidates:
                if dt.casefold() == primary.casefold():
                    continue
                if dt.casefold() in extras_cf:
                    continue
                if fetched >= MAX_DISTRICT_SLEEP_FETCH:
                    break
                durl = page_url(dt)
                time.sleep(1.0)
                try:
                    dhtml = fetch_html(durl)
                except requests.RequestException:
                    continue
                all_rows.extend(
                    extract_page(
                        dhtml,
                        durl,
                        canonical,
                        source_page_title=dt,
                        page_type="district_page",
                        sections=["Sleep"],
                    )
                )
                fetched += 1

        for ex in extras:
            time.sleep(1.0)
            ex_url = page_url(ex)
            try:
                ex_html = fetch_html(ex_url)
            except requests.RequestException:
                continue
            all_rows.extend(
                extract_page(
                    ex_html,
                    ex_url,
                    canonical,
                    source_page_title=ex,
                    page_type="district_page",
                )
            )

    all_rows = dedupe_rows(all_rows)

    fieldnames = [
        "destination",
        "source_page_title",
        "page_type",
        "section",
        "title",
        "description",
        "likely_place_listing",
        "usable_for_stay",
        "source_url",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    print("supported destinations (this scrape):")
    for i, name in enumerate(DESTINATIONS, start=1):
        print(f"  {i:2}. {name}")
    print(f"total: {len(DESTINATIONS)}")

    return OUT_CSV


if __name__ == "__main__":
    path = scrape_all()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
