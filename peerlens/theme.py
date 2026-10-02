"""Visual identity: an institutional research-desk look.

Palette
  ink navy   #0B1F3A  masthead, headings, primary text
  page       #F3F5F8  cool grey ground; white panels sit on it
  slate      #5B6B7F  secondary text
  rule       #D8DEE6  hairlines and table borders
  brass      #A8864F  the focal company, and nothing else
  signals    #2E7D5B positive, #B7862C watch, #A63D40 concern (muted, never neon)
Type
  Source Serif 4 for titles (the voice of a research note), IBM Plex Sans for everything else,
  with tabular figures so numbers line up in columns.
The memorable element is the comps table; everything around it stays quiet.
"""
import datetime as dt
import html

PALETTES = {
    "light": """
  --ink: #0B1F3A; --page: #F3F5F8; --panel: #FFFFFF; --slate: #5B6B7F; --rule: #D8DEE6;
  --soft: #EEF2F6; --brass: #A8864F; --brass-tint: #F6F0E4; --blue: #2F5C8F;
  --pos: #2E7D5B; --watch: #B7862C; --neg: #A63D40;
  --pos-tint: #E7F2EC; --watch-tint: #F8F0DC; --neg-tint: #F7E5E5;
  --masthead: #0B1F3A; --masthead-ink: #FFFFFF; --masthead-slate: #A9B8CC; --accent: #0B1F3A;
  --accent-ink: #FFFFFF;
  --input: #FFFFFF; --shadow: 0 1px 2px rgba(11,31,58,.05);
""",
    "dark": """
  --ink: #E8EDF5; --page: #0C1320; --panel: #121A28; --slate: #93A3B8; --rule: #24324A;
  --soft: #1B2638; --brass: #D4A961; --brass-tint: #2A2416; --blue: #6E9BC9;
  --pos: #5FBE8F; --watch: #E0B055; --neg: #E07A80;
  --pos-tint: #17301F; --watch-tint: #332715; --neg-tint: #35191C;
  --masthead: #060C16; --masthead-ink: #F2F6FC; --masthead-slate: #8FA3BE; --accent: #D4A961;
  --accent-ink: #11182A;
  --input: #1A2435; --shadow: none;
""",
}

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&display=swap');

html, body, .stApp, .stMarkdown, p, li, label, input, textarea, button, td, th, div[data-baseweb] {
  font-family: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
}
.stApp { background: var(--page); color: var(--ink); }
.block-container { padding-top: 3.2rem !important; max-width: 1360px; }
header[data-testid="stHeader"] { background: var(--page); }
header[data-testid="stHeader"] svg, header[data-testid="stHeader"] button { color: var(--ink); fill: var(--ink); }
.num { font-variant-numeric: tabular-nums; }

/* ---------- masthead ---------- */
.masthead { background: var(--masthead); color: var(--masthead-ink); margin: 0; padding: 1.1rem 1.6rem 1rem;
            display: flex; justify-content: space-between; align-items: flex-end; gap: 2rem; flex-wrap: wrap; }
.masthead .brand { font-family: 'Source Serif 4', Georgia, serif; font-size: 1.65rem; font-weight: 600; letter-spacing: .01em; }
.masthead .desk { color: var(--masthead-slate); font-size: .92rem; margin-top: .15rem; }
.masthead .meta { text-align: right; color: var(--masthead-slate); font-size: .85rem; line-height: 1.5; }
.masthead .meta b { color: var(--masthead-ink); font-weight: 600; }
.status { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: .4rem; vertical-align: middle; }
.status.live { background: #5FB88A; } .status.demo { background: var(--brass); }

/* ---------- process line ---------- */
.process { display: flex; flex-wrap: wrap; gap: 0; border: 1px solid var(--rule); border-top: none;
           margin: 0 0 1.6rem; background: var(--panel); padding: 0 1.6rem; }
.process .stage { padding: .8rem 1.4rem .7rem 0; margin-right: 1.4rem; color: var(--slate); opacity: .6;
                  font-size: .9rem; border-bottom: 2px solid transparent; }
.process .stage b { font-weight: 600; margin-right: .45rem; font-variant-numeric: tabular-nums; }
.process .stage.done { color: var(--slate); opacity: 1; }
.process .stage.now { color: var(--ink); opacity: 1; border-bottom-color: var(--ink); font-weight: 600; }

/* ---------- headings ---------- */
h1, h2, h3, .display { font-family: 'Source Serif 4', 'IBM Plex Sans', serif !important; color: var(--ink); letter-spacing: -0.01em; }
.h-section { font-family: 'Source Serif 4', Georgia, serif; font-size: 1.55rem; font-weight: 600; color: var(--ink);
             margin: 1.4rem 0 .15rem; }
.h-sub { color: var(--slate); font-size: .95rem; margin-bottom: .9rem; max-width: 80ch; }
.h-minor { font-size: 1rem; font-weight: 600; color: var(--ink); margin: 1.2rem 0 .5rem;
           padding-bottom: .35rem; border-bottom: 1px solid var(--rule); }

/* ---------- report header ---------- */
.report { background: var(--panel); border: 1px solid var(--rule); border-top: 3px solid var(--brass);
          padding: 1.2rem 1.4rem 1.1rem; margin-top: 1.2rem; box-shadow: var(--shadow); }
.report .kicker { color: var(--slate); font-size: .88rem; }
.report .title { font-family: 'Source Serif 4', Georgia, serif; font-size: 2rem; font-weight: 600; line-height: 1.15; margin: .15rem 0 .35rem; }
.report .thesis { font-size: 1.02rem; color: var(--ink); max-width: 90ch; line-height: 1.55; }

/* ---------- metric strip ---------- */
.strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); background: var(--panel);
         border: 1px solid var(--rule); border-top: none; }
.cell { padding: .8rem 1.1rem; border-right: 1px solid var(--rule); }
.cell:last-child { border-right: none; }
.cell .label { color: var(--slate); font-size: .8rem; }
.cell .value { font-size: 1.55rem; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.3; }
.cell .delta { font-size: .82rem; font-variant-numeric: tabular-nums; }
.delta.pos { color: var(--pos); } .delta.neg { color: var(--neg); } .delta.flat { color: var(--slate); }
.bar { height: 4px; background: var(--soft); margin-top: .45rem; }
.bar span { display: block; height: 4px; background: var(--brass); }

/* ---------- comps table ---------- */
.comps-wrap { overflow-x: auto; background: var(--panel); border: 1px solid var(--rule); }
table.comps { border-collapse: collapse; width: 100%; font-size: .85rem; font-variant-numeric: tabular-nums; color: var(--ink); }
table.comps th { text-align: right; font-weight: 600; color: var(--slate); font-size: .8rem; padding: .6rem .6rem;
                 border-bottom: 1px solid var(--ink); white-space: nowrap; background: var(--panel); }
table.comps th, table.comps td { border-left: none !important; border-right: none !important; }
table.comps th:first-child, table.comps td:first-child { text-align: left; position: sticky; left: 0; z-index: 1;
                                                       background: var(--panel); }
table.comps td { text-align: right; padding: .5rem .6rem; border-bottom: 1px solid var(--rule); white-space: nowrap; }
table.comps tr.focal td { background: var(--brass-tint); font-weight: 600; }
table.comps tr.focal td:first-child { background: var(--brass-tint); box-shadow: inset 3px 0 0 var(--brass); }
table.comps tr.median td { border-top: 1px solid var(--ink); border-bottom: none; color: var(--slate); font-style: italic; }
table.comps td.Green { color: var(--pos); } table.comps td.Red { color: var(--neg); }
table.comps td.Amber { color: var(--watch); }

/* ---------- findings ---------- */
.finding { display: grid; grid-template-columns: 2.2rem 1fr; background: var(--panel); border: 1px solid var(--rule);
           border-left: 3px solid var(--slate); padding: .8rem 1rem; margin-bottom: .5rem; }
.finding.Red { border-left-color: var(--neg); } .finding.Amber { border-left-color: var(--watch); }
.finding.Green { border-left-color: var(--pos); }
.finding .idx { font-family: 'Source Serif 4', Georgia, serif; font-size: 1.25rem; color: var(--slate); }
.finding .what { font-weight: 600; }
.finding .flag { font-size: .78rem; color: var(--slate); margin-left: .5rem; font-weight: 500; }
.finding .body { color: var(--ink); line-height: 1.5; margin-top: .15rem; }
.strengths { background: var(--panel); border: 1px solid var(--rule); padding: .8rem 1rem; line-height: 1.7; }
.strengths .item { color: var(--ink); } .strengths .item::before { content: "▲"; color: var(--pos); font-size: .7rem; margin-right: .5rem; }

/* ---------- Streamlit widgets: explicit in both themes ---------- */
section[data-testid="stSidebar"] { background: var(--panel); border-right: 1px solid var(--rule); }
section[data-testid="stSidebar"] *, div[data-testid="stSidebarContent"] * { color: var(--ink); }
section[data-testid="stSidebar"] h3 { font-family: 'Source Serif 4', Georgia, serif; color: var(--ink); }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: var(--slate) !important; }
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * { color: var(--ink) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--slate) !important; }
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"],
[data-testid="stTickBarMin"], [data-testid="stTickBarMax"] { color: var(--slate) !important; }
div[data-testid="stRadio"] label p, div[data-testid="stCheckbox"] label p,
div[data-testid="stToggle"] label p { color: var(--ink) !important; }
/* Streamlit's select and text inputs render as unlabelled emotion divs, so style them by container. */
[data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div,
[data-testid="stTextInput"] > div > div, div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div, div[data-baseweb="base-input"],
div[data-testid="stNumberInputContainer"] { background: var(--input) !important; border-color: var(--rule) !important;
                                            color: var(--ink) !important; }
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input,
[data-testid="stSelectbox"] div[value], div[data-baseweb="select"] * { color: var(--ink); }
div[data-baseweb="select"] svg, div[data-testid="stNumberInputContainer"] svg { fill: var(--slate); }
ul[data-baseweb="menu"], div[data-baseweb="popover"] div { background: var(--panel) !important; color: var(--ink) !important; }
div[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid var(--rule); gap: 1.4rem; }
div[data-testid="stTabs"] button { font-weight: 500; padding-left: 0; padding-right: 0;
                                   color: var(--slate) !important; }
div[data-testid="stTabs"] button * { color: inherit !important; }
div[data-testid="stTabs"] button[aria-selected="true"] { color: var(--ink) !important; font-weight: 600; }
div[data-baseweb="tab-highlight"] { background-color: var(--accent) !important; }
div[data-baseweb="tag"] { border-radius: 2px !important; background: var(--accent) !important; }
div[data-baseweb="tag"] span, div[data-baseweb="tag"] svg { color: var(--accent-ink) !important; fill: var(--accent-ink) !important; }
button[data-testid="stBaseButton-primary"] { border-radius: 2px; background: var(--accent); border: 1px solid var(--accent);
                                             color: var(--accent-ink); font-weight: 600; padding: .55rem 1.3rem; }
button[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.1); color: var(--accent-ink); }
button[data-testid="stBaseButton-secondary"] { border-radius: 2px; background: var(--panel); color: var(--ink);
                                               border: 1px solid var(--rule); }
div[data-testid="stButtonGroup"] button { border-radius: 2px !important; font-size: .86rem; background: var(--panel);
                                          color: var(--ink); border: 1px solid var(--rule); }
div[data-testid="stButtonGroup"] button p { color: var(--ink); }
div[data-testid="stButtonGroup"] button[kind="pillsActive"], div[data-testid="stButtonGroup"] button[aria-checked="true"],
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] {
  background: var(--accent) !important; border-color: var(--accent) !important; }
div[data-testid="stButtonGroup"] button[kind="pillsActive"] p,
div[data-testid="stButtonGroup"] button[aria-checked="true"] p,
div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] p { color: var(--accent-ink) !important; }
div[data-testid="stDownloadButton"] button { border-radius: 2px; font-weight: 600; }
div[data-testid="stExpander"] details { border-radius: 2px; border-color: var(--rule); background: var(--panel); }
div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary * { color: var(--ink); }
div[data-testid="stPlotlyChart"] { background: var(--panel); border: 1px solid var(--rule); padding: .4rem; }
div[data-testid="stAlertContainer"] { background: var(--soft); color: var(--ink); border: 1px solid var(--rule); }
div[data-testid="stAlertContainer"] * { color: var(--ink); }
div[data-testid="stMetricValue"], div[data-testid="stMetricLabel"] * { color: var(--ink); }
div[data-testid="stDataFrame"] { border: 1px solid var(--rule); }
.note-src { color: var(--slate); font-size: .8rem; margin-top: .35rem; }
hr, div[data-testid="stSidebar"] hr { border-color: var(--rule); }
:focus-visible { outline: 2px solid var(--accent) !important; outline-offset: 2px; }
@media (max-width: 800px) {
  .masthead, .process { padding-left: 1rem; padding-right: 1rem; }
  .masthead .meta { text-align: left; }
  .process .stage { padding-right: .5rem; margin-right: .6rem; font-size: .8rem; }
  .report .title { font-size: 1.5rem; }
  .cell { border-right: none; border-bottom: 1px solid var(--rule); }
}
</style>
"""


def css(dark=False):
    """The stylesheet with the chosen palette. Variables are declared here, so every rule above
    follows the theme and nothing depends on Streamlit's own light or dark base."""
    return "<style>:root {" + PALETTES["dark" if dark else "light"] + "}</style>" + BASE_CSS


def masthead(mode_is_live, source_label):
    status = "live" if mode_is_live else "demo"
    label = "Live market data" if mode_is_live else "Demo data (synthetic)"
    today = dt.date.today().strftime("%d %b %Y")
    return (f'<div class="masthead"><div><div class="brand">PeerLens</div>'
            f'<div class="desk">Peer comparables for the Nifty 500</div></div>'
            f'<div class="meta"><span class="status {status}"></span><b>{label}</b><br>'
            f'Universe: {html.escape(source_label)}. {today}</div></div>')


def process_line(current):
    stages = ["Universe", "Peer set", "Analysis", "Export"]
    parts = []
    for i, name in enumerate(stages, 1):
        state = "done" if i < current else "now" if i == current else ""
        parts.append(f'<div class="stage {state}"><b>{i}</b>{name}</div>')
    return '<div class="process">' + "".join(parts) + "</div>"
