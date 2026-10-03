"""Charts for the trading desk. Colours come from peerlens.charts, so these follow the dark-mode
toggle like every other exhibit in the app."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import charts as base


def _style(fig, height=420, legend=True):
    return base._style(fig, height=height, legend=legend)


def book_ladder(depth, best_bid, best_ask, levels=8):
    """Depth of market: resting size at each price, bids below, asks above — the ladder a trader
    watches to judge whether a price level will hold."""
    bids = depth[depth.side == "bid"].sort_values("price", ascending=False).head(levels)
    asks = depth[depth.side == "ask"].sort_values("price").head(levels)
    frame = pd.concat([asks.iloc[::-1], bids])
    colors = [base.SIGNAL["Red"] if side == "ask" else base.SIGNAL["Green"] for side in frame.side]
    fig = go.Figure(go.Bar(
        x=frame.quantity, y=[f"{p:.2f}" for p in frame.price], orientation="h",
        marker=dict(color=colors, opacity=0.75), text=frame.quantity, textposition="outside",
        cliponaxis=False, textfont=dict(color=base.INK),
        hovertemplate="%{y}: %{x} shares resting<extra></extra>"))
    fig.update_yaxes(type="category", autorange="reversed", title=None)
    fig.update_xaxes(title="Resting quantity", range=[0, frame.quantity.max() * 1.25])
    fig = _style(fig, height=90 + 32 * len(frame), legend=False)
    spread = "—" if best_bid is None or best_ask is None else f"{best_ask - best_bid:.2f}"
    return base.exhibit_title(fig, f"Order book — bid {best_bid or '—'} / ask {best_ask or '—'}, spread {spread}")


def price_tape(prices, candles_frame, anchor, trades=None):
    """Candlesticks from the tick mids, with the fundamental fair value as a reference line."""
    fig = go.Figure()
    if len(candles_frame):
        fig.add_trace(go.Candlestick(
            x=candles_frame.time, open=candles_frame.open, high=candles_frame.high,
            low=candles_frame.low, close=candles_frame.close, name="Price",
            increasing=dict(line=dict(color=base.SIGNAL["Green"]), fillcolor=base.SIGNAL["Green"]),
            decreasing=dict(line=dict(color=base.SIGNAL["Red"]), fillcolor=base.SIGNAL["Red"])))
    fig.add_trace(go.Scatter(x=prices.time, y=prices.fair_value, name="Fair value (fundamentals)",
                             mode="lines", line=dict(color=base.BRASS, width=2, dash="dot"),
                             hovertemplate="Fair value %{y:.2f}<extra></extra>"))
    fig.add_hline(y=anchor, line=dict(color=base.GUIDE, dash="dash", width=1),
                  annotation_text=f"health-score anchor {anchor:.2f}", annotation_position="top left",
                  annotation_font=dict(color=base.SLATE, size=11))
    fig.update_layout(xaxis_rangeslider_visible=False)
    fig.update_yaxes(title="Index level (open = 100)")
    fig = _style(fig, height=470)
    return base.exhibit_title(fig, "Traded price against fundamental fair value")


def equity_curves(equity, focal=None):
    """Mark-to-market money made by each strategy through the session."""
    fig = go.Figure()
    names = [c for c in equity.columns if c not in ("tick", "time")]
    colors = dict(zip(sorted(names), base.PALETTE["peers"], strict=False))
    if focal in colors:
        colors[focal] = base.BRASS
    for name in names:
        is_focal = name == focal
        fig.add_trace(go.Scatter(x=equity.time, y=equity[name], name=name, mode="lines",
                                 line=dict(color=colors[name], width=3 if is_focal else 1.6),
                                 hovertemplate=f"{name}<br>%{{y:,.0f}}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=base.AXIS, width=1))
    fig.update_yaxes(title="Mark-to-market P&L (₹)")
    fig = _style(fig, height=430)
    return base.exhibit_title(fig, "Strategy P&L through the session")


def trade_flow(trades, bucket_ticks=300):
    """Buyer-initiated against seller-initiated volume: who is leaning on the market."""
    if not trades:
        return None
    frame = pd.DataFrame([(t.tick, t.quantity, t.aggressor) for t in trades],
                         columns=["tick", "quantity", "aggressor"])
    frame["bucket"] = frame.tick // bucket_ticks * bucket_ticks
    pivot = frame.pivot_table(index="bucket", columns="aggressor", values="quantity", aggfunc="sum").fillna(0)
    fig = go.Figure()
    if "buy" in pivot:
        fig.add_trace(go.Bar(x=pivot.index, y=pivot["buy"], name="Buyer-initiated",
                             marker=dict(color=base.SIGNAL["Green"], opacity=0.75)))
    if "sell" in pivot:
        fig.add_trace(go.Bar(x=pivot.index, y=-pivot["sell"], name="Seller-initiated",
                             marker=dict(color=base.SIGNAL["Red"], opacity=0.75)))
    fig.update_layout(barmode="relative")
    fig.update_xaxes(title="Tick")
    fig.update_yaxes(title="Shares")
    fig = _style(fig, height=380)
    return base.exhibit_title(fig, "Aggressive order flow")


def pnl_bars(performance, focal=None):
    data = performance.sort_values("pnl")
    colors = [base.BRASS if s == focal else base.BAR for s in data.strategy]
    fig = go.Figure(go.Bar(
        x=data.pnl, y=data.strategy, orientation="h", marker=dict(color=colors), width=0.55,
        text=[f"₹{v:,.0f}" for v in data.pnl], textposition="outside", cliponaxis=False,
        textfont=dict(color=base.INK),
        customdata=np.stack([data.fills, data.position], axis=1),
        hovertemplate="%{y}<br>P&L %{x:,.0f}<br>%{customdata[0]} fills, position %{customdata[1]}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=base.AXIS, width=1))
    span = max(abs(data.pnl.min()), abs(data.pnl.max()), 1)      # headroom for the outside labels
    fig.update_xaxes(title="P&L (₹)", range=[data.pnl.min() - span * 0.35, data.pnl.max() + span * 0.35])
    fig = _style(fig, height=110 + 44 * len(data), legend=False)
    return base.exhibit_title(fig, "Session P&L by strategy")
