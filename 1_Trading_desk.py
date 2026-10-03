"""Trading desk: a live order book and three automated strategies on a synthetic market.

This is a separate Streamlit page, so the peer-analysis app in app.py is untouched. The session is a
deterministic replay from the market open, which means the market appears to run continuously through
the trading day without any background process, and every viewer sees the same book.
"""
import html

import pandas as pd
import streamlit as st

from peerlens import charts, market, market_charts, synthetic
from peerlens.pipeline import run_analysis
from peerlens.theme import css
from peerlens.universe import load_nifty500

st.set_page_config(page_title="PeerLens trading desk", page_icon="📈", layout="wide")
dark = st.session_state.get("dark_mode", False)
st.markdown(css(dark), unsafe_allow_html=True)
charts.use_dark(dark)

REFRESH_SECONDS = 10


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_universe():
    return load_nifty500()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_health(industry, companies, seed):
    """The composite health score from the peer analysis — the trading bot's fundamental input."""
    data = synthetic.generate_financials(companies, industry, seed)
    result = run_analysis(data, companies.company.iloc[0], mode="synthetic")
    latest = result.health[result.health.year == result.year]
    return dict(zip(latest.company, latest.health_score, strict=True)), result.year


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def get_session(symbol, health_score, ticks, day_key, seed):
    """Cached per refresh window so the whole desk replays once, not once per chart."""
    return market.run_session(symbol, health_score, ticks, pd.Timestamp(day_key), seed)


universe, source = get_universe()

with st.sidebar:
    st.markdown("### Desk settings")
    st.toggle("Dark mode", value=dark, key="dark_mode")
    seed = st.number_input("Random seed", 1, 9999, 42,
                           help="Same seed and same day reproduce the session exactly.")
    live = st.toggle("Live ticking", value=True, help=f"Re-reads the book every {REFRESH_SECONDS} seconds.")
    st.caption("Synthetic market. Prices are index levels opening at 100 and are not quotes for any "
               "real security.")

ticks, clock, day = market.session_ticks()
status = "open" if ticks < market.TICKS_PER_SESSION else "closed"
st.markdown(f'<div class="masthead"><div><div class="brand">PeerLens trading desk</div>'
            f'<div class="desk">Order book, execution and automated strategies on a synthetic market'
            f'</div></div><div class="meta"><span class="status {"live" if status == "open" else "demo"}">'
            f'</span><b>Market {status}</b><br>{day:%d %b %Y}, tick {ticks:,} of '
            f'{market.TICKS_PER_SESSION:,}</div></div>', unsafe_allow_html=True)

counts = universe.groupby("industry").size().sort_values(ascending=False)
left, right = st.columns([3, 2], gap="large")
with left:
    industry = st.selectbox("Industry", list(counts.index), index=0)
with right:
    members = universe[universe.industry == industry].reset_index(drop=True)
    company = st.selectbox("Listed company", members.company.tolist())

scores, year = get_health(industry, members[["company", "symbol"]], seed)
health = scores.get(company, 50.0)
symbol = members.loc[members.company == company, "symbol"].iloc[0]


@st.fragment(run_every=REFRESH_SECONDS if live else None)
def desk():
    now_ticks, _, today = market.session_ticks()
    result = get_session(symbol, health, now_ticks, f"{today:%Y-%m-%d}", seed)
    stats = market.microstructure(result)
    performance = market.performance_table(result)
    anchor = result["anchor"]

    cells = [
        ("Last", f"{stats['last']:.2f}", f"{stats['day_return']:+.2%} on the day",
         "pos" if stats["day_return"] >= 0 else "neg"),
        ("Fair value", f"{anchor:.2f}", f"health score {health:.0f}/100 ({year})", "flat"),
        ("Spread", "—" if stats["spread"] is None else f"{stats['spread']:.2f}",
         f"bid {stats['best_bid'] or '—'} / ask {stats['best_ask'] or '—'}", "flat"),
        ("Trades", f"{stats['trades']:,}", f"{stats['volume']:,} shares", "flat"),
        ("VWAP", f"{stats['vwap']:.2f}", f"{stats['buy_share']:.0%} buyer-initiated", "flat"),
    ]
    st.markdown('<div class="strip" style="border-top:1px solid var(--rule)">' + "".join(
        f'<div class="cell"><div class="label">{html.escape(a)}</div><div class="value">{b}</div>'
        f'<div class="delta {d}">{html.escape(c)}</div></div>' for a, b, c, d in cells) + "</div>",
        unsafe_allow_html=True)

    tape_col, book_col = st.columns([7, 3], gap="medium")
    with tape_col:
        st.plotly_chart(market_charts.price_tape(result["prices"], market.candles(result["prices"]), anchor),
                        config={"displayModeBar": False}, key="tape")
    with book_col:
        st.plotly_chart(market_charts.book_ladder(result["book"].depth(8), result["book"].best_bid,
                                                  result["book"].best_ask),
                        config={"displayModeBar": False}, key="ladder")

    st.markdown('<div class="h-minor">Automated strategies</div>', unsafe_allow_html=True)
    fundamental = performance[performance.strategy == "Fundamental bot"].iloc[0]
    verdict = ("below" if stats["last"] < anchor else "above")
    st.markdown(
        f'<div class="report" style="margin-top:0"><div class="kicker">{html.escape(company)} '
        f'({html.escape(symbol)}), {day:%d %b %Y}</div><div class="thesis">The market is trading '
        f'{verdict} the value its fundamentals justify, so the fundamental bot is '
        f'{"long" if fundamental.position > 0 else "short" if fundamental.position < 0 else "flat"} '
        f'{abs(int(fundamental.position)):,} shares after {int(fundamental.fills)} fills, for '
        f'₹{fundamental.pnl:,.0f} on the day.</div></div>', unsafe_allow_html=True)

    pnl_col, equity_col = st.columns(2, gap="medium")
    with pnl_col:
        st.plotly_chart(market_charts.pnl_bars(performance, "Fundamental bot"),
                        config={"displayModeBar": False}, key="pnl")
    with equity_col:
        st.plotly_chart(market_charts.equity_curves(result["equity"], "Fundamental bot"),
                        config={"displayModeBar": False}, key="equity")

    flow = market_charts.trade_flow(result["trades"])
    if flow is not None:
        st.plotly_chart(flow, config={"displayModeBar": False}, key="flow")

    detail, tape = st.tabs(["Strategy detail", "Trade tape"])
    with detail:
        table = performance.rename(columns={
            "strategy": "Strategy", "fills": "Fills", "position": "Position", "cash": "Cash (₹)",
            "fees": "Fees (₹)", "pnl": "P&L (₹)", "pnl_per_fill": "P&L per fill (₹)",
            "exposure": "Exposure (₹)"})
        st.dataframe(table, hide_index=True, column_config={
            c: st.column_config.NumberColumn(format="%,.0f")
            for c in ["Cash (₹)", "Fees (₹)", "P&L (₹)", "Exposure (₹)", "P&L per fill (₹)"]})
        st.markdown(
            '<div class="note-src">The market maker quotes both sides and earns the spread from '
            'uninformed flow, skewing its quotes against its own inventory. The momentum bot trades a '
            'moving-average crossover. The fundamental bot is the link to the peer analysis: its fair '
            'value is set by the company\'s composite health score, so it buys weakness in a sound '
            'company and sells strength in a weak one. Fees are 2 basis points a side.</div>',
            unsafe_allow_html=True)
    with tape:
        recent = result["book"].tape(60)
        if len(recent):
            recent = recent.rename(columns={"tick": "Tick", "price": "Price", "quantity": "Qty",
                                            "aggressor": "Aggressor", "buyer": "Buyer", "seller": "Seller"})
            st.dataframe(recent.iloc[::-1], hide_index=True)
        else:
            st.caption("No trades yet in this session.")

    st.markdown(f'<div class="note-src">Replayed from the 09:15 open to tick {now_ticks:,}; '
                f'{market.TICK_SECONDS}-second ticks, {market.PRICE_STEP:.2f} tick size. The session is '
                'generated from the seed and the date, so it is identical for every viewer and can be '
                'replayed exactly.</div>', unsafe_allow_html=True)


desk()
