"""PeerLens: Nifty 500 industry peer analysis.

Run locally:  streamlit run app.py
"""
import html

import pandas as pd
import streamlit as st

from peerlens import charts, live, macro, synthetic
from peerlens.excel_export import ExcelDashboard
from peerlens.pipeline import run_analysis
from peerlens.ratios import RATIO_BY_KEY, RatioEngine
from peerlens.schema import LABELS
from peerlens.theme import css, masthead, process_line
from peerlens.universe import load_nifty500

st.set_page_config(page_title="PeerLens: Nifty 500 peer analysis", page_icon="📊", layout="wide")

LIVE, DEMO = "Live market data", "Demo data (offline)"
MIN_PEERS, MAX_PEERS = 2, 8

# Styling is applied before any widget renders, using the toggle's stored value from the previous run.
st.markdown(css(st.session_state.get("dark_mode", False)), unsafe_allow_html=True)
charts.use_dark(st.session_state.get("dark_mode", False))


# ------------------------------------------------------------------ cached data access
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_universe():
    return load_nifty500()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_snapshot(mode, industry, members, seed):
    if mode == DEMO:
        return synthetic.generate_market_snapshot(members, industry, seed)
    return live.fetch_market_snapshot(members)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_financials(mode, industry, peers, seed, inject_errors):
    if mode == DEMO:
        return synthetic.generate_financials(peers, industry, seed, inject_errors), []
    return live.fetch_many_financials(peers)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_market(mode, industry, peers, seed):
    if mode == DEMO:
        prices = synthetic.generate_prices(peers["symbol"].tolist(), seed)
        valuation = synthetic.generate_market_snapshot(peers, industry, seed)[["symbol", "pe", "pb"]]
        return prices, valuation
    prices = live.fetch_prices(peers["yahoo_symbol"].tolist())
    valuation = live.fetch_valuation(peers["yahoo_symbol"].tolist())
    return prices, valuation


ANALYSIS_KEYS = ("analysis", "raw", "chosen", "failed", "workbook")


def clear_analysis():
    for key in ANALYSIS_KEYS:
        st.session_state.pop(key, None)


def switch_to_demo():
    st.session_state["mode"] = DEMO
    clear_analysis()


def reset_from(step):
    """Changing an earlier choice clears everything computed after it."""
    if step <= 1:
        st.session_state.pop("peer_select", None)
        st.session_state.pop("focal_select", None)
    clear_analysis()


def show_live_error(error):
    reason = str(error).rstrip(". ")
    st.error(f"Yahoo Finance did not return data ({reason}). It limits how often a server can ask. "
             "Wait a few minutes and try again, or switch to demo data to keep working.")
    st.button("Switch to demo data", on_click=switch_to_demo, type="primary")


def signed(ratio, value, median):
    """Difference from the peer median, phrased in the ratio's own unit, with a direction class."""
    if pd.isna(value) or pd.isna(median):
        return "no peer comparison", "flat"
    diff = value - median
    good = diff > 0 if ratio.higher_is_better else diff < 0
    css = "flat" if abs(diff) < 1e-9 else ("pos" if good else "neg")
    if ratio.unit == "%":
        text = f"{diff * 100:+.1f} pp vs peers"
    elif ratio.unit == "days":
        text = f"{diff:+.0f} days vs peers"
    else:
        text = f"{diff:+.2f}x vs peers"
    return text, css


def _fmt(value, spec, suffix=""):
    return "n/a" if value is None or pd.isna(value) else f"{value:{spec}}{suffix}"


def comps_table(result, market, focal):
    """The trading-comps table an analyst would paste into a note."""
    year = result.year
    snap = result.ratio_values[result.ratio_values.year == year].set_index("company")
    revenue = result.clean.pivot_table(index="company", columns="year", values="revenue", aggfunc="first")
    latest_rev = revenue[year] if year in revenue else pd.Series(dtype=float)
    earlier = [y for y in revenue.columns if y < year]
    prior_rev = revenue[earlier].ffill(axis=1).iloc[:, -1] if earlier else pd.Series(dtype=float)
    growth = latest_rev / prior_rev - 1
    health = result.health[result.health.year == year].set_index("company")["health_score"]
    market = market.set_index("company") if market is not None else pd.DataFrame()
    market_cap = market["market_cap"] if "market_cap" in market else pd.Series(dtype=float)
    pe = market["pe"] if "pe" in market else pd.Series(dtype=float)

    keys = [r.key for r in result.ratios]
    ratio_cols = [k for k in ["ebitda_margin", "roce", "roe", "net_debt_to_ebitda", "interest_coverage"] if k in keys]
    order = health.sort_values(ascending=False).index.tolist()

    def row_cells(company):
        cells = [f"<td>{html.escape(company)}</td>", f"<td>{_fmt(market_cap.get(company), ',.0f')}</td>",
                 f"<td>{_fmt(pe.get(company), '.1f', 'x')}</td>", f"<td>{_fmt(latest_rev.get(company), ',.0f')}</td>",
                 f"<td>{_fmt(growth.get(company), '+.1%')}</td>"]
        for key in ratio_cols:
            ratio, value = RATIO_BY_KEY[key], snap.loc[company, key] if company in snap.index else float("nan")
            cells.append(f'<td class="{ratio.rate(value).replace("/", "")}">{ratio.format(value)}</td>')
        cells.append(f"<td>{_fmt(health.get(company), '.0f')}</td>")
        return "".join(cells)

    header = ("<tr><th>Company</th><th>Mkt cap (₹ cr)</th><th>P/E</th><th>Revenue (₹ cr)</th><th>Rev. growth</th>"
              + "".join(f"<th>{RATIO_BY_KEY[k].short}</th>" for k in ratio_cols) + "<th>Score</th></tr>")
    rows = [f'<tr class="{"focal" if c == focal else ""}">{row_cells(c)}</tr>' for c in order]
    median = [f"<td>Median, all {len(order)}</td>", f"<td>{_fmt(market_cap.reindex(order).median(), ',.0f')}</td>",
              f"<td>{_fmt(pe.reindex(order).median(), '.1f', 'x')}</td>",
              f"<td>{_fmt(latest_rev.reindex(order).median(), ',.0f')}</td>",
              f"<td>{_fmt(growth.reindex(order).median(), '+.1%')}</td>"]
    median += [f"<td>{RATIO_BY_KEY[k].format(snap[k].median())}</td>" for k in ratio_cols]
    median.append(f"<td>{_fmt(health.median(), '.0f')}</td>")
    rows.append(f'<tr class="median">{"".join(median)}</tr>')
    return f'<div class="comps-wrap"><table class="comps">{header}{"".join(rows)}</table></div>'


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### Settings")
    dark = st.toggle("Dark mode", value=False, key="dark_mode",
                     help="Switches the whole report, charts included.")
    charts.use_dark(dark)
    mode = st.radio("Data source", [LIVE, DEMO], key="mode", on_change=reset_from, args=(1,),
                    help="Live pulls statements and prices from Yahoo Finance. Demo generates realistic "
                         "synthetic statements, works offline and is never rate-limited.")
    seed, inject = 42, False
    if mode == DEMO:
        seed = st.number_input("Random seed", 1, 9999, 42, on_change=reset_from, args=(2,),
                               help="Same seed, same numbers. Change it for a different synthetic market.")
        inject = st.toggle("Plant data-entry errors", value=True, on_change=reset_from, args=(2,),
                           help="Adds a missing value, a sign error and a duplicate row so you can watch "
                                "the data-quality checks catch and fix them.")
        st.caption("Demo figures are synthetic and are not the reported financials of these companies.")
    else:
        st.caption("Annual statements from Yahoo Finance, converted to ₹ crore; usually the last four "
                   "financial years.")
    st.divider()
    if st.button("Refresh cached data"):
        st.cache_data.clear()
        reset_from(1)
        st.rerun()

universe, universe_source = get_universe()
st.markdown(masthead(mode == LIVE, universe_source), unsafe_allow_html=True)
process_slot = st.empty()

# ------------------------------------------------------------------ 1. universe
left, right = st.columns([5, 7], gap="large")
with left:
    st.markdown('<div class="h-section">Select an industry</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="h-sub">{len(universe)} constituents across {universe.industry.nunique()} '
                'NSE industry classifications.</div>', unsafe_allow_html=True)
    counts = universe.groupby("industry").size().sort_values(ascending=False)
    industry = st.pills("Industry", options=list(counts.index), key="industry",
                        format_func=lambda name: f"{name} ({counts[name]})", label_visibility="collapsed",
                        on_change=reset_from, args=(1,), wrap=True)
with right:
    st.plotly_chart(charts.universe_map(universe, industry), config={"displayModeBar": False}, key="universe")
    st.markdown('<div class="note-src">Tile area = number of index constituents. Source: NSE Nifty 500 list.</div>',
                unsafe_allow_html=True)

if not industry:
    process_slot.markdown(process_line(1), unsafe_allow_html=True)
    st.stop()

members = universe[universe.industry == industry].reset_index(drop=True)
if len(members) < MIN_PEERS:
    process_slot.markdown(process_line(1), unsafe_allow_html=True)
    st.warning(f"{industry} has only {len(members)} constituent in the Nifty 500, so there is no peer set. "
               "Select another industry.")
    st.stop()

# ------------------------------------------------------------------ 2. peer set
st.markdown(f'<div class="h-section">Build the peer set: {html.escape(industry)}</div>', unsafe_allow_html=True)
st.markdown('<div class="h-sub">Tile area is market capitalisation. The focal company is shown in brass, '
            'selected peers in navy.</div>', unsafe_allow_html=True)
try:
    with st.spinner(f"Loading market capitalisation for {len(members)} companies…"):
        snapshot = get_snapshot(mode, industry, members[["company", "symbol", "yahoo_symbol"]], seed)
except Exception as error:
    # Market caps only size the tiles and rank the defaults; the analysis can proceed without them
    st.warning(f"Market capitalisation is unavailable right now ({str(error).rstrip('. ')}). Tiles are shown at equal size "
               "and companies in alphabetical order; the financial analysis is unaffected.")
    snapshot = pd.DataFrame({"symbol": members["symbol"], "market_cap": float("nan")})

members = members.merge(snapshot[["symbol", "market_cap"]], on="symbol", how="left")
members = members.sort_values("market_cap", ascending=False, na_position="last").reset_index(drop=True)
default_peers = members.company.head(5).tolist()

picker, tiles = st.columns([4, 8], gap="large")
with picker:
    options = members.company.tolist()
    if "peer_select" not in st.session_state or not set(st.session_state["peer_select"]) <= set(options):
        st.session_state["peer_select"] = default_peers
    peers = st.multiselect(f"Peer set ({MIN_PEERS} to {MAX_PEERS} companies)", options, key="peer_select",
                           max_selections=MAX_PEERS, on_change=reset_from, args=(2,))
    if st.session_state.get("focal_select") not in peers:
        st.session_state["focal_select"] = peers[0] if peers else None
    focal = st.selectbox("Focal company", peers, key="focal_select",
                         help="The company the findings are written for.")
    run = st.button("Run peer analysis", type="primary", disabled=len(peers) < MIN_PEERS)
    if len(peers) < MIN_PEERS:
        st.caption(f"Select at least {MIN_PEERS} companies.")
with tiles:
    st.plotly_chart(charts.industry_map(members, peers, focal), config={"displayModeBar": False}, key="industry_map")

if run:
    chosen = members[members.company.isin(peers)][["company", "symbol", "yahoo_symbol"]].reset_index(drop=True)
    try:
        with st.spinner("Fetching statements and running data checks…"):
            raw, failed = get_financials(mode, industry, chosen, seed, inject)
            clear_analysis()
            st.session_state["raw"] = raw
            st.session_state["failed"] = failed
            st.session_state["chosen"] = chosen
    except Exception as error:
        process_slot.markdown(process_line(2), unsafe_allow_html=True)
        show_live_error(error)
        st.stop()

if "raw" not in st.session_state:
    process_slot.markdown(process_line(2), unsafe_allow_html=True)
    st.stop()

# Re-run the (fast) analysis whenever the focal company changes; statements are not re-fetched
raw_companies = set(st.session_state["raw"].company)
focal_used = focal if focal in raw_companies else sorted(raw_companies)[0]
if st.session_state.get("analysis") is None or st.session_state["analysis"].focal != focal_used:
    st.session_state["analysis"] = run_analysis(st.session_state["raw"], focal_used,
                                                "synthetic" if mode == DEMO else "live")
    st.session_state.pop("workbook", None)

# ------------------------------------------------------------------ 3. analysis
process_slot.markdown(process_line(3), unsafe_allow_html=True)
result = st.session_state["analysis"]
chosen = st.session_state["chosen"]
year, focal = result.year, result.focal
if st.session_state.get("failed"):
    st.warning("No statements were returned for: " + ", ".join(st.session_state["failed"]) +
               ". They are excluded from the peer set.")

prices, valuation, market_error = None, None, None
try:
    prices, valuation = get_market(mode, industry, chosen, seed)
except Exception as error:
    market_error = error
market = chosen[["company", "symbol"]].merge(members[["symbol", "market_cap"]], on="symbol", how="left")
if valuation is not None:
    market = market.merge(valuation[["symbol", "pe"]], on="symbol", how="left")

snap = result.ratio_values[result.ratio_values.year == year]
focal_row = snap[snap.company == focal]
peer_median = snap[snap.company != focal][[r.key for r in result.ratios]].median()   # other peers only
score_series = result.health.loc[(result.health.company == focal) & (result.health.year == year), "health_score"]
score = float(score_series.iloc[0]) if len(score_series) and pd.notna(score_series.iloc[0]) else 0.0

peer_scores = result.health[result.health.year == year]["health_score"]
others = peer_scores[result.health.loc[peer_scores.index, "company"] != focal]
thesis = f"Composite score of {score:.0f}/100 against a peer median of {others.median():.0f}."
if result.strengths:
    thesis += " Ahead of peers on " + " and ".join(result.strengths[:2]) + "."
watch = [n["ratio"] for n in result.recommendations if not n["status"].startswith("Green")]
if watch:
    thesis += " Main watch item: " + watch[0].lower() + "."
thesis = html.escape(thesis)
st.markdown(f'<div class="report"><div class="kicker">{html.escape(industry)}, {year}, '
            f'{len(snap)}-company peer set</div>'
            f'<div class="title">{html.escape(focal)}: ranked {"joint " if result.tied else ""}{result.rank} of {len(snap)} on financial health</div>'
            f'<div class="thesis">{thesis}</div></div>', unsafe_allow_html=True)

cells = [f'<div class="cell score"><div class="label">Composite score</div>'
         f'<div class="value">{score:.0f}<span style="font-size:.9rem;color:#5B6B7F"> / 100</span></div>'
         f'<div class="bar"><span style="width:{score:.0f}%"></span></div></div>']
for key in ["roce", "ebitda_margin", "net_debt_to_ebitda", "roe"]:
    ratio = RATIO_BY_KEY[key]
    if ratio not in result.ratios or focal_row.empty:
        continue
    value = focal_row.iloc[0][key]
    text, css = signed(ratio, value, peer_median[key])
    cells.append(f'<div class="cell"><div class="label">{ratio.name}</div><div class="value">{ratio.format(value)}</div>'
                 f'<div class="delta {css}">{text}</div></div>')
st.markdown('<div class="strip">' + "".join(cells) + "</div>", unsafe_allow_html=True)

st.markdown('<div class="h-minor">Trading comparables</div>', unsafe_allow_html=True)
st.markdown(comps_table(result, market, focal), unsafe_allow_html=True)
st.markdown(f'<div class="note-src">₹ crore. {year} financials; market data as of the latest close. Ratio colour '
            'shows the rating against thresholds (green, amber, red). Sorted by composite score. The median row '
            'covers the whole set; comparisons elsewhere exclude the focal company.</div>',
            unsafe_allow_html=True)

findings_col, strengths_col = st.columns([7, 4], gap="large")
with findings_col:
    st.markdown('<div class="h-minor">Key findings</div>', unsafe_allow_html=True)
    for i, note in enumerate(result.recommendations, 1):
        status, _, flag = note["status"].partition(", ")
        st.markdown(f'<div class="finding {status.replace("/", "")}"><div class="idx">{i}</div><div>'
                    f'<span class="what">{html.escape(note["ratio"])}</span>'
                    f'<span class="flag">{html.escape(status)}{", " + html.escape(flag) if flag else ""}</span>'
                    f'<div class="body">{html.escape(note["text"])}</div></div></div>', unsafe_allow_html=True)
with strengths_col:
    st.markdown('<div class="h-minor">Relative strengths</div>', unsafe_allow_html=True)
    items = "".join(f'<div class="item">{html.escape(s)}</div>' for s in result.strengths) or \
        '<div>No ratio leads the peer median by more than 5%.</div>'
    st.markdown(f'<div class="strengths">{items}</div>', unsafe_allow_html=True)

st.markdown('<div class="h-minor">Exhibits</div>', unsafe_allow_html=True)
tab_map, tab_score, tab_shape, tab_trend, tab_macro, tab_market, tab_quality, tab_data = st.tabs(
    ["Positioning", "Scorecard", "Peer profile", "Trends", "Macro sensitivity", "Price performance",
     "Data quality", "Financials"])

with tab_map:
    figure = charts.peer_map(result.ratio_values, result.clean, focal)
    if figure is None:
        st.info("Net debt / EBITDA or ROCE is unavailable for this peer set.")
    else:
        st.plotly_chart(figure, config={"displayModeBar": False}, key="peermap")
        st.markdown('<div class="note-src">Press play to step through each financial year. Dotted lines mark the '
                    'green thresholds (ROCE 15%, net debt / EBITDA 1.5x).</div>', unsafe_allow_html=True)

with tab_score:
    st.plotly_chart(charts.rag_heatmap(result.ratio_values, result.rag, result.ratios, year, focal),
                    config={"displayModeBar": False}, key="heatmap")
    st.plotly_chart(charts.health_ranking(result.health, year, focal), config={"displayModeBar": False},
                    key="ranking")
    with st.expander("Rating methodology"):
        rows = [dict(Ratio=r.name, Category=r.category, Better="Higher" if r.higher_is_better else "Lower",
                     Green=r.format(r.green), Amber=r.format(r.amber)) for r in result.ratios]
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption("Green meets the first threshold, amber the second, red misses both; n/a means the line item "
                   "is not reported or the denominator is zero. Composite score: green 2, amber 1, red 0, "
                   "averaged over available ratios and scaled to 100.")

with tab_shape:
    percentiles = RatioEngine(result.ratios).peer_percentiles(result.ratio_values, year)
    st.plotly_chart(charts.peer_radar(percentiles, result.ratios, focal), config={"displayModeBar": False},
                    key="radar")
    st.markdown('<div class="note-src">Select names in the legend to overlay other peers.</div>',
                unsafe_allow_html=True)

with tab_trend:
    keys = [r.key for r in result.ratios]
    trend_ratio = st.selectbox("Ratio", result.ratios, format_func=lambda r: r.name,
                               index=keys.index("roce") if "roce" in keys else 0)
    st.plotly_chart(charts.ratio_trend(result.ratio_values, trend_ratio, focal), config={"displayModeBar": False},
                    key="trend")

with tab_macro:
    n_years = result.clean["year"].nunique()
    if mode == LIVE or n_years < macro.MIN_YEARS:
        st.info(f"Macro sensitivity needs at least {macro.MIN_YEARS} years of statements to estimate a reliable "
                f"slope; this peer set has {n_years}. Yahoo Finance supplies about four years, so this analysis "
                "runs on demo data, where ten years are generated alongside a simulated macro path. Connecting "
                "a real macro source (MoSPI, RBI) with longer statement history is the natural upgrade.")
    else:
        macro_path = macro.macro_for_years(sorted(result.clean["year"].unique()), seed)
        panel = macro.growth_panel(result.clean, macro_path)
        sensitivity = macro.gdp_sensitivity(panel)
        pooled = macro.pooled_sensitivity(panel)
        built_in = synthetic.true_gdp_beta(industry)

        st.markdown(f'<div class="report" style="margin-top:.4rem"><div class="kicker">Macro sensitivity, '
                    f'{html.escape(industry)}</div><div class="thesis">{html.escape(macro.headline(industry, pooled))}'
                    f'</div></div>', unsafe_allow_html=True)
        focal_beta = sensitivity.set_index("company")["beta"].get(focal, float("nan"))
        infl = pooled["inflation_margin_beta"]
        cells = [
            ("Industry GDP beta", f"{pooled['gdp_beta']:.2f}", pooled["profile"]),
            (f"{focal} GDP beta", "n/a" if pd.isna(focal_beta) else f"{focal_beta:.2f}", macro.classify(focal_beta)),
            ("Margin vs inflation", "n/a" if pd.isna(infl) else f"{infl:+.2f}",
             "margins squeezed by inflation" if infl < 0 else "margins hold up with inflation"),
            ("Check vs built-in beta", f"{built_in:.2f}",
             f"estimate off by {abs(pooled['gdp_beta'] - built_in):.2f}"),
        ]
        st.markdown('<div class="strip">' + "".join(
            f'<div class="cell"><div class="label">{html.escape(a)}</div><div class="value">{b}</div>'
            f'<div class="delta flat">{html.escape(c)}</div></div>' for a, b, c in cells) + "</div>",
            unsafe_allow_html=True)

        st.plotly_chart(charts.macro_dashboard(macro_path), config={"displayModeBar": False}, key="macro_path")
        left_col, right_col = st.columns(2, gap="medium")
        with left_col:
            st.plotly_chart(charts.gdp_scatter(panel, sensitivity, pooled, focal), config={"displayModeBar": False},
                            key="gdp_scatter")
        with right_col:
            st.plotly_chart(charts.beta_bars(sensitivity, focal, built_in), config={"displayModeBar": False},
                            key="beta_bars")
        left_col, right_col = st.columns(2, gap="medium")
        with left_col:
            st.plotly_chart(charts.correlation_heatmap(macro.change_correlations(macro_path, panel)),
                            config={"displayModeBar": False}, key="macro_corr")
            st.markdown('<div class="note-src">Uses growth rates and changes, not levels: trending levels '
                        '(GDP, prices, the rupee) all rise together and correlate spuriously.</div>',
                        unsafe_allow_html=True)
        with right_col:
            st.plotly_chart(charts.moving_average_chart(macro.moving_averages(macro_path, panel)),
                            config={"displayModeBar": False}, key="macro_ma")

        st.markdown('<div class="h-minor">Scenario: next year\'s GDP growth</div>', unsafe_allow_html=True)
        gdp_next = st.slider("Real GDP growth next year", -8.0, 12.0, 6.5, 0.5, format="%.1f%%") / 100
        projection = macro.scenario(sensitivity, gdp_next)
        st.dataframe(projection.rename(columns={"company": "Company", "beta": "GDP beta", "profile": "Profile",
                                                "projected_growth": "Projected revenue growth"})
                     [["Company", "GDP beta", "Profile", "Projected revenue growth"]],
                     hide_index=True, column_config={
                         "GDP beta": st.column_config.NumberColumn(format="%.2f"),
                         "Projected revenue growth": st.column_config.NumberColumn(format="percent")})
        st.markdown('<div class="note-src">The macro path is simulated, India-like but not official RBI or MoSPI '
                    'data. Its role is to drive the synthetic companies with a known sensitivity, so the built-in '
                    'beta lets us verify that the regression recovers it. Betas are OLS slopes (statsmodels) of '
                    'revenue growth on real GDP growth; intervals are 95%.</div>', unsafe_allow_html=True)

with tab_market:
    if prices is None:
        st.info(f"Price data is unavailable right now ({market_error}). The financial analysis is unaffected.")
    else:
        names = dict(zip(chosen.symbol, chosen.company, strict=True))
        st.plotly_chart(charts.price_performance(prices, names, focal), config={"displayModeBar": False},
                        key="prices")
        if mode == DEMO:
            st.markdown('<div class="note-src">Demo prices are simulated paths, not market history.</div>',
                        unsafe_allow_html=True)

with tab_quality:
    a, b, c = st.columns(3)
    a.metric("Issues in raw data", len(result.issues_before))
    b.metric("Automatic fixes", len(result.fixes))
    c.metric("Issues after cleaning", len(result.issues_after))
    if len(result.issues_before):
        st.dataframe(result.issues_before, hide_index=True)
    if len(result.fixes):
        st.dataframe(result.fixes, hide_index=True)
    if mode == LIVE:
        st.caption("Live data is never invented: blanks stay blank and the affected ratios show n/a.")

with tab_data:
    view = result.clean.rename(columns={**LABELS, "company": "Company", "symbol": "Symbol", "year": "Year"})
    st.dataframe(view, hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="%,.0f") for c in LABELS.values()})
    st.caption("₹ crore.")

# ------------------------------------------------------------------ 4. export
st.markdown('<div class="h-section">Export</div>', unsafe_allow_html=True)
st.markdown('<div class="h-sub">A live Excel workbook: ratios are formulas on the source data, the dashboard has '
            'company and year selectors, and the rating thresholds are editable.</div>', unsafe_allow_html=True)
source_label = ("Synthetic demo data generated by PeerLens (not reported financials)" if mode == DEMO
                else "Yahoo Finance annual statements via yfinance")
if "workbook" not in st.session_state:          # build once per analysis, not on every rerun
    macro_tables = None
    if mode == DEMO and result.clean["year"].nunique() >= macro.MIN_YEARS:
        path = macro.macro_for_years(sorted(result.clean["year"].unique()), seed)
        sens = macro.gdp_sensitivity(macro.growth_panel(result.clean, path))
        macro_tables = {"Macro path": path, "GDP sensitivity by company": sens}
    st.session_state["workbook"] = ExcelDashboard(
        result.clean, result.ratios, focal, year, industry, source_label, result.issues_before, result.fixes,
        result.recommendations, result.summary_line, macro_tables=macro_tables).to_bytes()
workbook = st.session_state["workbook"]
file_name = f"PeerLens_{industry.replace(' ', '_').replace('&', 'and')}_{year}.xlsx"
if st.download_button("Download Excel workbook", workbook, file_name=file_name, type="primary",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
    process_slot.markdown(process_line(5), unsafe_allow_html=True)
