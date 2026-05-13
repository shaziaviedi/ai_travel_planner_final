"""streamlit shell for the travel planner."""

from __future__ import annotations

import html

import streamlit as st

from planner import get_recommendations

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
        .day-card {
            border-radius: 18px;
            border: 1px solid rgba(210, 218, 232, 0.85);
            background: rgba(255, 255, 255, 0.92);
            box-shadow: 0 12px 32px rgba(95, 115, 145, 0.08);
            margin-bottom: 1rem;
            overflow: hidden;
        }
        .day-card__top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.65rem 1rem;
            background: linear-gradient(90deg, rgba(232, 240, 248, 0.9), rgba(245, 238, 252, 0.75));
            border-bottom: 1px solid rgba(210, 218, 232, 0.65);
        }
        .day-chip {
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #4a5d72;
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
        .stay-stack { display: flex; flex-direction: column; gap: 1rem; }
        .stay-card {
            border-radius: 18px;
            border: 1px solid rgba(220, 200, 185, 0.55);
            background: linear-gradient(145deg, rgba(255, 251, 246, 0.95), rgba(248, 242, 255, 0.75));
            box-shadow: 0 10px 26px rgba(120, 100, 90, 0.07);
            padding: 0.85rem 1rem 1rem 1rem;
            border-left: 4px solid rgba(196, 160, 140, 0.55);
        }
        .stay-eyebrow {
            font-size: 0.65rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: #9a7b6f;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .stay-title { font-weight: 600; color: #3a3230; font-size: 1rem; line-height: 1.35; }
        .stay-note { color: #5c534f; font-size: 0.92rem; line-height: 1.5; margin: 0.45rem 0 0; }
        .pack-card {
            border-radius: 18px;
            border: 1px solid rgba(210, 218, 232, 0.75);
            background: rgba(255, 255, 255, 0.88);
            padding: 0.9rem 1rem 1rem;
            box-shadow: 0 10px 28px rgba(95, 115, 145, 0.06);
        }
        .pack-cols { display: flex; gap: 1.5rem; flex-wrap: wrap; }
        .pack-cols ul {
            flex: 1;
            min-width: 220px;
            list-style: none;
            margin: 0;
            padding: 0;
        }
        .pack-cols li { margin-bottom: 0.45rem; }
        .pack-cols label {
            display: flex;
            align-items: flex-start;
            gap: 0.45rem;
            cursor: default;
            color: #4a5568;
            font-size: 0.95rem;
            line-height: 1.45;
        }
        .pack-cols input { margin-top: 0.2rem; accent-color: #7b9eb8; }
        .budget-card {
            border-radius: 18px;
            border: 1px solid rgba(200, 214, 228, 0.85);
            background: rgba(255, 255, 255, 0.9);
            padding: 0.95rem 1.1rem 1rem;
            box-shadow: 0 10px 28px rgba(95, 115, 145, 0.07);
            max-width: 520px;
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
            margin: 0 0 0.55rem;
            font-size: 0.98rem;
            font-weight: 600;
            color: #2f3847;
            line-height: 1.45;
        }
        ul.budget-bits {
            margin: 0;
            padding-left: 1.1rem;
            color: #5a6675;
            font-size: 0.88rem;
            line-height: 1.45;
        }
        ul.budget-bits li { margin-bottom: 0.25rem; }
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


def render_plan(plan: dict) -> None:
    #html bits only use escaped strings so random wiki angle brackets do not break the layout
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["checklist", "itinerary", "places to stay", "packing", "budget"]
    )

    with tab1:
        items_html = "".join(f"<li>{html.escape(str(i))}</li>" for i in plan["checklist"])
        st.markdown(
            f'<div class="list-card"><ul class="dreamy-list">{items_html}</ul></div>',
            unsafe_allow_html=True,
        )

    with tab2:
        for block in plan["itinerary"]:
            day = int(block["day"])
            acts = block["activities"]
            lis = "".join(f"<li>{html.escape(str(a))}</li>" for a in acts)
            st.markdown(
                f"""
                <div class="day-card">
                    <div class="day-card__top"><span class="day-chip">day {day}</span></div>
                    <ul class="day-card__acts">{lis}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab3:
        cards: list[str] = []
        for stay in plan["stays"]:
            title = html.escape(str(stay.get("title", "")))
            note = html.escape(str(stay.get("note", "")))
            cards.append(
                f'<div class="stay-card"><div class="stay-eyebrow">suggested stay</div>'
                f'<div class="stay-title">{title}</div><p class="stay-note">{note}</p></div>'
            )
        st.markdown(f'<div class="stay-stack">{"".join(cards)}</div>', unsafe_allow_html=True)

    with tab4:
        items = plan["packing"]
        mid = (len(items) + 1) // 2

        def pack_rows(chunk: list[str]) -> str:
            rows = []
            for x in chunk:
                rows.append(
                    "<li><label><input type='checkbox' disabled='disabled' /> "
                    f"<span>{html.escape(str(x))}</span></label></li>"
                )
            return "<ul>" + "".join(rows) + "</ul>"

        left = pack_rows(items[:mid])
        right = pack_rows(items[mid:])
        st.markdown(
            f'<div class="pack-card"><div class="pack-cols">{left}{right}</div></div>',
            unsafe_allow_html=True,
        )

    with tab5:
        summary = html.escape(str(plan["budget_summary"]))
        bits = "".join(f"<li>{html.escape(str(line))}</li>" for line in plan["budget_lines"])
        st.markdown(
            f"""
            <div class="budget-card">
                <div class="budget-head">rough estimate</div>
                <p class="budget-lede">{summary}</p>
                <ul class="budget-bits">{bits}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    #sidebar holds the form; main column is mostly results so it reads like a dashboard
    st.set_page_config(page_title="AI Travel Planner", layout="wide", initial_sidebar_state="expanded")
    inject_styles()
    hero()

    with st.sidebar:
        st.markdown("### trip inputs")
        destination = st.text_input("destination", placeholder="e.g. Tokyo")
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
        build = st.button("Build my trip", type="primary", use_container_width=True)

    if build:
        if not destination.strip():
            st.warning("add a destination so we know where to aim the retriever.")
        else:
            #first click may download weights; spinner keeps people patient
            with st.spinner("loading the mini lm model (first run can take a bit)…"):
                plan = get_recommendations(
                    destination=destination.strip(),
                    num_days=int(num_days),
                    trip_vibe=trip_vibe,
                    budget=budget,
                    must_see_interests=must_see,
                )
            st.session_state["last_plan"] = plan

    if st.session_state["last_plan"]:
        render_plan(st.session_state["last_plan"])


main()
