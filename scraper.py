"""
pull wikivoyage listing-style rows (names + blurbs) into a small csv for the planner.
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import quote

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

DESTINATIONS = ["Tokyo", "Kyoto", "Osaka", "Seoul", "Singapore"]
SECTIONS = ["See", "Do", "Eat", "Drink", "Sleep"]

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


def extract_section_rows(
    content: Tag,
    source_url: str,
    destination: str,
    section_id: str,
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
        if not _row_is_useful(title, desc):
            continue
        key = (title.lower(), desc[:160].lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "destination": destination,
                "section": section_id,
                "title": title,
                "description": desc,
                "source_url": source_url,
            }
        )
    return rows


def extract_page(html: str, source_url: str, destination: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    content = main_parser_output(soup)
    if not content:
        return []
    out: list[dict[str, str]] = []
    for sec in SECTIONS:
        out.extend(extract_section_rows(content, source_url, destination, sec))
    return out


def scrape_all() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, str]] = []

    for dest in DESTINATIONS:
        url = page_url(dest)
        time.sleep(1.0)
        html = fetch_html(url)
        all_rows.extend(extract_page(html, url, dest))

    fieldnames = ["destination", "section", "title", "description", "source_url"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    return OUT_CSV


if __name__ == "__main__":
    path = scrape_all()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
