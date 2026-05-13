"""streamlit shell for the travel planner."""

from __future__ import annotations

import hashlib
import html
import json
import math

import streamlit as st

from planner import (
    build_checklist,
    clean_description_for_display,
    get_recommendations,
    supported_destinations,
)

#streamlit reruns the whole script; keep the last plan around so widgets feel stable
if "last_plan" not in st.session_state:
    st.session_state["last_plan"] = None


def inject_styles() -> None:
    #soft palette + light cards; keeps streamlit widgets readable
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&display=swap');
        html, body, [class*="css"] {
            font-family: "DM Sans", system-ui, sans-serif;
            color: #3a4556;
        }
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(165deg, #f7f3ef 0%, #eef3f8 42%, #f2f6fb 100%);
        }
        [data-testid="stAppViewContainer"] > .main {
            background: transparent;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1080px;
        }
        .hero-wrap {
            position: relative;
            overflow: hidden;
            border-radius: 22px;
            padding: 2rem 2rem 1.85rem;
            margin: 0 0 1.75rem;
            background: linear-gradient(120deg, #e4edf6 0%, #ebe4f2 38%, #dce9ea 100%);
            border: 1px solid rgba(255, 255, 255, 0.65);
            box-shadow: 0 20px 50px rgba(120, 130, 160, 0.12);
        }
        .hero-wrap::after {
            content: "";
            position: absolute;
            inset: -40% -20% auto auto;
            width: 55%;
            height: 120%;
            background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.55), transparent 62%);
            pointer-events: none;
        }
        .hero-inner { position: relative; z-index: 1; max-width: 46rem; }
        .hero-kicker {
            display: inline-block;
            font-size: 0.72rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #6b7c93;
            margin-bottom: 0.55rem;
            font-weight: 600;
        }
        .hero-wrap h1 {
            margin: 0;
            font-size: clamp(1.85rem, 3.2vw, 2.45rem);
            font-weight: 600;
            letter-spacing: -0.035em;
            color: #2c3544;
            line-height: 1.12;
        }
        .hero-wrap p {
            margin: 0.75rem 0 0;
            color: #5a6a7d;
            font-size: 1.05rem;
            line-height: 1.55;
            font-weight: 400;
            max-width: 38rem;
        }
        div[data-testid="stSidebar"] {
            background: linear-gradient(185deg, #fbfcfe 0%, #f3f1fa 100%);
            border-right: 1px solid rgba(180, 190, 210, 0.35);
        }
        div[data-testid="stSidebar"] .block-container {
            padding-top: 1.5rem;
        }
        div[data-testid="stSidebar"] h3 {
            font-size: 0.78rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #7a8799;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stSidebar"] label, div[data-testid="stSidebar"] span {
            color: #4a5563;
        }
        div[data-testid="stSidebar"] .stTextInput input,
        div[data-testid="stSidebar"] .stNumberInput input,
        div[data-testid="stSidebar"] textarea,
        div[data-testid="stSidebar"] [data-baseweb="select"] > div {
            border-radius: 12px !important;
            border-color: rgba(160, 175, 195, 0.45) !important;
            background: rgba(255, 255, 255, 0.92) !important;
        }
        div[data-testid="stSidebar"] .stButton > button {
            border-radius: 14px;
            padding: 0.65rem 1rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            border: none;
            background: linear-gradient(120deg, #7b9eb8 0%, #9eb6c9 55%, #b8c9d8 100%);
            color: #ffffff;
            box-shadow: 0 10px 28px rgba(110, 140, 170, 0.28);
        }
        div[data-testid="stSidebar"] .stButton > button:hover {
            filter: brightness(1.03);
            box-shadow: 0 12px 32px rgba(110, 140, 170, 0.34);
        }
        .section-title {
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #323c4d;
            margin: 0.25rem 0 1rem;
        }
        .trip-meta-card {
            display: flex;
            flex-wrap: wrap;
            gap: 1.25rem 2rem;
            padding: 1.1rem 1.25rem;
            margin: 0 0 1.35rem;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(210, 218, 232, 0.65);
            box-shadow: 0 12px 36px rgba(90, 110, 140, 0.07);
        }
        .trip-meta-block span {
            display: block;
            font-size: 0.68rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #8b98a8;
            margin-bottom: 0.35rem;
            font-weight: 600;
        }
        .trip-meta-block strong {
            font-size: 1.02rem;
            color: #2f3847;
            font-weight: 600;
        }
        .list-card {
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid rgba(210, 218, 232, 0.6);
            padding: 1rem 1.15rem 0.85rem;
            box-shadow: 0 10px 30px rgba(90, 110, 140, 0.06);
        }
        ul.dreamy-list {
            margin: 0;
            padding-left: 1.15rem;
            color: #4a5568;
            line-height: 1.55;
        }
        ul.dreamy-list li { margin-bottom: 0.45rem; }
        .checklist-page-head {
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #323c4d;
            margin: 0 0 0.25rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px !important;
            background: rgba(255, 255, 255, 0.78) !important;
            border: 1px solid rgba(210, 218, 232, 0.6) !important;
            box-shadow: 0 10px 30px rgba(90, 110, 140, 0.06);
            padding: 0.35rem 0.5rem 0.65rem !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"],
        section.main [data-testid="stCheckbox"] {
            margin-bottom: 0.4rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"] label,
        section.main [data-testid="stCheckbox"] label {
            display: flex;
            align-items: flex-start;
            gap: 0.55rem;
            padding: 0.5rem 0.65rem;
            border-radius: 12px;
            border: 1px solid rgba(215, 224, 238, 0.75);
            background: rgba(255, 255, 255, 0.88);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"] label:hover,
        section.main [data-testid="stCheckbox"] label:hover {
            border-color: rgba(150, 170, 200, 0.55);
            box-shadow: 0 4px 16px rgba(95, 115, 145, 0.08);
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"] label p,
        section.main [data-testid="stCheckbox"] label p {
            margin: 0;
            font-size: 0.94rem;
            line-height: 1.45;
            color: #4a5568;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"]:has(input:checked) label,
        section.main [data-testid="stCheckbox"]:has(input:checked) label {
            border-color: rgba(123, 158, 184, 0.55);
            background: rgba(240, 248, 252, 0.95);
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"]:has(input:checked) label p,
        section.main [data-testid="stCheckbox"]:has(input:checked) label p {
            color: #3d4d63;
            text-decoration: line-through;
            text-decoration-thickness: 1px;
            text-decoration-color: rgba(100, 120, 140, 0.45);
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"],
        section.main [data-testid="stVerticalBlock"] [data-testid="stProgress"] {
            margin-top: 0.65rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"] > div,
        section.main [data-testid="stProgress"] > div {
            border-radius: 999px;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            background: rgba(255, 255, 255, 0.55);
            padding: 0.35rem 0.4rem;
            border-radius: 14px;
            border: 1px solid rgba(210, 218, 232, 0.55);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 11px;
            padding: 0.45rem 0.85rem;
            font-weight: 500;
            color: #5c6b7d;
        }
        .stTabs [aria-selected="true"] {
            background: rgba(255, 255, 255, 0.95) !important;
            color: #3d4d63 !important;
            box-shadow: 0 6px 18px rgba(100, 120, 150, 0.1);
        }
        .itinerary-stack {
            display: flex;
            flex-direction: column;
            gap: 1.15rem;
        }
        .day-card {
            border-radius: 20px;
            border: 1px solid rgba(200, 210, 228, 0.9);
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 14px 40px rgba(75, 95, 130, 0.09);
            overflow: hidden;
        }
        .day-card__top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.7rem 1.15rem;
            background: linear-gradient(105deg, rgba(228, 236, 248, 0.95) 0%, rgba(240, 234, 252, 0.88) 100%);
            border-bottom: 1px solid rgba(210, 218, 232, 0.7);
        }
        .day-chip {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #3d4f66;
        }
        .day-card__body {
            padding: 1rem 1.2rem 1.15rem;
        }
        .it-block {
            padding-bottom: 1rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid rgba(226, 232, 242, 0.95);
        }
        .it-block:last-child {
            padding-bottom: 0;
            margin-bottom: 0;
            border-bottom: none;
        }
        .it-block__eyebrow {
            display: block;
            font-size: 0.68rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            font-weight: 700;
            color: #64748b;
            margin-bottom: 0.4rem;
        }
        .it-block__title {
            margin: 0 0 0.35rem;
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: -0.02em;
            color: #0f172a;
            line-height: 1.28;
            word-wrap: break-word;
            overflow-wrap: anywhere;
        }
        .it-block__desc {
            margin: 0;
            font-size: 0.9rem;
            line-height: 1.55;
            color: #475569;
            word-wrap: break-word;
            overflow-wrap: anywhere;
            display: -webkit-box;
            -webkit-line-clamp: 5;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        ul.day-card__acts {
            margin: 0;
            padding: 0.85rem 1.05rem 1rem 1.25rem;
            color: #4d5868;
            line-height: 1.55;
            font-size: 0.96rem;
        }
        ul.day-card__acts li { margin-bottom: 0.55rem; }
        ul.day-card__acts li:last-child { margin-bottom: 0; }
        .stay-stack {
            display: flex;
            flex-direction: column;
            gap: 1.1rem;
        }
        .stay-card {
            border-radius: 20px;
            border: 1px solid rgba(210, 200, 220, 0.65);
            background: linear-gradient(155deg, rgba(255, 253, 250, 0.98) 0%, rgba(248, 246, 255, 0.92) 55%, rgba(241, 248, 255, 0.88) 100%);
            box-shadow: 0 12px 32px rgba(95, 85, 120, 0.08);
            padding: 1.05rem 1.2rem 1.1rem;
            border-left: 4px solid rgba(130, 150, 190, 0.45);
        }
        .stay-card__head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }
        .stay-card__kicker {
            font-size: 0.65rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            font-weight: 700;
            color: #7c8496;
        }
        .stay-band-pill {
            flex-shrink: 0;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            padding: 0.3rem 0.6rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.85);
            border: 1px solid rgba(190, 200, 220, 0.75);
            color: #4a5568;
        }
        .stay-card__title {
            margin: 0;
            font-weight: 600;
            color: #1e293b;
            font-size: 1.06rem;
            line-height: 1.3;
            letter-spacing: -0.02em;
            word-wrap: break-word;
            overflow-wrap: anywhere;
        }
        .stay-card__desc {
            margin: 0.5rem 0 0;
            color: #526077;
            font-size: 0.88rem;
            line-height: 1.55;
            word-wrap: break-word;
            overflow-wrap: anywhere;
            display: -webkit-box;
            -webkit-line-clamp: 5;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .packing-page-head {
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #323c4d;
            margin: 0 0 0.25rem;
        }
        .packing-group-head {
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
            color: #64748b;
            margin: 0.95rem 0 0.4rem;
        }
        .packing-group-head--first {
            margin-top: 0.35rem;
        }
        .budget-card {
            border-radius: 20px;
            border: 1px solid rgba(200, 214, 228, 0.85);
            background: rgba(255, 255, 255, 0.92);
            padding: 1rem 1.15rem 1.1rem;
            box-shadow: 0 12px 32px rgba(95, 115, 145, 0.08);
            max-width: 560px;
        }
        .budget-card--breakdown {
            max-width: 640px;
        }
        .budget-page-head {
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #323c4d;
            margin: 0 0 0.25rem;
        }
        .budget-head {
            font-size: 0.65rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #7a8799;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }
        .budget-lede {
            margin: 0 0 0.65rem;
            font-size: 0.93rem;
            font-weight: 500;
            color: #475569;
            line-height: 1.5;
        }
        .budget-table-wrap {
            border-radius: 14px;
            border: 1px solid rgba(215, 224, 238, 0.95);
            overflow: hidden;
            margin: 0.5rem 0 0.85rem;
            background: rgba(248, 250, 252, 0.65);
        }
        table.budget-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }
        table.budget-table th {
            text-align: left;
            font-size: 0.65rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
            color: #64748b;
            padding: 0.55rem 0.75rem;
            background: rgba(255, 255, 255, 0.9);
            border-bottom: 1px solid rgba(220, 228, 238, 0.95);
        }
        table.budget-table th:last-child,
        table.budget-table td:last-child {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        table.budget-table td {
            padding: 0.5rem 0.75rem;
            color: #334155;
            border-bottom: 1px solid rgba(230, 236, 244, 0.9);
        }
        table.budget-table tbody tr:nth-child(even) td {
            background: rgba(255, 255, 255, 0.45);
        }
        table.budget-table tbody tr:last-child td {
            border-bottom: none;
        }
        table.budget-table td.budget-cat {
            font-weight: 500;
            color: #475569;
        }
        table.budget-table td.budget-amt {
            font-weight: 600;
            color: #1e293b;
        }
        table.budget-table tfoot td {
            padding: 0.65rem 0.75rem;
            font-weight: 700;
            background: linear-gradient(120deg, rgba(232, 240, 248, 0.98), rgba(245, 238, 252, 0.9));
            border-top: 2px solid rgba(190, 205, 225, 0.55);
            border-bottom: none;
        }
        table.budget-table tfoot td.budget-cat {
            font-size: 0.72rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #4a5d72;
        }
        table.budget-table tfoot td.budget-amt {
            font-size: 1.05rem;
            color: #0f172a;
        }
        .budget-tips {
            margin-top: 0.85rem;
            padding: 0.65rem 0.75rem;
            border-radius: 12px;
            background: rgba(241, 248, 255, 0.55);
            border: 1px solid rgba(200, 218, 238, 0.65);
        }
        .budget-tips__title {
            margin: 0 0 0.4rem;
            font-size: 0.65rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-weight: 700;
            color: #64748b;
        }
        .budget-tips ul {
            margin: 0;
            padding-left: 1.05rem;
            color: #526077;
            font-size: 0.84rem;
            line-height: 1.5;
        }
        .budget-tips li { margin-bottom: 0.3rem; }
        .budget-tip-em { font-weight: 600; color: #3d4d63; }
        ul.budget-bits {
            margin: 0;
            padding-left: 1.1rem;
            color: #5a6675;
            font-size: 0.88rem;
            line-height: 1.45;
        }
        ul.budget-bits li { margin-bottom: 0.25rem; }
        .budget-foot {
            font-size: 0.76rem;
            color: #7a8799;
            margin: 0.65rem 0 0;
            line-height: 1.45;
        }
        .debug-section-head {
            font-size: 1.02rem;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #475569;
            margin: 0.35rem 0 0.25rem;
        }
        .debug-block-title {
            font-size: 0.72rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            font-weight: 700;
            color: #64748b;
            margin: 0.85rem 0 0.35rem;
        }
        div[data-testid="stMarkdownContainer"] p {
            line-height: 1.5;
        }
        div[data-testid="stAlert"] {
            background: rgba(255, 255, 255, 0.85) !important;
            border: 1px solid rgba(200, 214, 228, 0.75) !important;
            border-radius: 16px !important;
            color: #3d4d63 !important;
            box-shadow: 0 8px 24px rgba(95, 115, 145, 0.06);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _blankish(s: object) -> bool:
    #catch float nan and string "nan" so nothing ugly leaks into html
    if s is None:
        return True
    if isinstance(s, float) and (math.isnan(s) or math.isinf(s)):
        return True
    t = str(s).strip()
    return not t or t.casefold() in ("nan", "none", "null", "<na>")


def _h(s: str) -> str:
    return html.escape(s, quote=True)


def _ui_title(s: object, *, fallback: str) -> str:
    if _blankish(s):
        return fallback
    t = " ".join(str(s).split())
    if len(t) > 88:
        t = t[:85].rstrip(" ,;—") + "…"
    return t


def _ui_blurb(s: object) -> str:
    if _blankish(s):
        return ""
    return clean_description_for_display(str(s).strip(), soft_target=190, hard_max=280)


def _checklist_widget_fingerprint(plan: dict, items: list[str]) -> str:
    #stable id so checkbox keys reset when the user builds a different trip
    blob = json.dumps(
        {
            "b": plan.get("budget"),
            "d": plan.get("destination"),
            "items": items,
            "n": plan.get("num_days"),
            "v": plan.get("trip_vibe"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:18]


PACKING_GROUP_ORDER = ("essentials", "for_this_trip")
PACKING_GROUP_LABELS = {
    "essentials": "essentials",
    "for_this_trip": "for this trip",
}


def _normalize_packing(raw: object) -> dict[str, list[str]]:
    #planner returns grouped dict; old session_state may still have a flat list
    if isinstance(raw, dict):
        out: dict[str, list[str]] = {}
        for key in PACKING_GROUP_ORDER:
            if key not in raw:
                continue
            vals = raw[key]
            if not isinstance(vals, list):
                continue
            cleaned = [str(x).strip() for x in vals if not _blankish(x)]
            if cleaned:
                out[key] = cleaned
        return out
    if isinstance(raw, list):
        cleaned = [str(x).strip() for x in raw if not _blankish(x)]
        return {"essentials": cleaned} if cleaned else {}
    return {}


def _packing_widget_fingerprint(plan: dict, groups: dict[str, list[str]]) -> str:
    ordered = {k: groups[k] for k in PACKING_GROUP_ORDER if k in groups}
    blob = json.dumps(
        {
            "b": plan.get("budget"),
            "d": plan.get("destination"),
            "g": ordered,
            "n": plan.get("num_days"),
            "v": plan.get("trip_vibe"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:18]


def _it_block_html(eyebrow: str, title: str, desc: str) -> str:
    body = f'<p class="it-block__desc">{_h(desc)}</p>' if desc else ""
    return (
        f'<section class="it-block"><span class="it-block__eyebrow">{_h(eyebrow)}</span>'
        f'<h3 class="it-block__title">{_h(title)}</h3>{body}</section>'
    )


def _budget_breakdown_card_html(plan: dict, bd: dict) -> str:
    #mini table inside the card so numbers line up and scan like finance ui
    specs = (
        ("lodging", "lodging_estimate"),
        ("food", "food_estimate"),
        ("transit", "transit_estimate"),
        ("activities", "activities_estimate"),
    )
    body_rows = []
    for label, key in specs:
        lo, hi = bd[key]
        body_rows.append(
            "<tr>"
            f'<td class="budget-cat">{_h(label)}</td>'
            f'<td class="budget-amt">${lo:,}–${hi:,}</td>'
            "</tr>"
        )
    tlo, thi = bd["total_estimate"]
    days = max(1, int(plan.get("num_days") or 1))
    tips = (
        "<div class='budget-tips'>"
        "<p class='budget-tips__title'>how to use these numbers</p>"
        "<ul>"
        "<li><span class='budget-tip-em'>lodging ÷ nights</span> ≈ a nightly hotel filter to stay inside this trip shape.</li>"
        "<li><span class='budget-tip-em'>food ÷ days</span> ≈ a loose daily meals + snacks ceiling (coffee counts).</li>"
        "<li><span class='budget-tip-em'>transit + activities</span> are usually the first place to rebalance if one category runs hot.</li>"
        f"<li><span class='budget-tip-em'>total</span> sums the four rows — sanity-check big bookings against ${tlo:,}–${thi:,} before you lock dates.</li>"
        "</ul></div>"
    )
    summary = _h(str(plan.get("budget_summary", "")))
    table = (
        '<div class="budget-table-wrap">'
        '<table class="budget-table">'
        "<thead><tr><th>category</th><th>trip estimate (usd)</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "<tfoot><tr>"
        '<td class="budget-cat">total</td>'
        f'<td class="budget-amt">${tlo:,}–${thi:,}</td>'
        "</tr></tfoot></table></div>"
    )
    foot = (
        "<p class='budget-foot'>"
        "rule-based model · excludes flights and major tours · "
        "unknown cities use a neutral cost factor (1.0) · "
        f"shown for {days} {'days' if days != 1 else 'day'}"
        "</p>"
    )
    return (
        '<div class="budget-card budget-card--breakdown">'
        '<div class="budget-head">estimates by category</div>'
        f'<p class="budget-lede">{summary}</p>'
        f"{table}{tips}{foot}</div>"
    )


def hero() -> None:
    st.markdown(
        """
        <div class="hero-wrap">
            <div class="hero-inner">
                <span class="hero-kicker">soft itineraries · real pages</span>
                <h1>AI Travel Planner</h1>
                <p>plan a trip with scraped travel data and a hugging face recommendation model</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_debug_section(plan: dict) -> None:
    #only for dev: inspect ranking inputs and raw pools without opening python
    if not st.session_state.get("show_debug_info", False):
        return
    st.divider()
    st.markdown('<p class="debug-section-head">debug info</p>', unsafe_allow_html=True)
    st.caption(
        "compare queries to top rows to see why the embedder ranked things where it did — rebuild after toggling to refresh snapshots"
    )

    sup = plan.get("supported_destinations") or []
    st.markdown('<p class="debug-block-title">supported destinations</p>', unsafe_allow_html=True)
    st.code("\n".join(str(x) for x in sup) if sup else "(empty dataset list)", language=None)

    dbg = plan.get("debug")
    if not isinstance(dbg, dict):
        st.info('click "Build my trip" with this checkbox on to attach ranking snapshots from the planner.')
        return

    st.markdown('<p class="debug-block-title">ranking queries (embed input per slice)</p>', unsafe_allow_html=True)
    rq = dbg.get("ranking_queries") or {}
    if isinstance(rq, dict) and rq:
        for role in ("see_do", "eat", "drink", "sleep"):
            q = rq.get(role, "")
            st.markdown(f"**{role}**")
            st.code(q if q else "(empty)", language=None)
    else:
        st.caption("no query map in this plan snapshot")

    st.markdown('<p class="debug-block-title">top raw matches → itinerary pools</p>', unsafe_allow_html=True)
    st.caption("same ranked frames as _build_itinerary_days, before card copy runs")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**see / do**")
        st.json(dbg.get("top_see_do", []))
    with c2:
        st.markdown("**eat**")
        st.json(dbg.get("top_eat", []))
    with c3:
        st.markdown("**drink**")
        st.json(dbg.get("top_drink", []))

    st.markdown('<p class="debug-block-title">top raw hotel matches (sleep pool)</p>', unsafe_allow_html=True)
    st.json(dbg.get("top_hotel_rows", []))

    n = dbg.get("scoped_row_count")
    if n is not None:
        st.caption(f"rows in dataset for this destination (scoped): {n}")


def render_plan(plan: dict) -> None:
    #escape after we normalize so angle brackets from wiki text cannot break layout
    st.markdown('<p class="section-title">your trip pack</p>', unsafe_allow_html=True)

    dest = html.escape(str(plan["destination"]))
    vibe = html.escape(str(plan["trip_vibe"]) or "—")
    bud = html.escape(str(plan["budget"]) or "—")
    st.markdown(
        f"""
        <div class="trip-meta-card">
            <div class="trip-meta-block"><span>destination</span><strong>{dest}</strong></div>
            <div class="trip-meta-block"><span>vibe · budget</span><strong>{vibe} · {bud}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if plan.get("notice"):
        st.warning(html.escape(str(plan["notice"])))
    if not plan.get("ok", True) and plan.get("supported_destinations"):
        sup = ", ".join(html.escape(x) for x in plan["supported_destinations"])
        st.caption(f"supported destinations in dataset: {sup}")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["checklist", "itinerary", "places to stay", "packing", "budget"]
    )

    with tab1:
        st.markdown('<p class="checklist-page-head">travel checklist</p>', unsafe_allow_html=True)
        st.caption("tick rows as you finish them — ticks reset when you build a new trip")
        days = max(1, int(plan.get("num_days") or 1))
        checklist = build_checklist(
            str(plan.get("destination") or "your trip"),
            days,
            str(plan.get("trip_vibe") or ""),
            str(plan.get("budget") or "not sure"),
        )
        checklist = [str(x).strip() for x in checklist if not _blankish(x)]
        if not checklist:
            st.info("no checklist lines for this trip yet.")
        else:
            fp = _checklist_widget_fingerprint(plan, checklist)
            #bordered container reads like the old list-card when streamlit supports it
            try:
                shell = st.container(border=True)
            except TypeError:
                shell = st.container()
            with shell:
                for i, item in enumerate(checklist):
                    st.checkbox(item, key=f"travel_cb_{fp}_{i}")
                done = sum(
                    1 for j in range(len(checklist)) if st.session_state.get(f"travel_cb_{fp}_{j}", False)
                )
                st.progress(min(1.0, done / max(1, len(checklist))))
                st.caption(f"{done} of {len(checklist)} done")
            b1, b2, _ = st.columns([1, 1, 2])
            with b1:
                if st.button("mark all done", key=f"travel_cl_all_{fp}"):
                    for j in range(len(checklist)):
                        st.session_state[f"travel_cb_{fp}_{j}"] = True
                    st.rerun()
            with b2:
                if st.button("clear ticks", key=f"travel_cl_reset_{fp}"):
                    for j in range(len(checklist)):
                        st.session_state[f"travel_cb_{fp}_{j}"] = False
                    st.rerun()

    with tab2:
        if not plan.get("itinerary"):
            st.info(plan.get("notice") or "no itinerary built for this trip yet.")
        else:
            parts: list[str] = []
            for block in plan["itinerary"]:
                day = int(block["day"])
                mt = _ui_title(block.get("main_activity_title"), fallback="see & do")
                md = _ui_blurb(block.get("main_activity_description"))
                ft = _ui_title(block.get("food_title"), fallback="eat locally")
                fd = _ui_blurb(block.get("food_description"))
                dt = _ui_title(block.get("drink_title"), fallback="")
                dd = _ui_blurb(block.get("drink_description"))
                see_html = _it_block_html("see / do", mt, md)
                eat_html = _it_block_html("food", ft, fd)
                drink_html = ""
                if not _blankish(dt) or dd:
                    dtitle = dt if not _blankish(dt) else "drinks"
                    drink_html = _it_block_html("drink", dtitle, dd)
                parts.append(
                    f"""
                    <div class="day-card">
                        <div class="day-card__top"><span class="day-chip">day {day}</span></div>
                        <div class="day-card__body">{see_html}{eat_html}{drink_html}</div>
                    </div>
                    """
                )
            st.markdown(
                f'<div class="itinerary-stack">{"".join(parts)}</div>',
                unsafe_allow_html=True,
            )

    with tab3:
        if not plan.get("stays"):
            st.caption("no sleep rows passed the stay filter for this city yet.")
        else:
            cards: list[str] = []
            for stay in plan["stays"]:
                title = _ui_title(stay.get("title"), fallback="suggested stay")
                desc = _ui_blurb(stay.get("description", stay.get("note", "")))
                band_raw = stay.get("estimated_cost_band", "") or "unknown"
                band = "unknown" if _blankish(band_raw) else str(band_raw).strip()
                desc_block = f'<p class="stay-card__desc">{_h(desc)}</p>' if desc else ""
                cards.append(
                    f'<article class="stay-card">'
                    f'<div class="stay-card__head">'
                    f'<span class="stay-card__kicker">hotel</span>'
                    f'<span class="stay-band-pill">{_h(band)}</span></div>'
                    f'<h3 class="stay-card__title">{_h(title)}</h3>{desc_block}'
                    f"</article>"
                )
            st.markdown(f'<div class="stay-stack">{"".join(cards)}</div>', unsafe_allow_html=True)

    with tab4:
        st.markdown('<p class="packing-page-head">packing list</p>', unsafe_allow_html=True)
        st.caption("grouped by always-carry vs trip-shaped extras — ticks reset when you build a new trip")
        groups = _normalize_packing(plan.get("packing"))
        total = sum(len(v) for v in groups.values())
        if total == 0:
            st.info("no packing lines for this trip yet.")
        else:
            fp = _packing_widget_fingerprint(plan, groups)
            first_group = True
            for gk in PACKING_GROUP_ORDER:
                items = groups.get(gk, [])
                if not items:
                    continue
                label = PACKING_GROUP_LABELS.get(gk, gk.replace("_", " "))
                head_cls = (
                    "packing-group-head packing-group-head--first"
                    if first_group
                    else "packing-group-head"
                )
                first_group = False
                st.markdown(
                    f'<p class="{head_cls}">{html.escape(label)}</p>',
                    unsafe_allow_html=True,
                )
                try:
                    shell = st.container(border=True)
                except TypeError:
                    shell = st.container()
                with shell:
                    for i, item in enumerate(items):
                        st.checkbox(item, key=f"pack_cb_{fp}_{gk}_{i}")
            done = sum(
                1
                for gk in PACKING_GROUP_ORDER
                for j in range(len(groups.get(gk, [])))
                if st.session_state.get(f"pack_cb_{fp}_{gk}_{j}", False)
            )
            st.progress(min(1.0, done / max(1, total)))
            st.caption(f"{done} of {total} packed")
            b1, b2, _ = st.columns([1, 1, 2])
            with b1:
                if st.button("mark all packed", key=f"pack_all_{fp}"):
                    for gk in PACKING_GROUP_ORDER:
                        for j in range(len(groups.get(gk, []))):
                            st.session_state[f"pack_cb_{fp}_{gk}_{j}"] = True
                    st.rerun()
            with b2:
                if st.button("clear ticks", key=f"pack_reset_{fp}"):
                    for gk in PACKING_GROUP_ORDER:
                        for j in range(len(groups.get(gk, []))):
                            st.session_state[f"pack_cb_{fp}_{gk}_{j}"] = False
                    st.rerun()

    with tab5:
        st.markdown('<p class="budget-page-head">trip budget</p>', unsafe_allow_html=True)
        st.caption(
            "usd ranges for the whole trip — use the table to gut-check filters before you book, not as a quote"
        )
        bd = plan.get("budget_breakdown")
        req = (
            "lodging_estimate",
            "food_estimate",
            "transit_estimate",
            "activities_estimate",
            "total_estimate",
        )
        if isinstance(bd, dict) and all(k in bd for k in req):
            st.markdown(_budget_breakdown_card_html(plan, bd), unsafe_allow_html=True)
        else:
            summary = html.escape(str(plan.get("budget_summary", "")))
            bits = "".join(
                f"<li>{html.escape(str(line))}</li>" for line in (plan.get("budget_lines") or [])
            )
            st.markdown(
                f"""
                <div class="budget-card">
                    <div class="budget-head">rough estimate</div>
                    <p class="budget-lede">{summary}</p>
                    <ul class="budget-bits">{bits}</ul>
                    <p class="budget-foot">rebuild the trip to see the category breakdown.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    _render_debug_section(plan)


def main() -> None:
    #sidebar holds the form; main column is mostly results so it reads like a dashboard
    st.set_page_config(page_title="AI Travel Planner", layout="wide", initial_sidebar_state="expanded")
    inject_styles()
    hero()

    #one line so people see what the planner can actually use before touching the sidebar
    cities = supported_destinations()
    if cities:
        st.caption("cities in your dataset right now: " + ", ".join(cities))
    else:
        st.caption("no cities in travel_dataset.csv yet—run scraper.py then build_dataset.py.")

    with st.sidebar:
        st.markdown("### trip inputs")
        if cities:
            destination = st.selectbox(
                "destination",
                options=cities,
                index=0,
                help="only cities that survived the scrape + dataset filters",
            )
        else:
            st.selectbox(
                "destination",
                options=["(add data first)"],
                disabled=True,
                help="build travel_dataset.csv before this unlocks",
            )
            destination = ""
        num_days = st.number_input("number of days", min_value=1, max_value=21, value=4, step=1)
        trip_vibe = st.text_input("trip vibe", placeholder="e.g. slow food days + a little nightlife")
        budget = st.selectbox(
            "budget",
            options=["budget", "mid", "splurge", "not sure"],
            index=3,
        )
        must_see = st.text_area(
            "must-see interests",
            placeholder="temples, vinyl shopping, kid-friendly museums…",
            height=110,
        )
        st.checkbox(
            "show debug info",
            value=False,
            key="show_debug_info",
            help="after build: show destinations, embed queries, and top raw rows for itinerary + hotels",
        )
        build = st.button("Build my trip", type="primary", use_container_width=True, disabled=not cities)

    if build and cities:
        #selectbox already guarantees a supported city when the list is non-empty
        with st.spinner("loading the mini lm model (first run can take a bit)…"):
            plan = get_recommendations(
                destination=destination,
                num_days=int(num_days),
                trip_vibe=trip_vibe,
                budget=budget,
                must_see_interests=must_see,
                debug=st.session_state.get("show_debug_info", False),
            )
        st.session_state["last_plan"] = plan

    if st.session_state["last_plan"]:
        render_plan(st.session_state["last_plan"])


main()
