"""Light/dark-hybrid styling shared across the app: CSS injection, SVG art
generators and hero/ticker helpers."""
import base64
from typing import Optional

import streamlit as st

# Validated categorical palette (CVD-safe adjacent pairs).
CHART_COLORS = [
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#008300",  # green
    "#9085e9",  # violet
    "#e66767",  # red
]

SURFACE = "#0f172a"
PAGE_BG = "#0b1220"
GRIDLINE = "#1e293b"
INK_PRIMARY = "#e2e8f0"
INK_MUTED = "#94a3b8"
GOOD = "#4ade80"
BAD = "#f87171"

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK_PRIMARY, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
    xaxis=dict(gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor=GRIDLINE),
    yaxis=dict(gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor=GRIDLINE),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
    margin=dict(l=10, r=10, t=40, b=10),
)


# --- SVG image generators (inline, no files needed) ----------------------

def _svg_uri(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def chart_svg() -> str:
    """Decorative hero illustration: a glowing rising-market chart."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="520" height="300" viewBox="0 0 520 300">'
        "<defs>"
        '<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#67e8f9" stop-opacity="0.45"/>'
        '<stop offset="100%" stop-color="#a78bfa" stop-opacity="0.02"/>'
        "</linearGradient>"
        '<linearGradient id="stroke" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#67e8f9"/>'
        '<stop offset="100%" stop-color="#a78bfa"/>'
        "</linearGradient>"
        '<radialGradient id="coin" cx="50%" cy="40%" r="60%">'
        '<stop offset="0%" stop-color="#fde68a"/>'
        '<stop offset="100%" stop-color="#f59e0b"/>'
        "</radialGradient>"
        "</defs>"
        '<rect width="520" height="300" rx="22" fill="rgba(255,255,255,0.04)"/>'
        '<g stroke="rgba(255,255,255,0.07)" stroke-width="1">'
        '<line x1="40" y1="60" x2="480" y2="60"/><line x1="40" y1="120" x2="480" y2="120"/>'
        '<line x1="40" y1="180" x2="480" y2="180"/><line x1="40" y1="240" x2="480" y2="240"/>'
        '<line x1="120" y1="30" x2="120" y2="270"/><line x1="240" y1="30" x2="240" y2="270"/>'
        '<line x1="360" y1="30" x2="360" y2="270"/>'
        "</g>"
        '<path d="M40,240 C100,220 130,180 150,170 S220,180 270,120 S330,140 390,80 '
        'S440,100 460,95 L460,270 L40,270 Z" fill="url(#fill)"/>'
        '<path d="M40,240 C100,220 130,180 150,170 S220,180 270,120 S330,140 390,80 '
        'S440,100 460,95" fill="none" stroke="url(#stroke)" stroke-width="4" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<g stroke="rgba(255,255,255,0.85)" stroke-width="2">'
        '<circle cx="270" cy="120" r="6" fill="#67e8f9"/>'
        '<circle cx="390" cy="80" r="6" fill="#a78bfa"/>'
        "</g>"
        '<line x1="60" y1="200" x2="150" y2="120" stroke="#e66767" stroke-width="3" stroke-linecap="round"/>'
        '<line x1="90" y1="196" x2="60" y2="200" stroke="#e66767" stroke-width="3" stroke-linecap="round"/>'
        '<line x1="90" y1="196" x2="60" y2="200" stroke="#e66767" stroke-width="3" stroke-linecap="round"/>'
        '<rect x="205" y="60" width="10" height="30" rx="3" fill="#34d399"/>'
        '<line x1="210" y1="45" x2="210" y2="95" stroke="#34d399" stroke-width="2"/>'
        '<rect x="233" y="78" width="10" height="26" rx="3" fill="#e66767"/>'
        '<line x1="238" y1="65" x2="238" y2="112" stroke="#e66767" stroke-width="2"/>'
        '<rect x="375" y="42" width="10" height="22" rx="3" fill="#34d399"/>'
        '<line x1="380" y1="30" x2="380" y2="72" stroke="#34d399" stroke-width="2"/>'
        '<circle cx="78" cy="66" r="24" fill="url(#coin)"/>'
        '<text x="78" y="74" font-family="Arial, sans-serif" font-size="26" font-weight="800" '
        'fill="#92400e" text-anchor="middle">$</text>'
        '<circle cx="462" cy="214" r="15" fill="url(#coin)" opacity="0.9"/>'
        '<text x="462" y="221" font-family="Arial, sans-serif" font-size="16" font-weight="800" '
        'fill="#92400e" text-anchor="middle">$</text>'
        "</svg>"
    )
    return _svg_uri(svg)


def spark_svg(width: int = 110, height: int = 36, color: str = "#3987e5", accent: str = "#d55181") -> str:
    """Small glowing sparkline used as a decorative section image."""
    data = [26, 19, 22, 12, 15, 6, 8, 4]
    n = len(data)
    xs = [width * i / (n - 1) for i in range(n)]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, data))
    area = "M0,{h} L{xs} L{width},{h} Z".format(
        h=height, xs=" L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, data)), width=width
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        "<defs>"
        f'<linearGradient id="sp" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        "</linearGradient>"
        "</defs>"
        f'<path d="{area}" fill="url(#sp)"/>'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{width}" cy="{data[-1]}" r="3.5" fill="{accent}"/>'
        "</svg>"
    )
    return _svg_uri(svg)


def section_chip() -> str:
    """Subtle gradient accent tile placed before a section heading."""
    return '<span class="section-chip"></span>'


def hero_html(title: str, subtitle: str) -> str:
    """Animated hero banner with gradient title and floating chart art."""
    art = chart_svg()
    return (
        '<div class="hero">'
        '<div class="hero-glow hero-glow-a"></div>'
        '<div class="hero-glow hero-glow-b"></div>'
        '<div class="hero-text">'
        '<div class="hero-eyebrow">Paw Coders · Quant Portfolio Suite</div>'
        f"<h1 class=\"hero-title\">{title}</h1>"
        f'<p class="hero-sub">{subtitle}</p>'
        "</div>"
        f'<img class="hero-art" src="{art}" alt="market illustration"/>'
        "</div>"
    )


def ticker_html(items: list[tuple[str, str]]) -> str:
    """Scrolling live-price marquee (items are (symbol, price-string))."""
    cells = "".join(
        f'<span class="ticker-item"><b>{symbol}</b>&nbsp;&nbsp;{price}</span>' for symbol, price in items
    )
    return f'<div class="ticker-wrap"><div class="ticker">{cells}{cells}</div></div>'


# --- CSS -----------------------------------------------------------------

def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{ color-scheme: dark; }}

        [data-testid="stAppViewContainer"] {{
            background:
                radial-gradient(1200px 620px at 85% -10%, rgba(109,40,217,0.18), transparent 60%),
                radial-gradient(900px 520px at -10% 25%, rgba(57,135,229,0.14), transparent 55%),
                linear-gradient(135deg, #0b1220 0%, #0f1b33 100%);
            color: {INK_PRIMARY};
        }}
        [data-testid="stHeader"] {{ background: rgba(11,18,32,0.7); backdrop-filter: blur(6px); }}

        /* --- Scrollbar ------------------------------------------------ */
        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 6px; border: 2px solid transparent; background-clip: content-box; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #475569; background-clip: content-box; border: 2px solid transparent; }}

        /* --- Hero banner ---------------------------------------------- */
        .hero {{
            position: relative;
            display: flex; align-items: center; justify-content: space-between; gap: 2rem;
            background: linear-gradient(120deg, #0f172a 0%, #312e81 52%, #701a75 100%);
            border-radius: 22px;
            padding: 2.1rem 2.4rem;
            margin: 0.3rem 0 1.2rem;
            overflow: hidden;
            box-shadow: 0 18px 44px rgba(49,46,129,0.35);
        }}
        .hero-glow {{ position: absolute; border-radius: 50%; filter: blur(58px); opacity: 0.55; pointer-events: none; }}
        .hero-glow-a {{ width: 330px; height: 330px; background: #4f46e5; top: -130px; left: -70px; animation: drift 9s ease-in-out infinite; }}
        .hero-glow-b {{ width: 270px; height: 270px; background: #db2777; bottom: -120px; right: 170px; animation: drift 12s ease-in-out infinite reverse; }}
        .hero-text {{ position: relative; z-index: 2; max-width: 660px; }}
        .hero-eyebrow {{
            display: inline-flex; align-items: center;
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.25);
            border-radius: 999px; padding: 0.32rem 0.95rem;
            color: #e9d5ff; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em;
            backdrop-filter: blur(6px);
        }}
        .hero-title {{
            margin: 0.85rem 0 0.45rem; font-size: 2.7rem; font-weight: 800; line-height: 1.08;
            background: linear-gradient(90deg, #ffffff 0%, #c7d2fe 55%, #fbcfe8 100%);
            -webkit-background-clip: text; background-clip: text; color: transparent;
        }}
        .hero-sub {{ color: #c7d2fe; font-size: 1.05rem; margin: 0; }}
        .hero-art {{
            position: relative; z-index: 2;
            width: min(46%, 520px); min-width: 300px;
            animation: bob 6s ease-in-out infinite;
            filter: drop-shadow(0 16px 34px rgba(0,0,0,0.35));
        }}
        @keyframes drift {{ 0%,100% {{ transform: translate(0,0); }} 50% {{ transform: translate(32px,22px); }} }}
        @keyframes bob {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
        @media (max-width: 900px) {{
            .hero-art {{ display: none; }}
            .hero-title {{ font-size: 1.9rem; }}
        }}

        /* --- Ticker marquee ------------------------------------------- */
        .ticker-wrap {{
            position: relative; overflow: hidden; border-radius: 14px;
            background: linear-gradient(90deg, #0f172a, #1e293b);
            border: 1px solid rgba(148,163,184,0.22);
            margin-bottom: 1.1rem;
            box-shadow: 0 8px 22px rgba(15,23,42,0.18);
        }}
        .ticker {{ display: inline-flex; white-space: nowrap; padding: 0.6rem 0; animation: ticker 42s linear infinite; }}
        .ticker:hover {{ animation-play-state: paused; }}
        .ticker-item {{ margin-right: 2.6rem; color: #94a3b8; font-size: 0.92rem; }}
        .ticker-item b {{ color: #ffffff; }}
        .ticker-item::after {{ content: "●"; margin-left: 1.35rem; color: #f59e0b; font-size: 0.6rem; vertical-align: middle; }}
        @keyframes ticker {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}

        /* --- Sidebar (dark glass) -------------------------------------- */
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0b1220 0%, #14243d 100%);
            border-right: 1px solid rgba(148,163,184,0.18);
        }}
        [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: #f1f5f9; }}
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
            color: #cbd5e1;
        }}
        [data-testid="stSidebar"] hr {{ border-color: #334155; }}
        [data-testid="stSidebar"] .stTextInput input, [data-testid="stSidebar"] .stNumberInput input {{
            background: #1e293b; color: #f1f5f9; border: 1px solid #334155; border-radius: 10px;
        }}
        [data-testid="stSidebar"] [data-baseweb="select"] > div {{
            background: #1e293b; color: #f1f5f9; border-color: #334155; border-radius: 10px;
        }}
        [data-testid="stSidebar"] [data-baseweb="select"] > div * {{ color: #f1f5f9; }}
        [data-testid="stSidebar"] .stButton > button {{
            background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 10px;
        }}
        [data-testid="stSidebar"] .stButton > button:hover {{ border-color: #3987e5; color: #ffffff; }}

        .sidebar-brand {{
            background: linear-gradient(120deg, #3987e5, #6d28d9);
            border-radius: 14px; padding: 0.9rem 1rem; margin-bottom: 1rem;
            color: #ffffff; font-weight: 800; font-size: 1.05rem;
            box-shadow: 0 8px 20px rgba(57,135,229,0.4);
        }}
        .sidebar-brand span {{ display: block; font-size: 0.72rem; font-weight: 600; color: #dbeafe; margin-top: 0.18rem; letter-spacing: 0.06em; }}

        /* --- Metric cards --------------------------------------------- */
        [data-testid="stMetric"] {{
            background: rgba(15,23,42,0.75);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 16px;
            padding: 0.9rem 1.1rem;
            box-shadow: 0 6px 18px rgba(0,0,0,0.35);
            position: relative; overflow: hidden;
        }}
        [data-testid="stMetric"]::before {{
            content: "";
            position: absolute; left: 0; right: 0; top: 0; height: 4px;
            background: linear-gradient(90deg, #3987e5, #d55181, #f59e0b);
        }}
        [data-testid="stMetricLabel"] p {{ color: {INK_MUTED}; font-weight: 600; }}
        [data-testid="stMetricValue"] {{ font-weight: 800; }}
        [data-testid="stMetricDelta"] {{ font-weight: 600; }}

        /* --- Tabs ------------------------------------------------------- */
        [data-testid="stTabs"] [data-baseweb="tab-list"] {{
            background: rgba(15,23,42,0.7);
            border: 1px solid rgba(51,65,85,0.9);
            border-radius: 14px; padding: 6px; gap: 4px;
        }}
        [data-testid="stTabs"] [data-baseweb="tab"] {{
            border-radius: 10px; font-weight: 600; color: #cbd5e1; padding: 8px 18px;
        }}
        [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
            background: linear-gradient(135deg, #3987e5, #6d28d9);
            color: #ffffff;
            box-shadow: 0 4px 14px rgba(57,135,229,0.35);
        }}

        /* --- Buttons ----------------------------------------------------- */
        .stButton > button, .stFormSubmitButton > button,
        [data-testid="stBaseButton-secondary"], [data-testid="baseButton-secondary"] {{
            border-radius: 10px; font-weight: 600;
            border: 1px solid #334155; background: #1e293b; color: #e2e8f0;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            transition: all 0.18s ease;
        }}
        .stButton > button:hover, .stFormSubmitButton > button:hover,
        [data-testid="stBaseButton-secondary"]:hover, [data-testid="baseButton-secondary"]:hover {{
            border-color: #3987e5; color: #ffffff; transform: translateY(-1px);
            box-shadow: 0 6px 14px rgba(57,135,229,0.25);
        }}
        [data-testid="stBaseButton-primary"], [data-testid="baseButton-primary"] {{
            background: linear-gradient(135deg, #3987e5 0%, #6d28d9 100%);
            color: #ffffff; border: none;
            box-shadow: 0 6px 16px rgba(109,40,217,0.35);
        }}
        [data-testid="stBaseButton-primary"]:hover, [data-testid="baseButton-primary"]:hover {{
            transform: translateY(-1px); color: #ffffff;
            box-shadow: 0 8px 22px rgba(109,40,217,0.45);
        }}

        /* --- Inputs ------------------------------------------------------ */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input,
        .stSelectbox > div > div > div,
        .stTextArea > div > div > textarea {{
            background-color: {SURFACE};
            color: {INK_PRIMARY};
            border: 1px solid #334155;
            border-radius: 10px;
        }}
        .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {{
            border-color: #3987e5;
        }}
        [data-baseweb="popover"] [data-baseweb="menu"] {{
            background: #1e293b;
        }}
        [data-baseweb="popover"] [data-baseweb="menu"] li {{ color: #e2e8f0; }}
        [data-baseweb="popover"] [data-baseweb="menu"] li[aria-selected="true"] {{ background: #334155; }}

        /* --- Base text ------------------------------------------------------ */
        h1, h2, h3, h4, h5, h6, p, li, label {{ color: {INK_PRIMARY}; }}

        /* --- DataFrames --------------------------------------------------- */
        [data-testid="stDataFrame"] {{
            border-radius: 14px;
            border: 1px solid #1e293b;
            box-shadow: 0 6px 18px rgba(0,0,0,0.35);
            overflow: hidden;
        }}

        /* --- Expanders ----------------------------------------------------- */
        [data-testid="stExpander"] {{
            border: 1px solid #1e293b;
            border-radius: 14px;
            background: rgba(15,23,42,0.7);
            box-shadow: 0 4px 14px rgba(0,0,0,0.3);
        }}

        /* --- Section chips -------------------------------------------------- */
        .section-chip {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 2.05rem; height: 2.05rem; border-radius: 12px; margin-right: 0.55rem;
            background: linear-gradient(135deg, #3987e5, #6d28d9);
            box-shadow: 0 4px 10px rgba(57,135,229,0.32);
            font-size: 1rem;
            vertical-align: -0.35rem;
        }}

        /* --- Alerts --------------------------------------------------------- */
        [data-testid="stAlert"] {{ border-radius: 12px; }}

        /* --- Block spacing ---------------------------------------------------- */
        .block-container {{ padding-top: 1.2rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
