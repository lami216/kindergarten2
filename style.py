"""
style.py — Central CSS for Streamlit App. Professional RTL layout with clean Cairo font everywhere.
"""

CSS = """
<style>
/* ---------------------------------------------------------------- */
/* Google Fonts Import for Cairo Arabic Font                        */
/* ---------------------------------------------------------------- */
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap');

:root {
    /* Main Brand Colors */
    --primary: #10B981;
    --primary-dark: #064E3B;
    --primary-light: #D1FAE5;
    
    /* Modern Palette */
    --coral-pink: #F43F5E;
    --amber-gold: #F59E0B;
    --soft-sky: #3B82F6;
    
    /* Neutrals & Surfaces */
    --bg: #FAFAF9;
    --card-bg: #FFFFFF;
    --card-border: #E7E5E4;
    --text-main: #1C1917;
    --text-muted: #78716C;
    
    /* Elevation Shadows */
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.05);
    --shadow-md: 0 4px 12px -2px rgba(0,0,0,0.08);
    --shadow-lg: 0 10px 25px -5px rgba(0,0,0,0.1);
}

/* ---------------------------------------------------------------- */
/* GLOBAL FONT OVERRIDE — FORCING 'Cairo' EVERYWHERE                */
/* ---------------------------------------------------------------- */
*, *::before, *::after,
html, body, [class*="css"],
p, span, div, a, li, blockquote,
h1, h2, h3, h4, h5, h6, 
label, input, textarea, select, button,
div[data-baseweb="select"], 
.stMarkdown, .stMarkdown p, .section-title, .section-sub {
    font-family: 'Cairo', sans-serif !important;
}

/* Preserve Streamlit Native Icons */
[data-testid="stIconMaterial"], 
[class*="material-symbols"], 
i[class*="icon"] {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
}

html, body, [class*="css"] {
    direction: RTL;
    text-align: right;
    color: var(--text-main);
}

.stApp {
    background-color: var(--bg);
}

/* ---------------------------------------------------------------- */
/* STREAMLIT HEADINGS FIX                                          */
/* ---------------------------------------------------------------- */
div[data-testid="stHeadingWithHeadline"] {
    direction: rtl !important;
    text-align: right !important;
}

div[data-testid="stHeadingWithHeadline"] > h1,
div[data-testid="stHeadingWithHeadline"] > h2,
div[data-testid="stHeadingWithHeadline"] > h3,
div[data-testid="stHeadingWithHeadline"] > h4,
div[data-testid="stHeadingWithHeadline"] > h5,
div[data-testid="stHeadingWithHeadline"] > h6 {
    display: flex !important;
    flex-direction: row !important;
    justify-content: flex-start !important;
    align-items: center !important;
    gap: 8px !important;
    font-family: 'Cairo', sans-serif !important;
    font-weight: 700 !important;
    color: var(--text-main);
    margin-top: 4px;
    margin-bottom: 8px;
}

div[data-testid="stHeadingWithHeadline"] a {
    order: 2 !important;
    opacity: 0.3;
    transition: opacity 0.2s ease;
}

div[data-testid="stHeadingWithHeadline"]:hover a {
    opacity: 1;
}

/* ---------------------------------------------------------------- */
/* SECTION TITLES & SUBTITLES                                       */
/* ---------------------------------------------------------------- */
.section-title {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 10px;
    font-size: 26px;
    font-weight: 800 !important;
    font-family: 'Cairo', sans-serif !important;
    color: var(--primary-dark);
    margin-bottom: 4px;
    text-align: right;
}

.section-sub {
    color: var(--text-muted);
    margin-bottom: 24px;
    font-size: 15px;
    font-weight: 600 !important;
    font-family: 'Cairo', sans-serif !important;
    text-align: right;
}

/* ---------------------------------------------------------------- */
/* TABS STYLING                                                    */
/* ---------------------------------------------------------------- */
div[data-testid="stTabs"] {
    direction: rtl !important;
}

div[data-baseweb="tab-list"] {
    gap: 8px;
    background-color: transparent;
    border-bottom: 2px solid var(--card-border);
    justify-content: flex-start;
}

button[data-baseweb="tab"] {
    height: 44px;
    padding: 8px 18px;
    border-radius: 10px 10px 0 0 !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    font-family: 'Cairo', sans-serif !important;
    color: var(--text-muted) !important;
    background-color: transparent !important;
    transition: all 0.2s ease;
}

button[data-baseweb="tab"]:hover {
    color: var(--primary) !important;
    background-color: var(--primary-light) !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--primary-dark) !important;
    border-bottom: 3px solid var(--primary) !important;
    background-color: #FFFFFF !important;
}

/* ---------------------------------------------------------------- */
/* SIDEBAR STYLING (Margin Bug Cleaned)                             */
/* ---------------------------------------------------------------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #064E3B 0%, #022C22 100%) !important;
    direction: RTL;
    border-left: 1px solid rgba(255, 255, 255, 0.08) !important;
}

header[data-testid="stHeader"] {
    background-color: transparent !important;
    z-index: 99999 !important;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span:not([data-testid="stIconMaterial"]),
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stMarkdown {
    color: rgba(255, 255, 255, 0.9) !important;
    font-family: 'Cairo', sans-serif !important;
}

.brand-box {
    text-align: center;
    padding: 12px 8px 20px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
    margin-bottom: 18px;
}

.brand-box h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 800;
    color: #FFFFFF !important;
    letter-spacing: -0.3px;
    font-family: 'Cairo', sans-serif !important;
}

.brand-box p {
    margin: 4px 0 0 0;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.7) !important;
    font-family: 'Cairo', sans-serif !important;
}

section[data-testid="stSidebar"] .stButton {
    margin-bottom: 6px !important;
}

section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #E2E8F0 !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 12px !important;
    text-align: right !important;
    justify-content: flex-start !important;
    padding: 10px 16px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    font-family: 'Cairo', sans-serif !important;
    height: 44px !important;
    width: 100% !important;
    box-shadow: none !important;
    transition: all 0.2s ease-in-out !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="secondary"] * {
    color: #E2E8F0 !important;
    font-family: 'Cairo', sans-serif !important;
}

section[data-testid="stSidebar"] .stButton > button:hover,
section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
    background: rgba(255, 255, 255, 0.18) !important;
    color: #FFFFFF !important;
    border-color: rgba(255, 255, 255, 0.3) !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    text-align: right !important;
    justify-content: flex-start !important;
    padding: 10px 16px !important;
    font-weight: 800 !important;
    font-size: 14px !important;
    font-family: 'Cairo', sans-serif !important;
    height: 44px !important;
    width: 100% !important;
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35) !important;
}

section[data-testid="stSidebar"] .stButton > button[kind="primary"] * {
    color: #FFFFFF !important;
    font-family: 'Cairo', sans-serif !important;
}

/* ---------------------------------------------------------------- */
/* CONTAINERS, DATAFRAMES & CARDS                                   */
/* ---------------------------------------------------------------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--card-bg);
    border-radius: 16px !important;
    border: 1px solid var(--card-border) !important;
    box-shadow: var(--shadow-sm);
    padding: 12px;
    margin-bottom: 16px;
}

div[data-testid="stDataFrame"] {
    direction: rtl !important;
    border-radius: 12px;
    border: 1px solid var(--card-border);
}

.kpi-card {
    background:var(--card-bg); border:1px solid var(--card-border);
    border-inline-start:3px solid var(--kpi-accent,var(--primary));
    border-radius:12px; padding:12px 14px; box-shadow:var(--shadow-sm);
    display:grid !important; grid-template-columns:minmax(0,1fr) auto;
    align-items:center !important;
    gap:8px !important; min-height:64px; height:100%; box-sizing:border-box;
}
.kpi-heading { display:flex; align-items:center; gap:8px; min-width:0; }
.kpi-label { color:var(--text-muted); font-size:12px !important; line-height:1.5; font-weight:600; min-width:0; overflow-wrap:break-word; }
.kpi-icon { display:inline-flex; align-items:center; justify-content:center;
    width:28px; height:28px; min-width:28px; border-radius:8px; font-size:17px; flex-shrink:0; }
.kpi-number { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px; max-width:155px; }
.kpi-value { font-size:23px !important; font-weight:800; line-height:1.3;
    color:var(--text-main); overflow-wrap:anywhere; min-width:0; }
.kpi-unit { color:var(--text-muted); font-size:11px; }
.kpi-hint { grid-column:1/-1; color:var(--text-muted); font-size:11px; line-height:1.4; }
.stMainBlockContainer { max-width:1400px; }
@media (min-width:700px) and (max-width:1100px) {
    .kpi-card { padding:10px; }
    .kpi-heading { gap:5px; }
    .kpi-label { font-size:11px !important; }
    .kpi-value { font-size:20px !important; }
}
[class*="st-key-home_"] button:active { background:var(--primary) !important; color:white !important; }

/* ---------------------------------------------------------------- */
/* ORIGINAL LOGIN FORM & INPUT FIELD STYLING (RESTORED)             */
/* ---------------------------------------------------------------- */
.login-header {
    text-align: center;
    margin-top: 8px;
    margin-bottom: 20px;
}

.login-header h2 {
    font-size: 22px !important;
    font-weight: 800 !important;
    color: #064E3B !important;
    margin: 0 0 2px 0 !important;
    text-align: center !important;
}

.login-header .subtitle-en {
    font-size: 13px !important;
    color: #64748B !important;
    direction: ltr !important;
    margin: 0 0 12px 0 !important;
    font-weight: 500 !important;
    text-align: center !important;
}

.login-badge-wrapper {
    display: flex;
    justify-content: center;
    margin-top: 6px;
}

.login-badge {
    background-color: #ECFDF5;
    color: #064E3B;
    font-size: 13px;
    font-weight: 700;
    padding: 4px 14px;
    border-radius: 20px;
    border: 1px solid rgba(16, 185, 129, 0.25);
}

div[data-testid="stForm"] {
    background: #FFFFFF !important;
    border-radius: 20px !important;
    padding: 32px 28px !important;
    border: 1px solid #E2E8F0 !important;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01) !important;
}

div[data-testid="stForm"] div[data-baseweb="input"] {
    border-radius: 12px !important;
    background-color: #F8FAFC !important;
    border: 1px solid #CBD5E1 !important;
    transition: all 0.2s ease-in-out;
}

div[data-testid="stForm"] div[data-baseweb="input"]:focus-within {
    border-color: #10B981 !important;
    background-color: #FFFFFF !important;
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15) !important;
}

div[data-testid="stForm"] [data-aria-hidden="true"],
div[data-testid="stForm"] small,
div[data-testid="InputInstructions"] {
    display: none !important;
}

div[data-testid="stForm"] input::placeholder {
    opacity: 0.6 !important;
}

.stButton > button {
    border-radius: 10px;
    font-weight: 700;
    font-family: 'Cairo', sans-serif !important;
    transition: all 0.2s ease;
}

.stButton > button[kind="primary"] {
    background: var(--primary);
    border-color: var(--primary);
    color: #FFFFFF;
}

.stButton > button[kind="primary"]:hover {
    background: var(--primary-dark);
    border-color: var(--primary-dark);
    box-shadow: var(--shadow-md);
}

/* Force text alignment right */
div[data-testid="stMarkdownContainer"] {
    text-align: right !important;
}

/* Hide default UI elements while maintaining header controls */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
div[data-testid="stDecoration"] {display: none;}
div[data-testid="stStatusWidget"] {display: none !important;}
.stDeployButton {display: none !important;}
</style>
"""



SHELL_CSS = """
<style>
/* The internal pickup selector must not create its own layout row. */
[data-testid="stExpander"] [data-testid="stElementContainer"]:has(.pickup-style-anchor) {
    display:none !important;
}
/* Force BOTH native fee-choice buttons' actual text and backgrounds.
   Current Streamlit uses a ButtonGroup rather than stSegmentedControl on some
   installs; its selected data-baseweb buttons have no aria-pressed attribute. */
[class*="st-key-kid_finance_mode"] button {
    background:var(--card-bg) !important;
    color:var(--text-main) !important;
    border:1px solid var(--card-border) !important;
}
[class*="st-key-kid_finance_mode"] button :is(p,span,svg) {
    color:var(--text-main) !important;
}
[class*="st-key-kid_finance_mode"] button:is(:hover,:focus-visible) {
    background:var(--card-bg) !important;
    color:var(--text-main) !important;
    border-color:var(--primary) !important;
}
[class*="st-key-kid_finance_mode"] button:is([aria-pressed="true"],[aria-checked="true"],[data-state="on"],[data-selected="true"],[data-active="true"]),
[class*="st-key-kid_finance_mode"] [data-baseweb="button-group"] button[aria-selected="true"] {
    background:#006348 !important;
    color:#fff !important;
    border-color:#006348 !important;
}
[class*="st-key-kid_finance_mode"] button:is([aria-pressed="true"],[aria-checked="true"],[data-state="on"],[data-selected="true"],[data-active="true"]) :is(p,span,svg),
[class*="st-key-kid_finance_mode"] [data-baseweb="button-group"] button[aria-selected="true"] :is(p,span,svg) {
    color:#fff !important;
}
/* Native fee-mode choices: color the displayed descendants, not just wrapper.
   Covers versions of the existing Streamlit widget after successful saves. */
[class*="st-key-kid_finance_mode"] [data-testid="stSegmentedControl"] button,
[class*="st-key-kid_finance_mode"] button[aria-pressed] {
    background:var(--card-bg) !important;
    color:var(--text-main) !important;
    border:1px solid var(--card-border) !important;
}
[class*="st-key-kid_finance_mode"] :is([data-testid="stSegmentedControl"] button,button[aria-pressed]) :is(p,span,svg) {
    color:inherit !important;
}
[class*="st-key-kid_finance_mode"] :is([data-testid="stSegmentedControl"] button,button[aria-pressed]):is(:hover,:focus-visible):not([aria-pressed="true"]) {
    background:var(--card-bg) !important;
    color:var(--text-main) !important;
    border-color:var(--primary) !important;
}
[class*="st-key-kid_finance_mode"] button[aria-pressed="true"],
[class*="st-key-kid_finance_mode"] [data-testid="stSegmentedControl"] button[aria-checked="true"] {
    background:#006348 !important;
    color:#ffffff !important;
    border-color:#006348 !important;
}
[class*="st-key-kid_finance_mode"] :is(button[aria-pressed="true"],button[aria-checked="true"]) :is(p,span,svg) {
    color:#ffffff !important;
}
/* Native controls remain visible and use the existing palette. */
.st-key-appearance_control {
    position:fixed; top:8px; left:12px; width:150px !important;
    z-index:999992; background:var(--card-bg); color:var(--text-main);
    border:1px solid var(--card-border); border-radius:6px; padding:8px; min-height:44px;
}
[data-testid="stLayoutWrapper"]:has(> .st-key-appearance_control) {
    position:absolute; width:0 !important; height:0 !important;
}
.st-key-night_mode label > span + div { direction:ltr; }
.st-key-appearance_control [data-testid="stWidgetLabel"] p {
    color:var(--text-main) !important; font-size:14px;
}
[data-testid="stSidebarHeader"] { direction:ltr; }
div[data-testid="stToolbar"] { visibility:visible; }
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"] button {
    min-height:44px; min-width:44px; padding:8px !important;
    background:var(--card-bg); color:var(--text-main) !important;
    border:1px solid var(--card-border); border-radius:6px;
}
.st-key-night_mode label[data-selected="true"] > span + div {
    background:#006348 !important;
}
[data-testid="stExpandSidebarButton"] span,
[data-testid="stSidebarCollapseButton"] button span { color:var(--text-main) !important; }
[data-testid="stExpandSidebarButton"] > span { display:none; }
[data-testid="stExpandSidebarButton"] { gap:8px; min-width:104px; font-size:14px; }
[data-testid="stExpandSidebarButton"]::before {
    content:""; width:20px; height:20px; background:currentColor;
    mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M3 6h18M3 12h18M3 18h18' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E") center/contain no-repeat;
}
[data-testid="stExpandSidebarButton"]::after { content:"القائمة"; font-size:14px; }
[data-testid="stSidebarCollapseButton"] button::after { content:"إغلاق"; font-size:12px; }
section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarCollapseButton"] button {
    opacity:1 !important; visibility:visible !important;
}
section[data-testid="stSidebar"][aria-expanded="false"] { transform:translateX(100%); visibility:hidden; }
/* Some Streamlit descendants explicitly override inherited visibility.
   Keep the whole closed rail non-painting and non-interactive; do not hide
   the native reopen button, which lives outside this closed section. */
section[data-testid="stSidebar"][aria-expanded="false"] * {
    visibility:hidden !important;
    pointer-events:none !important;
}
section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"] {
    visibility:hidden !important;
}
button:focus-visible, input:focus-visible, [role="switch"]:focus-visible {
    outline:3px solid #8dd9bc !important; outline-offset:2px;
}
@media (max-width:768px) {
    [data-testid="stSidebar"] {
        position:fixed !important; right:0; left:auto; top:0; height:100dvh !important;
        width:min(300px, calc(100vw - 48px)) !important;
        min-width:0 !important; max-width:min(300px, calc(100vw - 48px)) !important;
    }
    [data-testid="stSidebar"][aria-expanded="true"] {
        transform:none; box-shadow:-32px 0 48px rgba(0,0,0,.4);
    }
    [data-testid="stSidebarContent"] { height:100%; overflow-y:auto; }
    [data-testid="stSidebarHeader"] { position:sticky; top:0; background:inherit; z-index:2; }
}
</style>
"""

THEME_SURFACES = """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebarHeader"] {
    background:#002d20 !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background:#006348 !important; box-shadow:none !important;
}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background:var(--bg); color:var(--text-main);
}
.stApp p, .stApp label, .stApp small, .stApp [data-testid="stMarkdownContainer"] {
    color:var(--text-main);
}
div[data-testid="stForm"], [data-testid="stDialog"] [role="dialog"],
[data-testid="stExpander"] details, [data-testid="stAlert"] {
    background:var(--card-bg) !important; color:var(--text-main) !important;
    border:1px solid var(--card-border) !important;
}
/* Only pickup editor expanders, and only when night mode is active.
   Streamlit's secondaryFormSubmit buttons are distinct from secondary buttons. */
[data-testid="stExpander"]:has(.pickup-style-anchor) details > summary,
[data-testid="stExpander"]:has(.pickup-style-anchor) details > summary:hover,
[data-testid="stExpander"]:has(.pickup-style-anchor) details > summary:focus-visible {
    background:var(--card-bg) !important;
    color:var(--text-main) !important;
    border-color:var(--card-border) !important;
}
[data-testid="stExpander"]:has(.pickup-style-anchor) details > summary
    [data-testid="stMarkdownContainer"],
[data-testid="stExpander"]:has(.pickup-style-anchor) details > summary
    [data-testid="stMarkdownContainer"] p,
[data-testid="stExpander"]:has(.pickup-style-anchor) details > summary svg {
    color:var(--text-main) !important;
}
[data-testid="stExpander"]:has(.pickup-style-anchor)
    button[kind="secondaryFormSubmit"] {
    background:var(--card-bg) !important;
    color:var(--text-main) !important;
    border:1px solid var(--card-border) !important;
}
[data-testid="stExpander"]:has(.pickup-style-anchor)
    button[kind="secondaryFormSubmit"] :is(p, span, svg) {
    color:var(--text-main) !important;
}
[data-testid="stDialog"] p, [data-testid="stDialog"] label,
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] {
    color:var(--text-main) !important;
}
.stApp input::placeholder, .stApp textarea::placeholder {
    color:var(--text-muted) !important; opacity:1 !important;
}
[data-baseweb="select"] div { color:var(--text-main); }
[data-testid="stAppDeployButton"] { display:none; }
[data-baseweb="tab-highlight"] { background-color:var(--primary) !important; }
div[data-testid="stForm"] div[data-baseweb="input"],
div[data-testid="stForm"] div[data-baseweb="input"]:focus-within,
[data-baseweb="input"], [data-baseweb="base-input"],
[data-baseweb="textarea"], [data-baseweb="select"] > div,
.stApp input:not([type="checkbox"]), .stApp textarea {
    background:var(--card-bg) !important; color:var(--text-main) !important;
    border-color:var(--card-border) !important; caret-color:var(--text-main);
}
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"],
[role="option"], [data-baseweb="calendar"], [data-baseweb="calendar"] button {
    background:var(--card-bg) !important; color:var(--text-main) !important;
}
[data-baseweb="select"] span { color:var(--text-main) !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] {
    background:var(--primary-light) !important;
}
.stApp button[kind="secondary"], [data-testid="stDownloadButton"] button,
[data-testid="stPopoverButton"] {
    background:var(--card-bg); color:var(--text-main); border-color:var(--card-border);
}
button[data-baseweb="tab"][aria-selected="true"] { background:var(--card-bg) !important; }
.login-header h2 { color:var(--primary-dark) !important; }
.login-header .subtitle-en { color:var(--text-muted) !important; }
.login-badge { background:var(--primary-light); color:var(--primary-dark); }
</style>
"""


def apply_style():
    """Public, URL-bound preference; never participates in authentication."""
    import streamlit as st
    with st.container(key="appearance_control"):
        night = st.toggle("الوضع الليلي", key="night_mode", bind="query-params",
                          persist_state="session")
    palette = """<style>:root {
        --bg:#101519; --card-bg:#202223; --card-border:#303636;
        --text-main:#f0f4f2; --text-muted:#b8c3bf;
        --primary:#006348; --primary-dark:#8dd9bc; --primary-light:#002d20;
        color-scheme:dark;
    }
    .kpi-icon { background:#002d20 !important; color:#8dd9bc !important; }
    </style>""" if night else "<style>:root {color-scheme:light;}</style>"
    surfaces = THEME_SURFACES if night else ""
    st.markdown(CSS + SHELL_CSS + surfaces + palette, unsafe_allow_html=True)
