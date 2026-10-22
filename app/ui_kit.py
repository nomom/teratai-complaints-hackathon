"""Owner: C. Design system for the ops console: light and dark token sets, one CSS block, and small HTML helpers.

Rules the helpers enforce:
- ~90% neutrals, one violet accent for action/selection, status colours only where they carry meaning
- status is never colour alone: every badge has an icon and a text label
- money is tabular, right-aligned in tables, two decimals, "RM" prefix
Everything user-supplied goes through esc() before it is put into HTML.

THEMING
Streamlit can't switch config.toml at runtime, so .streamlit/config.toml is the dark baseline and get_theme_css()
injects one token set (dark or light) plus the shared component CSS, which uses tokens only, never hex values.
The choice lives in st.session_state["theme"] ("dark" by default).

TOKENS (use these in any new component CSS as var(--name))
  Surfaces      --bg --surface --row-alt --elevated --border --sidebar --input-bg
  Text          --text (primary) --text-2 (secondary) --text-3 (disabled)
  Brand         --primary --primary-hover --primary-tint --primary-border --primary-ink (text on tint) --on-primary --link
  Status        --success --error --warning --info, each with -ink (text on its tint), -tint, -border
                --danger-solid (solid destructive button, white text)
  Neutral pill  --neutral-tint      Toggle track (off)  --toggle-off
  Depth         --card-shadow --elevated-shadow
  Charts        --grid (see chart_colors() for Altair, which can't read CSS variables)
  Decoration    --glow --glow-opacity --orb-hi --orb-mid --orb-lo --orb-edge --orb-shadow --rim (sign-in / page headers only)
"""
import datetime as dt
import html as _html
import re

import streamlit as st

THEMES = {
    "dark": {
        "scheme": "dark",
        "bg": "#0E0B1F", "surface": "#17142B", "row-alt": "#1A1730", "elevated": "#201C38", "border": "#2C2747",
        "sidebar": "#0A0818", "input-bg": "#17142B",
        "text": "#F2F0F7", "text-2": "#A6A1BD", "text-3": "#6B6685",
        "primary": "#6D4AFF", "primary-hover": "#7E5FFF", "primary-tint": "rgba(109,74,255,0.12)",
        "primary-border": "rgba(109,74,255,0.40)", "primary-ink": "#C9BDFF", "on-primary": "#FFFFFF", "link": "#9C86FF",
        "success": "#2FB67C", "success-ink": "#4FD39A", "success-tint": "rgba(47,182,124,0.12)", "success-border": "rgba(47,182,124,0.35)",
        "error": "#E5484D", "error-ink": "#FF8589", "error-tint": "rgba(229,72,77,0.12)", "error-border": "rgba(229,72,77,0.40)",
        "warning": "#E8A23A", "warning-ink": "#F2B85E", "warning-tint": "rgba(232,162,58,0.12)", "warning-border": "rgba(232,162,58,0.35)",
        "info": "#4C8DF6", "info-ink": "#7EAEFF", "info-tint": "rgba(76,141,246,0.12)", "info-border": "rgba(76,141,246,0.40)",
        "danger-solid": "#CF3A3F",            # error red deepened one step: white text 4.85:1 (#E5484D is 3.91:1)
        "neutral-tint": "rgba(255,255,255,0.04)", "toggle-off": "#6B6685",   # 3.6:1 on page and sidebar
        "card-shadow": "none", "elevated-shadow": "0 12px 32px rgba(0,0,0,0.45)",
        "grid": "rgba(255,255,255,0.05)",
        "glow": "#3B1E8F", "glow-opacity": "0.22", "rim": "rgba(232,196,138,0.10)",
        "orb-hi": "rgba(255,255,255,0.22)", "orb-mid": "rgba(109,74,255,0.35)", "orb-lo": "rgba(59,30,143,0.55)",
        "orb-edge": "rgba(14,11,31,0.90)", "orb-shadow": "rgba(59,30,143,0.45)",
    },
    "light": {
        "scheme": "light",
        "bg": "#F7F6FB", "surface": "#FFFFFF", "row-alt": "#FAF9FD", "elevated": "#FFFFFF", "border": "#E4E1EE",
        "sidebar": "#EFEDF6", "input-bg": "#FFFFFF",
        "text": "#17142B", "text-2": "#5E5878", "text-3": "#A6A1BD",
        "primary": "#5B36F2", "primary-hover": "#4A28D9", "primary-tint": "rgba(91,54,242,0.08)",
        "primary-border": "rgba(91,54,242,0.35)", "primary-ink": "#4A28D9", "on-primary": "#FFFFFF", "link": "#5B36F2",
        # Brief's status colours for icons, borders and fills; the -ink shades are darker so badge text passes AA
        # on its tint over white, the page and the sidebar (5.05 / 4.94 / 4.92 / 5.21 : 1)
        "success": "#1E8E5A", "success-ink": "#146B43", "success-tint": "rgba(30,142,90,0.10)", "success-border": "rgba(30,142,90,0.35)",
        "error": "#C9302C", "error-ink": "#B42824", "error-tint": "rgba(201,48,44,0.08)", "error-border": "rgba(201,48,44,0.35)",
        "warning": "#B26A00", "warning-ink": "#8A5200", "warning-tint": "rgba(178,106,0,0.10)", "warning-border": "rgba(178,106,0,0.35)",
        "info": "#2F6FD6", "info-ink": "#2459B3", "info-tint": "rgba(47,111,214,0.08)", "info-border": "rgba(47,111,214,0.35)",
        "danger-solid": "#C9302C",            # white text 5.33:1
        "neutral-tint": "rgba(23,20,43,0.04)", "toggle-off": "#87819F",      # 3.2:1+ on page, sidebar and white
        "card-shadow": "0 1px 2px rgba(20,16,50,0.04), 0 4px 12px rgba(20,16,50,0.05)",
        "elevated-shadow": "0 8px 24px rgba(20,16,50,0.08)",
        "grid": "rgba(23,20,43,0.07)",
        "glow": "#E6DEFF", "glow-opacity": "0.55", "rim": "rgba(245,230,200,0.35)",
        "orb-hi": "rgba(255,255,255,0.95)", "orb-mid": "rgba(193,178,255,0.60)", "orb-lo": "rgba(140,116,240,0.45)",
        "orb-edge": "rgba(230,222,255,0.90)", "orb-shadow": "rgba(150,130,240,0.35)",
    },
}

# Shared component CSS: tokens only. Literal values below are geometry, never colour.
COMPONENT_CSS = """
/* ---- Smooth theme switch ---------------------------------------------------------------------------------------- */
.stApp, section[data-testid="stSidebar"], .tk-card, .tk-badge, .tk-alert, .tk-empty, p, span, label, h1, h2, h3, li, dt, dd,
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, .stButton > button,
.stFormSubmitButton > button, [data-testid="stExpander"] details, [data-testid="stForm"],
[data-testid="stVerticalBlockBorderWrapper"] { transition: background-color .2s ease, color .2s ease, border-color .2s ease; }

/* ---- Page frame ------------------------------------------------------------------------------------------------- */
html { color-scheme: var(--scheme); }
body { background: var(--bg); color: var(--text); }     /* menus and dialogs are attached to the page body */
section[data-testid="stSidebar"] { color: var(--text); }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: var(--bg); color: var(--text); }
.block-container { padding-top: 1.25rem; padding-bottom: 4rem; max-width: 1400px; }
header[data-testid="stHeader"] { background: transparent; }
header[data-testid="stHeader"] button, [data-testid="stToolbar"] button { color: var(--text-2); }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { color: var(--text); }
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p, label { color: var(--text); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--text-2); opacity: 1 !important; }
.stApp a { color: var(--link); }
hr, [data-testid="stDivider"] hr { border-color: var(--border) !important; background: var(--border); }

/* ---- Sidebar: active nav item gets a 3px violet bar and tint ------------------------------------------------------ */
section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div { background: var(--sidebar); }
section[data-testid="stSidebar"] { border-right: 1px solid var(--border); }
[data-testid="stSidebarNavLink"] { border-radius: var(--radius); border-left: 3px solid transparent; }
[data-testid="stSidebarNavLink"] span { color: var(--text-2); }
[data-testid="stSidebarNavLink"]:hover { background: var(--primary-tint); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: var(--primary-tint); border-left-color: var(--primary); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: var(--text) !important; font-weight: 600; }
[data-testid="stSidebarNavSeparator"] { border-color: var(--border); }
[data-testid="stNavSectionHeader"], [data-testid="stNavSectionHeader"] * { color: var(--text-2) !important; }
[data-testid="stSidebarCollapseButton"] button, [data-testid="stExpandSidebarButton"] { color: var(--text-2); }

/* ---- Buttons: primary solid violet, secondary outlined ---------------------------------------------------------- */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  min-height: 42px; border-radius: var(--radius); font-weight: 600; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"],
.stButton > button[kind="primaryFormSubmit"], .stFormSubmitButton > button[kind="primaryFormSubmit"] {
  background: var(--primary); border: 1px solid var(--primary); color: var(--on-primary); }
.stButton > button[kind="primary"] *, .stFormSubmitButton > button[kind="primaryFormSubmit"] * { color: var(--on-primary); }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover {
  background: var(--primary-hover); border-color: var(--primary-hover); }
.stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondaryFormSubmit"] {
  background: transparent; border: 1px solid var(--border); color: var(--text); }
.stButton > button[kind="secondary"] *, .stFormSubmitButton > button[kind="secondaryFormSubmit"] * { color: var(--text); }
.stButton > button[kind="secondary"]:hover { border-color: var(--primary); }
.stButton > button:disabled, .stFormSubmitButton > button:disabled { background: var(--surface) !important;
  border-color: var(--border) !important; color: var(--text-3) !important; }
.stButton > button:disabled * { color: var(--text-3) !important; }
.stButton > button:focus-visible { box-shadow: 0 0 0 3px var(--primary-tint); outline: 1px solid var(--primary); }
/* Destructive: red outline (widget key contains "-danger"); solid red only in the final confirm dialog */
[class*="-danger"] button { border-color: var(--error) !important; background: transparent !important; }
[class*="-danger"] button, [class*="-danger"] button * { color: var(--error-ink) !important; }
[data-testid="stDialog"] [class*="confirm-danger"] button { background: var(--danger-solid) !important;
  border-color: var(--danger-solid) !important; }
[data-testid="stDialog"] [class*="confirm-danger"] button, [data-testid="stDialog"] [class*="confirm-danger"] button * {
  color: var(--on-primary) !important; }
[data-testid="stDialog"] [class*="confirm-danger"] button:disabled { background: var(--surface) !important;
  border-color: var(--border) !important; }
[data-testid="stDialog"] [class*="confirm-danger"] button:disabled * { color: var(--text-3) !important; }
/* Segmented controls and pills (one button group; the chosen option has aria-checked="true") */
[data-testid="stButtonGroup"] button { background: var(--surface) !important; border-color: var(--border) !important; }
[data-testid="stButtonGroup"] button, [data-testid="stButtonGroup"] button * { color: var(--text) !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"] { background: var(--primary-tint) !important;
  border-color: var(--primary) !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[aria-checked="true"] * {
  color: var(--primary-ink) !important; font-weight: 600; }
/* Toggle switch: track = border colour when off, violet when on; thumb always light with a hairline */
[data-testid="stCheckbox"] label > div:not([data-testid="stWidgetLabel"]) { background: var(--toggle-off) !important; }
[data-testid="stCheckbox"] label:has(input:checked) > div:not([data-testid="stWidgetLabel"]) { background: var(--primary) !important; }
[data-testid="stCheckbox"] label > div:not([data-testid="stWidgetLabel"]) > div { background: var(--on-primary) !important;
  box-shadow: 0 0 0 1px var(--border); }

/* ---- Inputs, selects, menus: surface fill, violet focus ring ---------------------------------------------------- */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
[data-testid="stTextAreaRootElement"], [data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"],
[data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div {
  background: var(--input-bg) !important; border-color: var(--border) !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stSelectbox"] > div > div:focus-within, [data-testid="stMultiSelect"] > div > div:focus-within {
  border-color: var(--primary) !important; box-shadow: 0 0 0 3px var(--primary-tint); }
[data-testid="stSelectbox"] button, [data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] button,
[data-testid="stMultiSelect"] svg { color: var(--text-2) !important; }
[data-testid="stSelectboxVirtualDropdown"], [data-testid$="VirtualDropdown"], [role="listbox"] {
  background: var(--elevated) !important; color: var(--text) !important; border: 1px solid var(--border);
  box-shadow: var(--elevated-shadow); }
[role="option"][data-focused="true"], [role="option"][data-selected="true"] { background: var(--primary-tint) !important; }
.stApp input, .stApp textarea, [data-baseweb="select"] div, [data-baseweb="select"] span {
  color: var(--text) !important; -webkit-text-fill-color: var(--text); caret-color: var(--text); }
.stApp input::placeholder, .stApp textarea::placeholder { color: var(--text-3) !important; -webkit-text-fill-color: var(--text-3); }
.stApp textarea:disabled, .stApp input:disabled { color: var(--text-2) !important; -webkit-text-fill-color: var(--text-2); }
[data-baseweb="select"] svg, [data-baseweb="input"] svg { color: var(--text-2); fill: var(--text-2); }
[data-baseweb="popover"] > div, [data-baseweb="menu"], ul[role="listbox"] { background: var(--elevated) !important;
  border: 1px solid var(--border); box-shadow: var(--elevated-shadow); }
[role="option"], [role="option"] * { color: var(--text) !important; background: transparent; }
[role="option"]:hover, [role="option"][aria-selected="true"] { background: var(--primary-tint) !important; }
[data-baseweb="tag"] { background: var(--primary-tint) !important; border: 1px solid var(--primary-border); }
[data-baseweb="tag"] span { color: var(--primary-ink) !important; }
[data-baseweb="tooltip"] > div, [data-baseweb="tooltip"] [role="tooltip"] { background: var(--elevated) !important;
  color: var(--text) !important; border: 1px solid var(--border); box-shadow: var(--elevated-shadow); }
[data-testid="stTooltipContent"], [data-testid="stTooltipContent"] * { color: var(--text) !important; }

/* ---- Tabs, expanders, forms, containers, dialogs, toasts ------------------------------------------------------- */
[data-baseweb="tab-list"] button[role="tab"], [data-baseweb="tab-list"] button[role="tab"] p { color: var(--text-2); }
[data-baseweb="tab-list"] button[role="tab"][aria-selected="true"], [data-baseweb="tab-list"] button[role="tab"][aria-selected="true"] p { color: var(--text); }
[data-baseweb="tab-highlight"] { background: var(--primary) !important; }
[data-baseweb="tab-border"] { background: var(--border) !important; }
[data-testid="stExpander"] details { border-radius: var(--radius-card); border-color: var(--border); background: var(--surface);
  box-shadow: var(--card-shadow); }
[data-testid="stExpander"] summary { background: var(--surface) !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color: var(--text) !important; }
[data-testid="stExpander"] summary:hover { background: var(--primary-tint) !important; }
[data-testid="stForm"] { border-color: var(--border) !important; background: var(--surface); box-shadow: var(--card-shadow); }
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stVerticalBlock"] { border-color: var(--border) !important; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: var(--radius-card); }
[data-testid="stDialog"] [role="dialog"] { background: var(--elevated); border: 1px solid var(--border);
  box-shadow: var(--elevated-shadow); color: var(--text); }
[data-testid="stDialog"] [role="dialog"] button[aria-label="Close"] { color: var(--text-2); }
[data-testid="stToast"] { background: var(--elevated) !important; border: 1px solid var(--border); box-shadow: var(--elevated-shadow); }
[data-testid="stToast"] * { color: var(--text) !important; }
[data-testid="stAlertContainer"] { border-radius: var(--radius); }
[data-testid="stJson"], [data-testid="stJson"] * { background: transparent !important; }
[data-testid="stJson"] span { color: var(--text-2) !important; }
[data-testid="stCode"] pre, [data-testid="stCode"] code { background: var(--surface) !important; color: var(--text) !important; }
[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; border-radius: var(--radius); }
[data-testid="stCheckbox"] label span, [data-testid="stToggle"] label span { color: var(--text); }

/* ---- Components rendered by the helpers below ------------------------------------------------------------------ */
.tk-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-card);
  padding: 16px 20px; box-shadow: var(--card-shadow); }
.tk-card + .tk-card { margin-top: 12px; }
.tk-label { color: var(--text-2); font-size: 12.5px; letter-spacing: .02em; margin: 0 0 4px 0; }
.tk-value { color: var(--text); font-size: 16px; font-weight: 600; font-variant-numeric: tabular-nums; margin: 0;
  overflow-wrap: anywhere; }
.tk-value .tk-badge { white-space: normal; }
.tk-hero { color: var(--text); font-size: 34px; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.15; margin: 0; }
.tk-sub { color: var(--text-2); font-size: 13px; margin: 4px 0 0 0; }
.tk-muted { color: var(--text-2); }
.tk-num { font-variant-numeric: tabular-nums; }
.tk-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.tk-grid .tk-card { margin: 0; padding: 14px 16px; }
.tk-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.tk-title { color: var(--text); font-size: 20px; font-weight: 600; margin: 0; }
.tk-h { color: var(--text); font-size: 15px; font-weight: 600; margin: 0 0 8px 0; }
.tk-why { margin: 0; padding-left: 18px; color: var(--text); }
.tk-why li { margin: 2px 0; }
.tk-quote { color: var(--text); border-left: 3px solid var(--border); padding: 4px 0 4px 12px; margin: 0; white-space: pre-wrap; }
.tk-kv { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; margin: 0 !important; padding: 0 !important; }
.tk-kv dt { color: var(--text-2); font-size: 13px; margin: 0 !important; padding: 0 !important; }
.tk-kv dd { color: var(--text); margin: 0 !important; padding: 0 !important; font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere; }

.tk-badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px;
  font-size: 12.5px; font-weight: 600; line-height: 20px; white-space: nowrap; border: 1px solid transparent; }
.tk-success { background: var(--success-tint); color: var(--success-ink); border-color: var(--success-border); }
.tk-error   { background: var(--error-tint);   color: var(--error-ink);   border-color: var(--error-border); }
.tk-warning { background: var(--warning-tint); color: var(--warning-ink); border-color: var(--warning-border); }
.tk-info    { background: var(--info-tint);    color: var(--info-ink);    border-color: var(--info-border); }
.tk-neutral { background: var(--neutral-tint); color: var(--text-2); border-color: var(--border); }
.tk-accent  { background: var(--primary-tint); color: var(--primary-ink); border-color: var(--primary-border); }

.tk-alert { display: flex; gap: 10px; align-items: flex-start; border-radius: var(--radius); padding: 12px 14px;
  border: 1px solid; margin: 4px 0 8px 0; }
.tk-alert p, .tk-alert ul { margin: 0; color: var(--text); }
.tk-alert ul { padding-left: 18px; }
.tk-alert .tk-ico { font-weight: 700; line-height: 1.4; }
.tk-alert.tk-success .tk-ico { color: var(--success-ink); }
.tk-alert.tk-error .tk-ico   { color: var(--error-ink); }
.tk-alert.tk-warning .tk-ico { color: var(--warning-ink); }
.tk-alert.tk-info .tk-ico    { color: var(--info-ink); }

.tk-empty { text-align: center; padding: 36px 16px; border: 1px dashed var(--border); border-radius: var(--radius-card); }
.tk-empty p { margin: 4px 0; }

.tk-steps { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.tk-steps li { display: grid; grid-template-columns: 130px 1fr 72px; align-items: center; gap: 12px; color: var(--text); }
.tk-bar { height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
.tk-bar span { display: block; height: 100%; background: var(--primary); border-radius: 3px; }

.tk-timeline { list-style: none; margin: 0; padding: 0; }
.tk-timeline li { position: relative; padding: 0 0 14px 20px; border-left: 1px solid var(--border); margin-left: 6px; }
.tk-timeline li::before { content: ""; position: absolute; left: -5px; top: 5px; width: 9px; height: 9px;
  border-radius: 50%; background: var(--surface); border: 2px solid var(--text-3); }
.tk-timeline li.tk-t-staff::before { border-color: var(--primary); }
.tk-timeline .tk-ts { color: var(--text-2); font-size: 12.5px; }
.tk-timeline .tk-d { color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; }

/* Customer conversation thread */
.tk-thread { display: grid; gap: 10px; }
.tk-msg { max-width: 78%; padding: 10px 14px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface);
  box-shadow: var(--card-shadow); }
.tk-msg p { margin: 0; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
.tk-msg .tk-ts { color: var(--text-2); font-size: 12px; margin-bottom: 4px; }
.tk-msg.tk-me { justify-self: end; background: var(--primary-tint); border-color: var(--primary-border); }

/* ---- Ambient glow: sign-in and page headers only, never behind tables, forms or numbers ------------------------- */
.tk-hero-wrap { position: relative; isolation: isolate; padding: 8px 0 4px 0; margin-bottom: 8px; }
.tk-hero-wrap.tk-glow::before { content: ""; position: absolute; z-index: -1; left: -120px; top: -160px;
  width: 520px; height: 360px; border-radius: 50%; filter: blur(80px); opacity: var(--glow-opacity);
  background: radial-gradient(circle at 40% 40%, var(--glow) 0%, transparent 70%); pointer-events: none; }
.tk-orb { position: relative; width: 132px; height: 132px; margin: 8px auto 20px auto; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, var(--orb-hi), var(--orb-mid) 38%, var(--orb-lo) 70%, var(--orb-edge));
  box-shadow: 0 0 80px 10px var(--orb-shadow), inset -10px -14px 30px var(--orb-edge), inset 6px 6px 18px var(--rim); }
.tk-signin-glow { position: fixed; z-index: 0; left: 50%; top: 18%; width: 720px; height: 520px;
  transform: translateX(-50%); border-radius: 50%; filter: blur(110px); opacity: var(--glow-opacity); pointer-events: none;
  background: radial-gradient(circle, var(--glow) 0%, transparent 70%); }
.tk-brand { display: flex; align-items: center; gap: 10px; margin: 0 0 4px 0; }
.tk-brand-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 0 4px var(--primary-tint); }
.tk-brand-name { color: var(--text); font-weight: 700; letter-spacing: .01em; }
"""

# Light mode only: Streamlit draws tables (st.dataframe / st.data_editor) on a canvas from the dark config.toml, which
# CSS colours can't reach. Inverting and rotating the hue back turns the dark grid into a light one with the same
# violet accent; text stays readable.
LIGHT_ONLY_CSS = """
[data-testid="stDataFrame"] > div { filter: invert(1) hue-rotate(180deg) brightness(1.04); }
"""


def get_theme_css(theme: str) -> str:
    """The token set for `theme` ("dark" or "light") plus the shared component CSS, as one stylesheet."""
    tokens = THEMES.get(theme, THEMES["dark"])
    root = ":root {\n" + "\n".join(f"  --{k}: {v};" for k, v in tokens.items()) + \
        "\n  --radius-card: 12px; --radius: 8px;\n}\n"
    css = root + COMPONENT_CSS + (LIGHT_ONLY_CSS if theme == "light" else "")
    # st.html sanitises its input and silently drops a <style> whose text looks like it holds a tag ("<body", "</")
    assert not re.search(r"<[/\w!]", css), "CSS must not contain '<' followed by a letter, '/' or '!'"
    return css


def current_theme() -> str:
    return st.session_state.get("theme", "dark")


def inject_css():
    """Load the design system for the current theme (Streamlit re-renders the page on every interaction)."""
    st.html(f"<style>{get_theme_css(current_theme())}</style>")


def chart_colors(theme: str = None) -> dict:
    """Altair can't read CSS variables, so charts take their colours from the same token set."""
    t = THEMES.get(theme or current_theme(), THEMES["dark"])
    return {"bar": t["primary"], "label": t["text-2"], "text": t["text"], "grid": t["grid"], "background": "transparent"}


# ---- Formatting ----------------------------------------------------------------------------------------------------
def esc(v) -> str:
    return _html.escape("" if v is None else str(v))


def money(v, dash="—") -> str:
    """RM 1,234.56: always two decimals; a debit shows a minus sign in neutral ink, never red."""
    if v is None or v == "":
        return dash
    v = float(v)
    return f"{'-' if v < 0 else ''}RM {abs(v):,.2f}"


def mask(s: str, keep: int = 4) -> str:
    s = s or ""
    return "•" * max(len(s) - keep, 0) + s[-keep:] if len(s) > keep else s


def nice(code: str) -> str:
    """DUPLICATE_CHARGE -> Duplicate charge; ATM_NOT_DISPENSED -> ATM not dispensed."""
    text = (code or "").replace("_", " ").capitalize() or "—"
    return text.replace("Atm ", "ATM ").replace("Llm", "LLM").replace("Sla ", "SLA ")


def duration(td: dt.timedelta) -> str:
    secs = int(abs(td.total_seconds()))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d}d {h}h" if d else (f"{h}h {m:02d}m" if h else f"{m}m")


# ---- Badges: tinted pill + icon + label ---------------------------------------------------------------------------
STATUS = {   # status -> (tone, icon, label)
    "RESOLVED": ("success", "✓", "Resolved"),
    "APPROVED": ("success", "✓", "Approved & sent"),
    "PENDING_APPROVAL": ("warning", "⏳", "Pending approval"),
    "ESCALATED": ("warning", "⇪", "Escalated"),
    "FRAUD_QUEUE": ("error", "⚑", "Fraud queue"),
    "AWAITING_CUSTOMER": ("info", "…", "Awaiting customer"),
    "FRAUD_CLOSED": ("neutral", "■", "Fraud case closed"),
    "REJECTED": ("neutral", "✕", "Rejected"),
    "ANSWERED": ("neutral", "↩", "Answered"),
}
PRIORITY = {"P1": ("error", "▲", "P1 urgent"), "P2": ("warning", "◆", "P2"), "P3": ("neutral", "●", "P3")}


def badge(tone: str, label: str, icon: str = "") -> str:
    return f'<span class="tk-badge tk-{tone}">{esc(icon)} {esc(label)}</span>' if icon else \
        f'<span class="tk-badge tk-{tone}">{esc(label)}</span>'


def status_badge(status: str) -> str:
    tone, icon, label = STATUS.get(status, ("neutral", "•", nice(status)))
    return badge(tone, label, icon)


def priority_badge(p: str) -> str:
    tone, icon, label = PRIORITY.get(p or "", ("neutral", "•", p or "—"))
    return badge(tone, label, icon)


def check_badge(problems) -> str:
    return badge("error", "Self-check flagged", "✕") if problems else badge("success", "Self-check verified", "✓")


def sla_badge(left) -> str:
    """left: timedelta until the acknowledge deadline, or None for a closed case."""
    if left is None:
        return badge("neutral", "SLA closed", "◷")
    if left.total_seconds() < 0:
        return badge("error", f"SLA overdue {duration(left)}", "◷")
    if left.total_seconds() < 3600:
        return badge("warning", f"SLA {duration(left)} left", "◷")
    return badge("neutral", f"SLA {duration(left)} left", "◷")


# ---- Blocks --------------------------------------------------------------------------------------------------------
def render(markup: str):
    st.html(markup)


def card(body: str, title: str = "") -> str:
    head = f'<p class="tk-h">{esc(title)}</p>' if title else ""
    return f'<div class="tk-card">{head}{body}</div>'


def kpi(label: str, value: str, sub: str = "") -> str:
    """A stat tile. value is pre-formatted text; numbers stay in primary ink, never status colour."""
    s = f'<p class="tk-sub">{sub}</p>' if sub else ""
    return f'<div class="tk-card"><p class="tk-label">{esc(label)}</p><p class="tk-hero">{esc(value)}</p>{s}</div>'


def tile(label: str, value_html: str) -> str:
    return f'<div class="tk-card"><p class="tk-label">{esc(label)}</p><p class="tk-value">{value_html}</p></div>'


def grid(items) -> str:
    return f'<div class="tk-grid">{"".join(items)}</div>'


def page_header(title: str, subtitle: str = "", glow: bool = False):
    cls = "tk-hero-wrap tk-glow" if glow else "tk-hero-wrap"
    sub = f'<p class="tk-sub">{esc(subtitle)}</p>' if subtitle else ""
    render(f'<div class="{cls}"><h1 style="margin:0;font-size:28px;font-weight:600">{esc(title)}</h1>{sub}</div>')


ALERT_ICON = {"success": "✓", "error": "✕", "warning": "!", "info": "i"}


def alert(tone: str, text: str, items=None):
    """Our own alert in the semantic palette, always icon + text. items: optional bullet list."""
    li = "".join(f"<li>{esc(i)}</li>" for i in (items or []))
    lst = f"<ul>{li}</ul>" if li else ""
    render(f'<div class="tk-alert tk-{tone}" role="status"><span class="tk-ico">{ALERT_ICON[tone]}</span>'
           f'<div><p>{esc(text)}</p>{lst}</div></div>')


def empty_state(title: str, body: str = ""):
    render(f'<div class="tk-empty"><p class="tk-value">{esc(title)}</p><p class="tk-sub">{esc(body)}</p></div>')


def kv(pairs) -> str:
    """Definition list of (label, value_html) pairs."""
    return '<dl class="tk-kv">' + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"
