"""Streamlit shell for Somnia Travel Planner."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import time

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

#dreamy loading card: html clouds + css only, shown in an st.empty while the planner runs
SOMNIA_LOADER_HTML = """
<div class="somnia-loader-card" role="status" aria-live="polite">
  <div class="somnia-loader-ambient" aria-hidden="true"></div>
  <div class="somnia-loader-cloud-stage" aria-hidden="true">
    <div class="somnia-loader-cloud somnia-loader-cloud--big"></div>
    <div class="somnia-loader-cloud somnia-loader-cloud--mid"></div>
    <div class="somnia-loader-cloud somnia-loader-cloud--small"></div>
  </div>
  <p class="somnia-loader-text">generating your dreamy getaway...</p>
  <p class="somnia-loader-sub">soft ideas, light ranks, no rush</p>
  <div class="somnia-loader-shimmer" aria-hidden="true"><span></span></div>
</div>
"""


def inject_styles() -> None:
    #twilight / plum glass theme; sidebar hidden so the page reads as one dreamscape
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;1,9..144,400&family=Outfit:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: "Outfit", system-ui, sans-serif;
            color: #dce3f4;
        }
        section[data-testid="stSidebar"],
        div[data-testid="collapsedControl"] {
            display: none !important;
        }
        [data-testid="stAppViewContainer"] {
            background: radial-gradient(ellipse 100% 70% at 50% -15%, rgba(118, 86, 168, 0.28) 0%, transparent 52%),
                radial-gradient(ellipse 80% 50% at 100% 20%, rgba(72, 62, 120, 0.35) 0%, transparent 45%),
                linear-gradient(172deg, #0f1118 0%, #151222 32%, #12182c 58%, #141326 100%) !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            background: transparent;
        }
        /*streamlit injects primaryColor etc; nudge widgets off default red/blue when vars exist*/
        .stApp {
            --primary-color: #8b74c4 !important;
            /*results + tabs: keep typography to a small scale (caption / body / title / section)*/
            --somnia-fs-cap: 0.75rem;
            --somnia-fs-body: 0.875rem;
            --somnia-fs-title: 1rem;
            --somnia-fs-section: 1.125rem;
        }
        html {
            scroll-behavior: smooth;
            scroll-padding-top: 4.5rem;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 3.5rem;
            max-width: min(1320px, 96vw);
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        section.main .stMarkdown, section.main [data-testid="stMarkdownContainer"] p {
            color: #c8d2ec;
        }
        section.main label, section.main [data-baseweb="form-control"] label {
            color: #b8c5e5 !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.04em;
        }
        section.main [data-testid="stWidgetLabel"] p {
            color: #c5d0ea !important;
        }
        section.main [data-baseweb="input"],
        section.main [data-baseweb="textarea"] {
            background: rgba(28, 32, 52, 0.55) !important;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(130, 110, 180, 0.22) !important;
            border-radius: 14px !important;
            color: #eef2ff !important;
        }
        section.main [data-baseweb="select"] > div {
            background: rgba(28, 32, 52, 0.55) !important;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(130, 110, 180, 0.22) !important;
            border-radius: 14px !important;
        }
        section.main .stNumberInput input {
            background: rgba(28, 32, 52, 0.55) !important;
            color: #eef2ff !important;
            border-radius: 14px !important;
            border: 1px solid rgba(130, 110, 180, 0.22) !important;
        }
        section.main .stButton > button[kind="primary"],
        section.main [data-testid="stFormSubmitButton"] button,
        section.main [data-testid="baseButton-primary"],
        .stApp [data-testid="stFormSubmitButton"] button,
        .stApp [data-testid="baseButton-primary"],
        .stApp button[kind="primary"] {
            border-radius: 999px !important;
            border: 1px solid rgba(170, 150, 220, 0.35) !important;
            padding: 0.7rem 1.5rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.06em !important;
            background: linear-gradient(125deg, #6a4fa8 0%, #8b6bc4 38%, #5c7eb8 100%) !important;
            background-image: linear-gradient(125deg, #6a4fa8 0%, #8b6bc4 38%, #5c7eb8 100%) !important;
            color: #f4f2ff !important;
            box-shadow: 0 12px 36px rgba(60, 40, 100, 0.45) !important;
        }
        section.main .stButton > button[kind="primary"]:hover,
        section.main [data-testid="stFormSubmitButton"] button:hover,
        section.main [data-testid="baseButton-primary"]:hover,
        .stApp [data-testid="stFormSubmitButton"] button:hover,
        .stApp [data-testid="baseButton-primary"]:hover,
        .stApp button[kind="primary"]:hover {
            filter: brightness(1.06);
            box-shadow: 0 14px 40px rgba(80, 55, 130, 0.5) !important;
        }
        section.main .stButton > button[kind="secondary"],
        section.main [data-testid="baseButton-secondary"] {
            border-radius: 999px !important;
            background: rgba(40, 44, 68, 0.75) !important;
            border: 1px solid rgba(130, 115, 175, 0.45) !important;
            color: #e4defc !important;
        }
        section.main .stButton > button[kind="secondary"]:hover,
        section.main [data-testid="baseButton-secondary"]:hover {
            border-color: rgba(170, 150, 215, 0.55) !important;
            background: rgba(52, 48, 82, 0.85) !important;
        }
        section.main [data-testid="stFormSubmitButton"] {
            width: 100%;
        }
        section.main [data-testid="stFormSubmitButton"] > div {
            width: 100%;
        }
        section.main [data-testid="stFormSubmitButton"] button {
            width: 100% !important;
        }
        section.main [data-testid="stForm"] {
            border-radius: 24px !important;
            padding: 1.35rem 1.4rem 1.5rem !important;
            margin: 0 0 1.25rem !important;
            background: rgba(22, 26, 42, 0.5) !important;
            border: 1px solid rgba(120, 100, 170, 0.22) !important;
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
            backdrop-filter: blur(14px);
        }
        section.main .stCheckbox label {
            color: #c8d2ec !important;
        }
        [data-testid="stCaptionContainer"] p, section.main [data-testid="stCaptionContainer"] p {
            color: #8a9ab8 !important;
            font-size: 0.84rem !important;
        }
        div[data-testid="stSpinner"] {
            color: #d4ccf0 !important;
        }
        section.main [data-testid="stMarkdownContainer"] strong {
            color: #e8e0ff;
        }
        .somnia-hero {
            position: relative;
            overflow: hidden;
            border-radius: 28px;
            padding: clamp(2rem, 6vh, 4rem) clamp(1.5rem, 4vw, 3rem);
            margin: 0 0 2rem;
            min-height: min(100svh, calc(100vh - 3.5rem));
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(145deg, rgba(42, 38, 72, 0.55) 0%, rgba(32, 36, 58, 0.72) 45%, rgba(28, 34, 56, 0.78) 100%);
            border: 1px solid rgba(140, 120, 190, 0.2);
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(16px);
        }
        .somnia-hero::before {
            content: "";
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at 15% 30%, rgba(160, 120, 220, 0.15) 0%, transparent 45%),
                radial-gradient(circle at 88% 15%, rgba(100, 140, 200, 0.12) 0%, transparent 40%);
            pointer-events: none;
        }
        .somnia-cloud {
            position: absolute;
            border-radius: 50%;
            background: radial-gradient(
                circle at 40% 38%,
                rgba(225, 215, 252, 0.52) 0%,
                rgba(175, 160, 220, 0.22) 42%,
                rgba(120, 105, 165, 0.1) 62%,
                transparent 78%
            );
            filter: blur(3px);
            opacity: 0.92;
            pointer-events: none;
            box-shadow:
                0 0 32px rgba(185, 175, 235, 0.28),
                inset 0 -6px 20px rgba(55, 48, 88, 0.1);
        }
        .somnia-cloud::before,
        .somnia-cloud::after {
            content: "";
            position: absolute;
            border-radius: 50%;
            pointer-events: none;
            filter: blur(2px);
        }
        .somnia-cloud::before {
            width: 58%;
            height: 52%;
            left: -18%;
            top: 14%;
            background: radial-gradient(circle at 45% 42%, rgba(218, 208, 250, 0.48), transparent 72%);
        }
        .somnia-cloud::after {
            width: 50%;
            height: 46%;
            right: -14%;
            top: 18%;
            background: radial-gradient(circle at 52% 40%, rgba(205, 195, 242, 0.42), transparent 74%);
        }
        .somnia-cloud--1 {
            width: 248px;
            height: 132px;
            top: 8%;
            right: 4%;
            animation: somnia-hero-drift-a 9.5s ease-in-out infinite;
        }
        .somnia-cloud--2 {
            width: 188px;
            height: 100px;
            top: auto;
            bottom: 12%;
            right: 10%;
            animation: somnia-hero-drift-b 11.5s ease-in-out infinite reverse;
            opacity: 0.62;
        }
        .somnia-cloud--3 {
            width: 156px;
            height: 88px;
            top: 18%;
            left: 3%;
            animation: somnia-hero-drift-c 10s ease-in-out infinite 0.6s;
            opacity: 0.52;
        }
        @keyframes somnia-hero-drift-a {
            0%, 100% { transform: translate(0, 0) scale(1); }
            30% { transform: translate(-26px, 16px) scale(1.05); }
            55% { transform: translate(12px, -18px) scale(0.98); }
            78% { transform: translate(20px, 8px) scale(1.02); }
        }
        @keyframes somnia-hero-drift-b {
            0%, 100% { transform: translate(0, 0) scale(1); }
            35% { transform: translate(24px, 14px) scale(1.04); }
            65% { transform: translate(-22px, -16px) scale(0.97); }
            85% { transform: translate(-8px, 18px) scale(1.03); }
        }
        @keyframes somnia-hero-drift-c {
            0%, 100% { transform: translate(0, 0) scale(1); }
            28% { transform: translate(22px, -14px) scale(1.06); }
            52% { transform: translate(-24px, 12px) scale(0.96); }
            72% { transform: translate(-10px, -20px) scale(1.03); }
        }
        .somnia-hero-inner {
            position: relative;
            z-index: 1;
            max-width: min(56rem, 94%);
            margin: 0 auto;
            text-align: center;
        }
        .somnia-brand {
            font-family: "Outfit", sans-serif;
            font-size: clamp(0.75rem, 1.2vw, 0.88rem);
            letter-spacing: 0.22em;
            text-transform: none;
            color: #a898d8;
            margin: 0 0 1rem;
            font-weight: 600;
        }
        .somnia-title {
            font-family: "Fraunces", Georgia, serif;
            margin: 0;
            font-size: clamp(2.75rem, 10vw, 5.75rem);
            font-weight: 600;
            letter-spacing: -0.035em;
            line-height: 1.02;
            color: #f2efff;
            text-shadow: 0 4px 40px rgba(80, 60, 140, 0.45);
        }
        .somnia-hero-cta {
            display: inline-block;
            margin-top: clamp(1.75rem, 4vh, 2.75rem);
            padding: 0.95rem 2.1rem;
            font-family: "Outfit", system-ui, sans-serif;
            font-size: clamp(0.95rem, 1.8vw, 1.12rem);
            font-weight: 600;
            letter-spacing: 0.04em;
            color: #f4f2ff !important;
            text-decoration: none !important;
            border-radius: 999px;
            background: linear-gradient(125deg, #6a4fa8 0%, #8b6bc4 38%, #5c7eb8 100%);
            box-shadow: 0 14px 44px rgba(60, 40, 100, 0.5);
            border: none;
            transition: filter 0.15s ease, transform 0.15s ease;
        }
        .somnia-hero-cta:hover {
            filter: brightness(1.08);
            transform: translateY(-2px);
            color: #faf8ff !important;
        }
        .somnia-anchor {
            height: 0;
            margin: 0;
            padding: 0;
            scroll-margin-top: 5rem;
        }
        .somnia-form-eyebrow {
            font-size: 0.68rem;
            letter-spacing: 0.12em;
            text-transform: none;
            color: #9aa8cc;
            font-weight: 600;
            margin: 0 0 0.75rem;
        }
        .somnia-dataset-note {
            font-size: 0.82rem;
            color: #7d8db0;
            margin: 0 0 1.1rem;
            line-height: 1.45;
        }
        .somnia-loader-card {
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.65rem;
            padding: 2.35rem 1.5rem 2.1rem;
            margin: 0 0 1.25rem;
            min-height: 200px;
            justify-content: center;
            border-radius: 26px;
            background: linear-gradient(165deg, rgba(38, 34, 62, 0.72) 0%, rgba(26, 30, 50, 0.78) 50%, rgba(22, 28, 48, 0.82) 100%);
            border: 1px solid rgba(140, 120, 190, 0.28);
            box-shadow: 0 20px 56px rgba(0, 0, 0, 0.38),
                inset 0 1px 0 rgba(255, 255, 255, 0.06),
                0 0 80px rgba(100, 80, 160, 0.12);
            backdrop-filter: blur(18px);
        }
        .somnia-loader-ambient {
            position: absolute;
            inset: -35% -25%;
            background: radial-gradient(ellipse 50% 42% at 48% 38%, rgba(150, 120, 210, 0.28), transparent 65%),
                radial-gradient(ellipse 40% 35% at 72% 62%, rgba(90, 120, 180, 0.14), transparent 58%);
            animation: somnia-loader-ambient 5.5s ease-in-out infinite;
            pointer-events: none;
        }
        @keyframes somnia-loader-ambient {
            0%, 100% { opacity: 0.55; transform: translate(0, 0) scale(1); }
            50% { opacity: 1; transform: translate(6px, -10px) scale(1.05); }
        }
        .somnia-loader-cloud-stage {
            position: relative;
            z-index: 1;
            width: 220px;
            height: 88px;
            animation: somnia-loader-float 4.2s ease-in-out infinite;
        }
        @keyframes somnia-loader-float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-8px); }
        }
        .somnia-loader-cloud {
            position: absolute;
            border-radius: 50%;
            background: radial-gradient(
                circle at 40% 36%,
                rgba(228, 218, 255, 0.58) 0%,
                rgba(175, 158, 225, 0.26) 48%,
                rgba(115, 98, 165, 0.12) 68%,
                transparent 82%
            );
            filter: blur(1.8px);
            box-shadow:
                0 0 22px rgba(190, 178, 240, 0.35),
                inset 0 -5px 14px rgba(48, 42, 78, 0.12),
                16px 6px 0 -4px rgba(205, 192, 248, 0.28),
                -14px 8px 0 -5px rgba(188, 175, 235, 0.22);
        }
        .somnia-loader-cloud::before,
        .somnia-loader-cloud::after {
            content: "";
            position: absolute;
            border-radius: 50%;
            pointer-events: none;
            filter: blur(1.2px);
        }
        .somnia-loader-cloud::before {
            width: 54%;
            height: 50%;
            left: -16%;
            top: 16%;
            background: radial-gradient(circle at 46% 44%, rgba(220, 208, 252, 0.55), transparent 70%);
        }
        .somnia-loader-cloud::after {
            width: 48%;
            height: 44%;
            right: -14%;
            top: 20%;
            background: radial-gradient(circle at 50% 40%, rgba(210, 198, 245, 0.48), transparent 74%);
        }
        .somnia-loader-cloud--big {
            width: 100px;
            height: 58px;
            left: 50%;
            top: 6px;
            transform: translateX(-50%);
            animation: somnia-loader-puff 2.4s ease-in-out infinite;
        }
        .somnia-loader-cloud--mid {
            width: 60px;
            height: 40px;
            left: 10%;
            top: 30px;
            opacity: 0.9;
            animation: somnia-loader-puff-sat 2.4s ease-in-out infinite 0.25s;
        }
        .somnia-loader-cloud--small {
            width: 48px;
            height: 32px;
            right: 8%;
            top: 34px;
            opacity: 0.82;
            animation: somnia-loader-puff-sat 2.4s ease-in-out infinite 0.5s;
        }
        @keyframes somnia-loader-puff {
            0%, 100% { transform: translateX(-50%) scale(1); opacity: 0.75; }
            50% { transform: translateX(-50%) scale(1.06); opacity: 1; }
        }
        @keyframes somnia-loader-puff-sat {
            0%, 100% { transform: scale(1); opacity: 0.7; }
            50% { transform: scale(1.08); opacity: 1; }
        }
        .somnia-loader-text {
            position: relative;
            z-index: 1;
            font-family: "Fraunces", Georgia, serif;
            font-size: 1.12rem;
            font-weight: 500;
            font-style: italic;
            color: #ebe6ff;
            letter-spacing: 0.02em;
            margin: 0.35rem 0 0;
            text-shadow: 0 2px 20px rgba(80, 60, 130, 0.45);
            animation: somnia-loader-text-glow 2.8s ease-in-out infinite;
        }
        @keyframes somnia-loader-text-glow {
            0%, 100% { opacity: 0.88; }
            50% { opacity: 1; }
        }
        .somnia-loader-sub {
            position: relative;
            z-index: 1;
            margin: 0;
            font-size: 0.78rem;
            font-weight: 400;
            color: #8b9cc8;
            letter-spacing: 0.06em;
        }
        .somnia-loader-shimmer {
            position: relative;
            z-index: 1;
            width: min(300px, 92%);
            height: 3px;
            margin-top: 0.5rem;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(80, 72, 120, 0.35);
        }
        .somnia-loader-shimmer span {
            display: block;
            height: 100%;
            width: 38%;
            border-radius: 999px;
            background: linear-gradient(90deg, transparent, rgba(200, 188, 245, 0.65), transparent);
            animation: somnia-loader-shimmer 1.75s ease-in-out infinite;
        }
        @keyframes somnia-loader-shimmer {
            0% { transform: translateX(-120%); }
            100% { transform: translateX(320%); }
        }
        .somnia-results-anchor {
            margin: 2.5rem 0 1.85rem;
            padding: 1.85rem 1.5rem 1.65rem;
            border-radius: 22px;
            border-top: none;
            background: linear-gradient(165deg, rgba(40, 36, 68, 0.88) 0%, rgba(22, 26, 44, 0.9) 100%);
            border: 1px solid rgba(125, 105, 175, 0.38);
            box-shadow: 0 22px 56px rgba(0, 0, 0, 0.38), inset 0 1px 0 rgba(255, 255, 255, 0.06);
        }
        .somnia-results-anchor.somnia-results-reveal {
            animation: somnia-results-in 0.75s cubic-bezier(0.22, 1, 0.36, 1) forwards;
            opacity: 0;
        }
        @keyframes somnia-results-in {
            from {
                opacity: 0;
                transform: translateY(18px);
                filter: blur(8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
                filter: blur(0);
            }
        }
        .somnia-results-kicker {
            margin: 0 0 0.4rem;
            font-size: var(--somnia-fs-cap);
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: #b0a4e0;
        }
        .somnia-trip-summary-title {
            margin: 0 0 1.15rem;
            font-family: "Fraunces", Georgia, serif;
            font-size: clamp(1.65rem, 2.6vw, 2.15rem);
            font-weight: 650;
            letter-spacing: -0.035em;
            line-height: 1.12;
            color: #faf8ff;
        }
        .trip-meta-card {
            display: flex;
            flex-wrap: wrap;
            gap: 1.25rem 2rem;
            padding: 1.2rem 1.4rem 1.2rem 1.35rem;
            margin: 0;
            border-radius: 18px;
            background: rgba(18, 22, 38, 0.72);
            border: 1px solid rgba(110, 95, 155, 0.32);
            border-left: 4px solid rgba(175, 155, 245, 0.75);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 10px 32px rgba(0, 0, 0, 0.22);
            backdrop-filter: blur(12px);
        }
        .trip-meta-block span {
            display: block;
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.1em;
            text-transform: none;
            color: #8b9cc8;
            margin-bottom: 0.35rem;
            font-weight: 600;
        }
        .trip-meta-block strong {
            font-size: var(--somnia-fs-title);
            color: #f0ecff;
            font-weight: 600;
        }
        .list-card {
            border-radius: 18px;
            background: rgba(28, 32, 50, 0.5);
            border: 1px solid rgba(110, 95, 160, 0.2);
            padding: 1rem 1.15rem 0.85rem;
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.2);
        }
        ul.dreamy-list {
            margin: 0;
            padding-left: 1.15rem;
            color: #b4c0df;
            line-height: 1.55;
        }
        ul.dreamy-list li { margin-bottom: 0.45rem; }
        .prep-page-head, .budget-page-head {
            font-size: var(--somnia-fs-section);
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #e8e4fc;
            margin: 0 0 0.35rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 18px !important;
            background: rgba(26, 30, 48, 0.55) !important;
            border: 1px solid rgba(120, 100, 170, 0.2) !important;
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.22) !important;
            padding: 0.4rem 0.55rem 0.7rem !important;
            backdrop-filter: blur(10px);
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
            border-radius: 14px;
            border: 1px solid rgba(100, 90, 140, 0.25);
            background: rgba(36, 40, 62, 0.55);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"] label:hover,
        section.main [data-testid="stCheckbox"] label:hover {
            border-color: rgba(160, 140, 210, 0.35);
            box-shadow: 0 4px 20px rgba(60, 40, 100, 0.25);
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"] label p,
        section.main [data-testid="stCheckbox"] label p {
            margin: 0;
            font-size: var(--somnia-fs-body);
            line-height: 1.45;
            color: #c8d2ec;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"]:has(input:checked) label,
        section.main [data-testid="stCheckbox"]:has(input:checked) label {
            border-color: rgba(140, 120, 200, 0.45);
            background: rgba(50, 45, 85, 0.45);
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCheckbox"]:has(input:checked) label p,
        section.main [data-testid="stCheckbox"]:has(input:checked) label p {
            color: #9db0d8;
            text-decoration: line-through;
            text-decoration-thickness: 1px;
            text-decoration-color: rgba(140, 150, 190, 0.45);
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"],
        section.main [data-testid="stVerticalBlock"] [data-testid="stProgress"] {
            margin-top: 0.65rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"] > div,
        section.main [data-testid="stProgress"] > div,
        .stApp [data-testid="stProgress"] > div {
            border-radius: 999px !important;
            background: transparent !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"] > div > div,
        .stApp [data-testid="stProgress"] > div > div,
        section.main [data-testid="stProgress"] > div > div {
            border-radius: 999px !important;
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
        }
        /*third nested div is the full-width track; fourth is the fill (streamlit/baseui convention)*/
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"] > div > div > div,
        .stApp [data-testid="stProgress"] > div > div > div,
        section.main [data-testid="stProgress"] > div > div > div,
        .stApp .stProgress > div > div > div,
        section.main .stProgress > div > div > div {
            border-radius: 999px !important;
            background: rgba(12, 14, 24, 0.97) !important;
            background-image: none !important;
            box-shadow: inset 0 1px 5px rgba(0, 0, 0, 0.55) !important;
            border: 1px solid rgba(42, 40, 62, 0.75) !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stProgress"] > div > div > div > div,
        .stApp [data-testid="stProgress"] > div > div > div > div,
        section.main [data-testid="stProgress"] > div > div > div > div,
        .stApp .stProgress > div > div > div > div,
        section.main .stProgress > div > div > div > div {
            background: linear-gradient(90deg, #6a4fa8 0%, #8b7ec8 50%, #a898e0 100%) !important;
            background-color: #7d68b8 !important;
            border-radius: 999px !important;
            border: none !important;
            box-shadow: none !important;
        }
        .stApp [data-testid="stProgress"] [role="progressbar"],
        section.main [data-testid="stProgress"] [role="progressbar"] {
            background: transparent !important;
        }
        .stApp [data-testid="stTabs"],
        section.main [data-testid="stTabs"] {
            margin: 0 0 0.9rem !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
        }
        /*outer tabs shell: no card — card is only on the tab row so results are not inside the nav chrome*/
        .stApp [data-testid="stTabs"] [data-baseweb="tabs"],
        section.main [data-testid="stTabs"] [data-baseweb="tabs"] {
            margin: 0 !important;
            padding: 0 !important;
            border: none !important;
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            box-sizing: border-box !important;
            overflow: visible;
            display: flex;
            flex-direction: column;
            /*keep a tiny flex gap for layout quirks; main air below nav is on tab panels*/
            gap: 0.35rem;
        }
        /*big vertical pause below the nav card, above tab body (Prep headline, itinerary, etc.)*/
        .stApp [data-testid="stTabs"] [data-baseweb="tab-panel"],
        section.main [data-testid="stTabs"] [data-baseweb="tab-panel"],
        .stApp [data-testid="stTabs"] [role="tabpanel"],
        section.main [data-testid="stTabs"] [role="tabpanel"] {
            padding-top: 3rem !important;
        }
        /*tabs-motion draws a full-width TabBorder under the row (borderColorLight); hide it, keep per-tab styling*/
        .stApp [data-testid="stTabs"] [data-baseweb*="tab-border"],
        section.main [data-testid="stTabs"] [data-baseweb*="tab-border"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        .stApp .stTabs [data-baseweb="tab-list"] {
            align-self: stretch;
            gap: 0.4rem;
            margin: 0 !important;
            padding: 8px 10px 10px !important;
            border-radius: 18px !important;
            border: 1px solid rgba(120, 100, 165, 0.44) !important;
            background: linear-gradient(180deg, rgba(28, 32, 52, 0.82) 0%, rgba(20, 24, 40, 0.9) 100%) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 10px 32px rgba(0, 0, 0, 0.25) !important;
            box-sizing: border-box !important;
        }
        .stApp .stTabs [data-baseweb="tab-list"]::before,
        .stApp .stTabs [data-baseweb="tab-list"]::after {
            display: none !important;
            content: none !important;
        }
        .stApp .stTabs [data-baseweb="tab"] {
            border-radius: 12px;
            padding: 0.5rem 0.85rem;
            font-size: var(--somnia-fs-body);
            font-weight: 500;
            color: #8a9ab8;
            border-bottom: 2px solid transparent !important;
            box-shadow: none !important;
        }
        .stApp .stTabs [data-baseweb="tab"][aria-selected="false"] {
            color: #8a9ab8 !important;
            border-bottom-color: transparent !important;
        }
        .stApp .stTabs [aria-selected="true"],
        .stApp .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(145deg, rgba(70, 55, 110, 0.65) 0%, rgba(45, 55, 95, 0.75) 100%) !important;
            color: #f0ecff !important;
            box-shadow: 0 6px 22px rgba(40, 30, 80, 0.35);
            border: 1px solid rgba(140, 120, 190, 0.25) !important;
            border-bottom: 2px solid rgba(190, 170, 245, 0.9) !important;
        }
        .stApp .stTabs [data-baseweb="tab"]:focus-visible {
            outline: 2px solid rgba(170, 150, 230, 0.55) !important;
            outline-offset: 1px;
        }
        /*prep checklist: outer row is spacer + right “tray”; inner row packs both buttons to the tray’s right (same edge as full-width progress)*/
        .stApp [data-baseweb="tab-panel"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child [data-testid="stHorizontalBlock"],
        section.main [data-baseweb="tab-panel"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            justify-content: flex-end !important;
            align-items: center !important;
            gap: 0.12rem !important;
            column-gap: 0.12rem !important;
        }
        .stApp [data-baseweb="tab-panel"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        section.main [data-baseweb="tab-panel"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            flex: 0 0 auto !important;
            min-width: 0 !important;
            width: auto !important;
        }
        .stApp [data-testid="stCheckbox"] input[type="checkbox"],
        section.main [data-testid="stCheckbox"] input[type="checkbox"] {
            accent-color: #9578d4 !important;
        }
        .stApp [data-baseweb="checkbox"] [role="checkbox"],
        section.main [data-baseweb="checkbox"] [role="checkbox"] {
            border-color: rgba(140, 125, 190, 0.6) !important;
            background: rgba(32, 36, 56, 0.85) !important;
        }
        .stApp [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"],
        section.main [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] {
            background: linear-gradient(145deg, rgba(110, 88, 168, 0.98), rgba(150, 125, 210, 0.98)) !important;
            background-color: #7d68b8 !important;
            border-color: rgba(220, 210, 252, 0.55) !important;
        }
        .stApp [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] svg,
        .stApp [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] path,
        section.main [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] svg,
        section.main [data-baseweb="checkbox"] [role="checkbox"][aria-checked="true"] path {
            fill: #f4f2ff !important;
            stroke: #f4f2ff !important;
        }
        .itinerary-stack {
            display: flex;
            flex-direction: column;
            gap: 1.2rem;
        }
        details.it-day-card-outer.it-day-expand {
            border-radius: 20px;
            border: 1px solid rgba(120, 105, 175, 0.32);
            background: linear-gradient(165deg, rgba(34, 32, 56, 0.92) 0%, rgba(22, 26, 44, 0.95) 100%);
            box-shadow: 0 18px 48px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            overflow: hidden;
            margin: 0.35rem 0 0.65rem;
            backdrop-filter: blur(14px);
        }
        details.it-day-expand:not([open]) .it-day-card__banner {
            border-bottom: none;
        }
        .it-day-expand__summary {
            cursor: pointer;
            list-style: none;
            width: 100%;
            box-sizing: border-box;
        }
        .it-day-expand__summary::-webkit-details-marker {
            display: none;
        }
        .it-day-expand__chev {
            margin-left: auto;
            flex-shrink: 0;
            font-size: 0.75rem;
            line-height: 1;
            color: #c8b8f0;
            padding: 0.35rem 0.5rem;
            transition: transform 0.2s ease;
        }
        details.it-day-expand[open] .it-day-expand__chev {
            transform: rotate(180deg);
        }
        section.main [data-testid="stMarkdownContainer"] details.it-day-expand {
            width: 100%;
            max-width: none;
        }
        .it-day-card__banner {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1rem 1.15rem 1rem 1.25rem;
            background: linear-gradient(105deg, rgba(62, 52, 98, 0.55) 0%, rgba(42, 48, 82, 0.6) 100%);
            border-bottom: 1px solid rgba(110, 95, 155, 0.35);
        }
        .it-day-card__num {
            flex-shrink: 0;
            min-width: 3.25rem;
            height: 3.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Fraunces", Georgia, serif;
            font-size: 1.85rem;
            font-weight: 700;
            line-height: 1;
            color: #faf8ff;
            letter-spacing: -0.03em;
            border-radius: 16px;
            background: linear-gradient(145deg, rgba(110, 88, 168, 0.55) 0%, rgba(70, 58, 120, 0.75) 100%);
            border: 1px solid rgba(180, 165, 230, 0.35);
            box-shadow: 0 8px 28px rgba(40, 30, 80, 0.4);
        }
        .it-day-card__banner-text {
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
            min-width: 0;
        }
        .it-day-card__ribbon {
            margin: 0;
            font-size: var(--somnia-fs-cap);
            font-weight: 700;
            letter-spacing: 0.2em;
            text-transform: uppercase;
            color: #b8a8e8;
        }
        .it-day-card__sub {
            margin: 0;
            font-size: var(--somnia-fs-body);
            font-weight: 500;
            color: #d8dff5;
            letter-spacing: 0.01em;
        }
        .it-day-card__grid {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            padding: 1rem 1.15rem 1.15rem;
            width: 100%;
            box-sizing: border-box;
        }
        .it-day-panel {
            border-radius: 14px;
            border: 1px solid rgba(100, 90, 145, 0.28);
            background: rgba(18, 22, 38, 0.55);
            padding: 0.85rem 1rem 0.95rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
            width: 100%;
            box-sizing: border-box;
        }
        .it-day-panel__head {
            margin: 0 0 0.55rem;
            padding-bottom: 0.45rem;
            border-bottom: 1px solid rgba(90, 85, 130, 0.35);
        }
        .it-day-panel__label {
            display: block;
            font-size: var(--somnia-fs-cap);
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #c4b8f0;
        }
        .it-day-panel__body {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            width: 100%;
            max-width: none;
            min-width: 0;
        }
        .it-day-panel__spot {
            margin: 0 0 0.15rem;
            font-size: var(--somnia-fs-title);
            font-weight: 600;
            letter-spacing: -0.02em;
            color: #f4f2ff;
            line-height: 1.35;
            word-wrap: break-word;
            overflow-wrap: anywhere;
        }
        .it-day-lede {
            margin: 0;
            font-size: var(--somnia-fs-body);
            line-height: 1.58;
            color: #c5d4ec;
            font-weight: 400;
            max-width: none;
            width: 100%;
        }
        ul.it-day-bullets {
            margin: 0.35rem 0 0;
            padding-left: 1.15rem;
            color: #d0dcf0;
            line-height: 1.55;
            font-size: var(--somnia-fs-body);
            max-width: none;
            width: 100%;
            box-sizing: border-box;
        }
        ul.it-day-bullets li {
            margin-bottom: 0.45rem;
            padding-left: 0.15rem;
        }
        ul.it-day-bullets li:last-child { margin-bottom: 0; }
        .it-day-lede + .it-day-lede {
            margin-top: 0.45rem;
        }
        .it-day-bullet-para {
            margin: 0 0 0.38rem;
            font-size: inherit;
            line-height: inherit;
            color: inherit;
        }
        .it-day-bullet-para:last-child {
            margin-bottom: 0;
        }
        .day-card {
            border-radius: 22px;
            border: 1px solid rgba(110, 95, 155, 0.25);
            background: rgba(26, 30, 48, 0.58);
            box-shadow: 0 16px 44px rgba(0, 0, 0, 0.28);
            overflow: hidden;
            backdrop-filter: blur(12px);
        }
        .day-card__top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 1.2rem;
            background: linear-gradient(105deg, rgba(55, 48, 88, 0.45) 0%, rgba(38, 48, 78, 0.5) 100%);
            border-bottom: 1px solid rgba(100, 90, 140, 0.2);
        }
        .day-chip {
            font-size: var(--somnia-fs-cap);
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: none;
            color: #b8a8e8;
        }
        .day-card__body {
            padding: 1.05rem 1.25rem 1.15rem;
        }
        .it-block {
            padding-bottom: 1rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid rgba(90, 85, 130, 0.25);
        }
        .it-block:last-child {
            padding-bottom: 0;
            margin-bottom: 0;
            border-bottom: none;
        }
        .it-block__eyebrow {
            display: block;
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.06em;
            text-transform: none;
            font-weight: 700;
            color: #9aa8d0;
            margin-bottom: 0.4rem;
        }
        .it-block__title {
            margin: 0 0 0.35rem;
            font-size: var(--somnia-fs-title);
            font-weight: 600;
            letter-spacing: -0.02em;
            color: #f4f2ff;
            line-height: 1.28;
            word-wrap: break-word;
            overflow-wrap: anywhere;
        }
        .it-block__desc {
            margin: 0;
            font-size: var(--somnia-fs-body);
            line-height: 1.55;
            color: #aeb9dd;
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
            color: #b4c0df;
            line-height: 1.55;
            font-size: var(--somnia-fs-body);
        }
        ul.day-card__acts li { margin-bottom: 0.55rem; }
        ul.day-card__acts li:last-child { margin-bottom: 0; }
        .stay-stack {
            display: flex;
            flex-direction: column;
            gap: 1.1rem;
        }
        .stay-card {
            border-radius: 22px;
            border: 1px solid rgba(120, 100, 160, 0.28);
            background: linear-gradient(155deg, rgba(38, 34, 62, 0.65) 0%, rgba(28, 34, 54, 0.72) 100%);
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
            padding: 1.1rem 1.25rem 1.15rem;
            border-left: 4px solid rgba(140, 120, 200, 0.45);
            backdrop-filter: blur(12px);
        }
        .stay-card__head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }
        .stay-card__kicker {
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.06em;
            text-transform: none;
            font-weight: 700;
            color: #9aa8cc;
        }
        .stay-band-pill {
            flex-shrink: 0;
            font-size: var(--somnia-fs-cap);
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: none;
            padding: 0.28rem 0.55rem;
            border-radius: 999px;
            background: rgba(50, 48, 78, 0.75);
            border: 1px solid rgba(130, 115, 175, 0.35);
            color: #d4ccf0;
        }
        .stay-card__title {
            margin: 0;
            font-weight: 600;
            color: #f4f2ff;
            font-size: var(--somnia-fs-title);
            line-height: 1.3;
            letter-spacing: -0.02em;
            word-wrap: break-word;
            overflow-wrap: anywhere;
        }
        .stay-card__desc {
            margin: 0.5rem 0 0;
            color: #aeb9dd;
            font-size: var(--somnia-fs-body);
            line-height: 1.55;
            word-wrap: break-word;
            overflow-wrap: anywhere;
            display: -webkit-box;
            -webkit-line-clamp: 5;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .stay-card__why {
            margin: 0.45rem 0 0;
            font-size: var(--somnia-fs-body);
            line-height: 1.45;
            color: #c8b8ec;
            font-style: italic;
            opacity: 0.95;
            word-wrap: break-word;
            overflow-wrap: anywhere;
        }
        .prep-group-head {
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.06em;
            text-transform: none;
            font-weight: 700;
            color: #9aa8cc;
            margin: 0.95rem 0 0.4rem;
        }
        .prep-group-head--first {
            margin-top: 0.35rem;
        }
        .budget-card {
            border-radius: 22px;
            border: 1px solid rgba(110, 95, 155, 0.28);
            background: rgba(26, 30, 48, 0.62);
            padding: 1.1rem 1.2rem 1.15rem;
            box-shadow: 0 14px 42px rgba(0, 0, 0, 0.28);
            max-width: 560px;
            backdrop-filter: blur(12px);
        }
        .budget-card--breakdown {
            max-width: 640px;
        }
        .budget-head {
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.08em;
            text-transform: none;
            color: #9aa8cc;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }
        .budget-lede {
            margin: 0 0 0.65rem;
            font-size: var(--somnia-fs-body);
            font-weight: 400;
            color: #aeb9dd;
            line-height: 1.5;
        }
        .budget-table-wrap {
            border-radius: 16px;
            border: 1px solid rgba(100, 90, 140, 0.28);
            overflow: hidden;
            margin: 0.5rem 0 0.85rem;
            background: rgba(20, 24, 40, 0.45);
        }
        table.budget-table {
            width: 100%;
            border-collapse: collapse;
            font-size: var(--somnia-fs-body);
        }
        table.budget-table th {
            text-align: left;
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.06em;
            text-transform: none;
            font-weight: 700;
            color: #9aa8cc;
            padding: 0.55rem 0.75rem;
            background: rgba(36, 40, 62, 0.85);
            border-bottom: 1px solid rgba(90, 85, 130, 0.35);
        }
        table.budget-table th:last-child,
        table.budget-table td:last-child {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }
        table.budget-table td {
            padding: 0.5rem 0.75rem;
            color: #c8d2ec;
            border-bottom: 1px solid rgba(70, 65, 100, 0.25);
        }
        table.budget-table tbody tr:nth-child(even) td {
            background: rgba(32, 36, 56, 0.35);
        }
        table.budget-table tbody tr:last-child td {
            border-bottom: none;
        }
        table.budget-table td.budget-cat {
            font-weight: 500;
            color: #aeb9dd;
        }
        table.budget-table td.budget-amt {
            font-weight: 600;
            color: #f0ecff;
        }
        table.budget-table tfoot td {
            padding: 0.65rem 0.75rem;
            font-weight: 700;
            background: linear-gradient(120deg, rgba(55, 48, 88, 0.55) 0%, rgba(38, 48, 78, 0.55) 100%);
            border-top: 2px solid rgba(130, 110, 180, 0.35);
            border-bottom: none;
        }
        table.budget-table tfoot td.budget-cat {
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #c4b8e8;
        }
        table.budget-table tfoot td.budget-amt {
            font-size: var(--somnia-fs-title);
            color: #faf8ff;
        }
        .budget-tips {
            margin-top: 0.85rem;
            padding: 0.65rem 0.75rem;
            border-radius: 14px;
            background: rgba(36, 40, 62, 0.45);
            border: 1px solid rgba(100, 90, 140, 0.25);
        }
        .budget-tips__title {
            margin: 0 0 0.4rem;
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.06em;
            text-transform: none;
            font-weight: 700;
            color: #9aa8cc;
        }
        .budget-tips ul {
            margin: 0;
            padding-left: 1.05rem;
            color: #aeb9dd;
            font-size: var(--somnia-fs-body);
            line-height: 1.5;
        }
        .budget-tips li { margin-bottom: 0.3rem; }
        .budget-tip-em { font-weight: 600; color: #ddd4f8; }
        ul.budget-bits {
            margin: 0;
            padding-left: 1.1rem;
            color: #aeb9dd;
            font-size: var(--somnia-fs-body);
            line-height: 1.45;
        }
        ul.budget-bits li { margin-bottom: 0.25rem; }
        .budget-foot {
            font-size: 0.75rem;
            color: #7d8db0;
            margin: 0.65rem 0 0;
            line-height: 1.45;
        }
        .debug-section-head {
            font-size: var(--somnia-fs-section);
            font-weight: 600;
            letter-spacing: -0.01em;
            color: #e8e4fc;
            margin: 0.35rem 0 0.25rem;
        }
        .debug-block-title {
            font-size: var(--somnia-fs-cap);
            letter-spacing: 0.04em;
            text-transform: none;
            font-weight: 700;
            color: #9aa8cc;
            margin: 0.85rem 0 0.35rem;
        }
        div[data-testid="stMarkdownContainer"] p {
            line-height: 1.5;
        }
        div[data-testid="stAlert"] {
            background: rgba(36, 40, 62, 0.75) !important;
            border: 1px solid rgba(130, 110, 180, 0.3) !important;
            border-radius: 16px !important;
            color: #dce3f4 !important;
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.25);
        }
        section.main [data-testid="stJson"] {
            background: rgba(22, 26, 42, 0.65) !important;
            border: 1px solid rgba(100, 90, 140, 0.25) !important;
            border-radius: 12px !important;
        }
        section.main pre, section.main code {
            color: #c8d2ec !important;
            background: rgba(22, 26, 42, 0.55) !important;
            border: 1px solid rgba(100, 90, 140, 0.2) !important;
            border-radius: 10px !important;
        }
        hr.somnia-rule {
            border: none;
            height: 1px;
            margin: 0.15rem 0 1.5rem;
            background: linear-gradient(90deg, transparent, rgba(130, 110, 170, 0.35), transparent);
        }
        [data-testid="stHeader"] {
            background: rgba(14, 16, 26, 0.88) !important;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(90, 80, 130, 0.25);
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


PREP_LOGISTICS_KEY = "trip_logistics"
PACKING_GROUP_ORDER = ("essentials", "for_this_trip")
PREP_GROUP_LABELS = {
    PREP_LOGISTICS_KEY: "Before you go",
    "essentials": "Essentials",
    "for_this_trip": "For this trip",
}


def _prep_section_blocks(
    checklist: list[str], groups: dict[str, list[str]]
) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    if checklist:
        blocks.append((PREP_LOGISTICS_KEY, checklist))
    for gk in PACKING_GROUP_ORDER:
        items = groups.get(gk, [])
        if items:
            blocks.append((gk, items))
    return blocks


def _apply_prep_bulk_actions(fp: str, blocks: list[tuple[str, list[str]]]) -> None:
    #must run before prep_cb_* checkboxes mount; avoids streamlit's widget session write errors
    req = st.session_state.get("_prep_bulk")
    if not isinstance(req, dict) or str(req.get("fp", "")) != str(fp):
        return
    st.session_state.pop("_prep_bulk", None)
    mode = req.get("mode")
    if mode == "all":
        val = True
    elif mode == "clear":
        val = False
    else:
        return
    for group_id, items in blocks:
        for j in range(len(items)):
            st.session_state[f"prep_cb_{fp}_{group_id}_{j}"] = val


def _prep_widget_fingerprint(plan: dict, checklist: list[str], groups: dict[str, list[str]]) -> str:
    ordered = {k: groups[k] for k in PACKING_GROUP_ORDER if k in groups}
    blob = json.dumps(
        {
            "b": plan.get("budget"),
            "c": checklist,
            "d": plan.get("destination"),
            "g": ordered,
            "n": plan.get("num_days"),
            "v": plan.get("trip_vibe"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:18]


_BUDGET_OPTION_LABELS = {
    "budget": "Budget ($70–$120/day)",
    "mid": "Moderate ($130–$220/day)",
    "splurge": "Splurge ($250–$450/day)",
    "not sure": "Not sure (flexible)",
}

#shorter line for the trip pack header so it does not overflow on small widths
_BUDGET_META_SHORT = {
    "budget": "$70–120/day",
    "mid": "$130–220/day",
    "splurge": "$250–450/day",
    "not sure": "Not sure (flexible)",
}


def _budget_meta_line(raw: object) -> str:
    k = str(raw or "not sure").strip().lower()
    if k in _BUDGET_META_SHORT:
        return _BUDGET_META_SHORT[k]
    if k in _BUDGET_OPTION_LABELS:
        return _BUDGET_OPTION_LABELS[k]
    return str(raw or "not sure")

_DEBUG_ROLE_LABELS = {
    "see_do": "See / do",
    "eat": "Eat",
    "drink": "Drink",
    "sleep": "Sleep",
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


def _render_prep_and_packing_tab(plan: dict) -> None:
    st.markdown('<p class="prep-page-head">Trip prep & packing</p>', unsafe_allow_html=True)
    st.caption(
        "Trip logistics first, then packing. Each line reflects this destination, how many days you are "
        "going, your vibe, and your budget. Your checkmarks clear when you click Build my trip."
    )
    days = max(1, int(plan.get("num_days") or 1))
    checklist = build_checklist(
        str(plan.get("destination") or "your trip"),
        days,
        str(plan.get("trip_vibe") or ""),
        str(plan.get("budget") or "not sure"),
    )
    checklist = [str(x).strip() for x in checklist if not _blankish(x)]
    groups = _normalize_packing(plan.get("packing"))
    blocks = _prep_section_blocks(checklist, groups)
    if not blocks:
        st.info("No prep or packing lines for this trip yet.")
        return
    fp = _prep_widget_fingerprint(plan, checklist, groups)
    _apply_prep_bulk_actions(fp, blocks)
    total = sum(len(items) for _, items in blocks)
    first = True
    for group_id, items in blocks:
        label = PREP_GROUP_LABELS.get(group_id, group_id.replace("_", " "))
        head_cls = "prep-group-head prep-group-head--first" if first else "prep-group-head"
        first = False
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
                st.checkbox(item, key=f"prep_cb_{fp}_{group_id}_{i}")
    done = sum(
        1
        for gid, items in blocks
        for j in range(len(items))
        if st.session_state.get(f"prep_cb_{fp}_{gid}_{j}", False)
    )
    st.progress(min(1.0, done / max(1, total)))
    st.caption(f"{done} of {total} done")
    try:
        _sp, tray = st.columns([11, 3], gap="small")
    except TypeError:
        _sp, tray = st.columns([11, 3])
    with _sp:
        pass
    with tray:
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Mark all done", key=f"prep_all_{fp}", use_container_width=False):
                st.session_state["_prep_bulk"] = {"fp": fp, "mode": "all"}
                st.rerun()
        with c2:
            if st.button("Clear ticks", key=f"prep_reset_{fp}", use_container_width=False):
                st.session_state["_prep_bulk"] = {"fp": fp, "mode": "clear"}
                st.rerun()


def _normalize_plan_section(raw: object) -> tuple[str, list[str]]:
    if isinstance(raw, dict):
        intro = str(raw.get("intro") or "").strip()
        items = raw.get("bullets")
        if items is None:
            items = raw.get("items") or []
        if not isinstance(items, list):
            items = []
        bullets = [str(x).strip() for x in items if x and str(x).strip()]
        return intro, bullets
    if isinstance(raw, list):
        return "", [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        return ("", [s]) if s else ("", [])
    return "", []


def _split_into_paragraph_chunks(text: str, max_chars: int = 280) -> list[str]:
    #break long blurbs on sentence-ish boundaries so the eye gets resting spots
    text = str(text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    if not parts:
        return [text]
    out: list[str] = []
    buf = ""
    for p in parts:
        cand = f"{buf} {p}".strip() if buf else p
        if len(cand) <= max_chars:
            buf = cand
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    #one monster sentence still happens sometimes—slice on spaces so lines breathe
    refined: list[str] = []
    for chunk in out:
        c = chunk.strip()
        if not c:
            continue
        while len(c) > max_chars:
            window = c[:max_chars]
            br = window.rfind(" ")
            cut = br if br > max_chars // 3 else max_chars
            refined.append(c[:cut].strip())
            c = c[cut:].strip()
        if c:
            refined.append(c)
    return refined


def _intro_ledes_html(intro: str) -> str:
    chunks = _split_into_paragraph_chunks(intro)
    return "".join(f'<p class="it-day-lede">{_h(c)}</p>' for c in chunks)


def _bullets_html(bullets: list[str]) -> str:
    lis: list[str] = []
    for b in bullets:
        chunks = _split_into_paragraph_chunks(b, max_chars=260)
        if len(chunks) <= 1:
            lis.append(f"<li>{_h(b)}</li>")
        else:
            inner = "".join(f'<p class="it-day-bullet-para">{_h(c)}</p>' for c in chunks)
            lis.append(f"<li>{inner}</li>")
    return f'<ul class="it-day-bullets">{"".join(lis)}</ul>'


def _day_plan_panel_html(label: str, section: object) -> str:
    intro, bullets = _normalize_plan_section(section)
    body_inner: list[str] = []
    if intro:
        body_inner.append(_intro_ledes_html(intro))
    if bullets:
        body_inner.append(_bullets_html(bullets))
    if not body_inner:
        return ""
    return (
        '<article class="it-day-panel">'
        f'<header class="it-day-panel__head"><span class="it-day-panel__label">{_h(label)}</span></header>'
        f'<div class="it-day-panel__body">{"".join(body_inner)}</div>'
        "</article>"
    )


def _legacy_plan_panel(label: str, title: str, desc: str) -> str:
    if _blankish(title) and _blankish(desc):
        return ""
    spot = f'<p class="it-day-panel__spot">{_h(title)}</p>' if not _blankish(title) else ""
    desc_html = _intro_ledes_html(desc) if not _blankish(desc) else ""
    inner = f"{spot}{desc_html}"
    return (
        '<article class="it-day-panel">'
        f'<header class="it-day-panel__head"><span class="it-day-panel__label">{_h(label)}</span></header>'
        f'<div class="it-day-panel__body">{inner}</div>'
        "</article>"
    )


def _legacy_day_body_html(block: dict) -> str:
    mt = _ui_title(block.get("main_activity_title"), fallback="See & do")
    md = _ui_blurb(block.get("main_activity_description"))
    ft = _ui_title(block.get("food_title"), fallback="Eat locally")
    fd = _ui_blurb(block.get("food_description"))
    dt = _ui_title(block.get("drink_title"), fallback="")
    dd = _ui_blurb(block.get("drink_description"))
    see_html = _legacy_plan_panel("See / do", mt, md)
    eat_html = _legacy_plan_panel("Food", ft, fd)
    drink_html = ""
    if not _blankish(dt) or dd:
        dtitle = dt if not _blankish(dt) else "Drinks"
        drink_html = _legacy_plan_panel("Drink", dtitle, dd)
    return f"{see_html}{eat_html}{drink_html}"


def _it_day_details_html(day: int, total_days: int, inner: str, *, open_default: bool) -> str:
    #native details so the purple banner is the only tap target (no duplicate streamlit label)
    td = max(1, int(total_days))
    sub = f"Day {day} of {td}"
    open_attr = " open" if open_default else ""
    return (
        f'<details class="it-day-card-outer it-day-expand"{open_attr}>'
        '<summary class="it-day-card__banner it-day-expand__summary">'
        f'<span class="it-day-card__num">{int(day)}</span>'
        '<div class="it-day-card__banner-text">'
        '<p class="it-day-card__ribbon">Itinerary</p>'
        f'<p class="it-day-card__sub">{_h(sub)}</p>'
        "</div>"
        '<span class="it-day-expand__chev" aria-hidden="true">▾</span>'
        "</summary>"
        f'<div class="it-day-card__grid">{inner}</div>'
        "</details>"
    )


def _detailed_day_body_html(block: dict) -> str:
    return (
        _day_plan_panel_html("Morning", block.get("morning_plan"))
        + _day_plan_panel_html("Afternoon", block.get("afternoon_plan"))
        + _day_plan_panel_html("Evening", block.get("evening_plan"))
        + _day_plan_panel_html("Food", block.get("food_plan"))
        + _day_plan_panel_html("Notes", block.get("optional_notes"))
    )


def _budget_breakdown_card_html(plan: dict, bd: dict) -> str:
    #mini table inside the card so numbers line up and scan like finance ui
    specs = (
        ("Lodging", "lodging_estimate"),
        ("Food", "food_estimate"),
        ("Transit", "transit_estimate"),
        ("Activities", "activities_estimate"),
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
        "<p class='budget-tips__title'>How to use these numbers</p>"
        "<ul>"
        "<li><span class='budget-tip-em'>Lodging ÷ nights</span> ≈ a nightly hotel filter to stay inside this trip shape.</li>"
        "<li><span class='budget-tip-em'>Food ÷ days</span> ≈ a loose daily meals + snacks ceiling (coffee counts).</li>"
        "<li><span class='budget-tip-em'>Transit + activities</span> are usually the first place to rebalance if one category runs hot.</li>"
        f"<li><span class='budget-tip-em'>Total</span> sums the four rows. Use it to sanity-check major bookings against ${tlo:,}–${thi:,} before you lock dates.</li>"
        "</ul></div>"
    )
    summary = _h(str(plan.get("budget_summary", "")))
    table = (
        '<div class="budget-table-wrap">'
        '<table class="budget-table">'
        "<thead><tr><th>Category</th><th>Trip estimate (USD)</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "<tfoot><tr>"
        '<td class="budget-cat">Total</td>'
        f'<td class="budget-amt">${tlo:,}–${thi:,}</td>'
        "</tr></tfoot></table></div>"
    )
    foot = (
        "<p class='budget-foot'>"
        "Rule-based model · excludes flights and major tours · "
        "Unknown cities use a neutral cost factor (1.0) · "
        f"Shown for {days} {'days' if days != 1 else 'day'}"
        "</p>"
    )
    return (
        '<div class="budget-card budget-card--breakdown">'
        '<div class="budget-head">Estimates by category</div>'
        f'<p class="budget-lede">{summary}</p>'
        f"{table}{tips}{foot}</div>"
    )


def somnia_landing() -> None:
    #full-viewport hero + in-page anchor to trip form (same url, no new tab)
    st.markdown(
        """
        <div class="somnia-hero">
            <div class="somnia-cloud somnia-cloud--1"></div>
            <div class="somnia-cloud somnia-cloud--2"></div>
            <div class="somnia-cloud somnia-cloud--3"></div>
            <div class="somnia-hero-inner">
                <p class="somnia-brand">Somnia</p>
                <h1 class="somnia-title">Somnia Travel Planner</h1>
                <a class="somnia-hero-cta" href="#somnia-trip-form" target="_self" aria-label="Scroll to trip planning form">Start planning your dream vacation</a>
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
    st.markdown('<p class="debug-section-head">Debug info</p>', unsafe_allow_html=True)
    st.caption(
        "Compare ranking queries with the top rows to see how the embedder ordered results. Rebuild after toggling this option to refresh snapshots."
    )

    sup = plan.get("supported_destinations") or []
    st.markdown('<p class="debug-block-title">Supported destinations</p>', unsafe_allow_html=True)
    st.code("\n".join(str(x) for x in sup) if sup else "(empty dataset list)", language=None)

    dbg = plan.get("debug")
    if not isinstance(dbg, dict):
        st.info(
            'Turn on this checkbox, then click "Build my trip", to attach ranking snapshots from the planner.'
        )
        return

    st.markdown('<p class="debug-block-title">Ranking queries (embed input per slice)</p>', unsafe_allow_html=True)
    rq = dbg.get("ranking_queries") or {}
    if isinstance(rq, dict) and rq:
        for role in ("see_do", "eat", "drink", "sleep"):
            q = rq.get(role, "")
            label = _DEBUG_ROLE_LABELS.get(role, role)
            st.markdown(f"**{label}**")
            st.code(q if q else "(empty)", language=None)
    else:
        st.caption("This snapshot has no saved ranking queries yet.")

    st.markdown('<p class="debug-block-title">Top raw matches → itinerary pools</p>', unsafe_allow_html=True)
    st.caption(
        "The same ranked row lists the planner feeds into _build_itinerary_days, shown here before card copy runs."
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**See / do**")
        st.json(dbg.get("top_see_do", []))
    with c2:
        st.markdown("**Eat**")
        st.json(dbg.get("top_eat", []))
    with c3:
        st.markdown("**Drink**")
        st.json(dbg.get("top_drink", []))

    st.markdown('<p class="debug-block-title">Top raw hotel matches (sleep pool)</p>', unsafe_allow_html=True)
    st.json(dbg.get("top_hotel_rows", []))

    n = dbg.get("scoped_row_count")
    if n is not None:
        st.caption(f"Rows in dataset for this destination (scoped): {n}")


def render_plan(plan: dict) -> None:
    #escape after we normalize so angle brackets from wiki text cannot break layout
    reveal = st.session_state.pop("somnia_reveal_once", False)
    reveal_cls = " somnia-results-reveal" if reveal else ""
    dest = html.escape(str(plan["destination"]))
    vibe = html.escape(str(plan["trip_vibe"]) or "Not set")
    bud = html.escape(_budget_meta_line(plan.get("budget")))
    try:
        nd = max(1, int(plan.get("num_days") or 0))
    except (TypeError, ValueError):
        nd = 0
    days_label = html.escape(f"{nd} day" + ("" if nd == 1 else "s")) if nd else "—"

    st.markdown(
        f'<div class="somnia-results-anchor{reveal_cls}">'
        '<p class="somnia-results-kicker">Your travel plan</p>'
        '<h2 class="somnia-trip-summary-title">Trip Summary</h2>'
        '<div class="trip-meta-card">'
        f'<div class="trip-meta-block"><span>Destination</span><strong>{dest}</strong></div>'
        f'<div class="trip-meta-block"><span>Trip length</span><strong>{days_label}</strong></div>'
        f'<div class="trip-meta-block"><span>Vibe · budget</span><strong>{vibe} · {bud}</strong></div>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    if plan.get("notice"):
        st.warning(html.escape(str(plan["notice"])))
    if not plan.get("ok", True) and plan.get("supported_destinations"):
        sup = ", ".join(html.escape(x) for x in plan["supported_destinations"])
        st.caption(f"Supported destinations in dataset: {sup}")

    tab_prep, tab2, tab3, tab4 = st.tabs(["Prep & packing", "Itinerary", "Hotels", "Budget"])

    with tab_prep:
        _render_prep_and_packing_tab(plan)

    with tab2:
        if not plan.get("itinerary"):
            st.info(plan.get("notice") or "No itinerary built for this trip yet.")
        else:
            st.caption("Tap the purple day header to expand or collapse.")
            itin = plan["itinerary"]
            total_days = max(
                int(plan.get("num_days") or 0),
                len(itin),
                max((int(b["day"]) for b in itin), default=0),
            )
            for block in itin:
                day = int(block["day"])
                inner = (
                    _detailed_day_body_html(block)
                    if "morning_plan" in block
                    else _legacy_day_body_html(block)
                )
                block_html = _it_day_details_html(day, total_days, inner, open_default=(day == 1))
                st.markdown(block_html, unsafe_allow_html=True)

    with tab3:
        stay_note = plan.get("stay_suggestions_notice")
        if stay_note:
            st.info(str(stay_note))
        if not plan.get("stays"):
            if not stay_note:
                st.caption("No sleep rows passed the stay filter for this city yet.")
        else:
            cards: list[str] = []
            for stay in plan["stays"]:
                title = _ui_title(stay.get("title"), fallback="Suggested stay")
                desc = _ui_blurb(stay.get("description", stay.get("note", "")))
                why_raw = stay.get("match_reason", "")
                why = _ui_blurb(why_raw) if not _blankish(why_raw) else ""
                band_raw = stay.get("estimated_cost_band", "") or "unknown"
                band = "unknown" if _blankish(band_raw) else str(band_raw).strip()
                band_label = "Unknown" if band.casefold() == "unknown" else band.replace("_", " ").title()
                desc_block = f'<p class="stay-card__desc">{_h(desc)}</p>' if desc else ""
                why_block = f'<p class="stay-card__why">{_h(why)}</p>' if why else ""
                cards.append(
                    f'<article class="stay-card">'
                    f'<div class="stay-card__head">'
                    f'<span class="stay-card__kicker">Hotel</span>'
                    f'<span class="stay-band-pill">{_h(band_label)}</span></div>'
                    f'<h3 class="stay-card__title">{_h(title)}</h3>{desc_block}{why_block}'
                    f"</article>"
                )
            st.markdown(f'<div class="stay-stack">{"".join(cards)}</div>', unsafe_allow_html=True)

    with tab4:
        st.markdown('<p class="budget-page-head">Trip budget</p>', unsafe_allow_html=True)
        st.caption(
            "USD ranges cover the whole trip. Use the table to sanity-check filters before you book; it is not a quote."
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
                    <div class="budget-head">Rough estimate</div>
                    <p class="budget-lede">{summary}</p>
                    <ul class="budget-bits">{bits}</ul>
                    <p class="budget-foot">Rebuild the trip to see the category breakdown.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    _render_debug_section(plan)


def main() -> None:
    #single-column dreamscape: trip inputs live in one st.form directly under the hero
    st.set_page_config(
        page_title="Somnia Travel Planner",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_styles()
    somnia_landing()

    cities = supported_destinations()
    st.markdown(
        '<div id="somnia-trip-form" class="somnia-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    with st.form("somnia_trip", clear_on_submit=False):
        st.markdown(
            '<p class="somnia-form-eyebrow">Tell us about your trip</p>',
            unsafe_allow_html=True,
        )
        if cities:
            n = len(cities)
            if n == 1:
                note = (
                    '<p class="somnia-dataset-note">This dataset supports travel planning for '
                    "<strong>1</strong> city destination.</p>"
                )
            else:
                note = (
                    '<p class="somnia-dataset-note">This dataset supports travel planning for '
                    f"<strong>{n}</strong> city destinations.</p>"
                )
            st.markdown(note, unsafe_allow_html=True)
        else:
            st.markdown(
                '<p class="somnia-dataset-note">No cities in travel_dataset.csv yet. Run scraper.py, then build_dataset.py.</p>',
                unsafe_allow_html=True,
            )
        if cities:
            destination = st.selectbox(
                "Destination",
                options=cities,
                index=0,
                help="Only cities that survived the scrape and dataset filters.",
            )
        else:
            st.selectbox(
                "Destination",
                options=["(Add data first)"],
                disabled=True,
                help="Build travel_dataset.csv before this unlocks.",
            )
            destination = ""
        num_days = st.number_input("Number of days", min_value=1, max_value=21, value=4, step=1)
        trip_vibe = st.text_input(
            "Trip vibe", placeholder="e.g. slow food days + a little nightlife"
        )
        budget = st.selectbox(
            "Budget (daily ballpark)",
            options=["budget", "mid", "splurge", "not sure"],
            index=3,
            format_func=lambda k: _BUDGET_OPTION_LABELS.get(k, k),
            help=(
                "Rough per-day spending feel on the ground (lodging, meals, local transit, activities). "
                "Flights and big tours are not baked into these bands."
            ),
        )
        must_see = st.text_area(
            "Must-see interests",
            placeholder="Temples, vinyl shopping, kid-friendly museums…",
            height=110,
        )
        submitted = st.form_submit_button(
            "Build my trip",
            type="primary",
            use_container_width=True,
            disabled=not cities,
        )

    st.checkbox(
        "Show debug info",
        value=False,
        key="show_debug_info",
        help="After build: show destinations, embed queries, and top raw rows for itinerary and hotels.",
    )

    if submitted and cities:
        load_slot = st.empty()
        load_slot.markdown(SOMNIA_LOADER_HTML, unsafe_allow_html=True)
        t0 = time.perf_counter()
        plan = get_recommendations(
            destination=destination,
            num_days=int(num_days),
            trip_vibe=trip_vibe,
            budget=budget,
            must_see_interests=must_see,
            debug=st.session_state.get("show_debug_info", False),
        )
        elapsed = time.perf_counter() - t0
        remainder = 3.0 - elapsed
        if remainder > 0:
            time.sleep(remainder)
        load_slot.empty()
        st.session_state["last_plan"] = plan
        st.session_state["somnia_reveal_once"] = True

    if st.session_state["last_plan"]:
        render_plan(st.session_state["last_plan"])


main()
