"""All Plotly figures, styled as research-desk exhibits: white panels, hairline grids, navy and slate
for the peer set, brass reserved for the focal company, muted signal colours."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

FONT = "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"

LIGHT = dict(
    ink="#0B1F3A", slate="#5B6B7F", rule="#E3E8EE", axis="#C9D1DB", guide="#9AA7B8",
    brass="#A8864F", paper="#FFFFFF", muted_fill="#DCE3EB", bar="#8A9BB0",
    peers=["#0B1F3A", "#6E9BC9", "#3D6A99", "#8A9BB0", "#1F4E79", "#A9B8C9", "#5B6B7F", "#C3CDD8"],
    tints={"Green": "#DCEFE4", "Amber": "#F6EACB", "Red": "#F3DADA", "n/a": "#EEF1F5"},
    diverging=[[0, "#A63D40"], [0.5, "#FFFFFF"], [1, "#2F5C8F"]],
    bands={"good": "rgba(46,125,91,0.05)", "bad": "rgba(166,61,64,0.05)"},
    focal_fill="rgba(168,134,79,0.18)",
)
DARK = dict(
    ink="#E8EDF5", slate="#93A3B8", rule="#24324A", axis="#33435E", guide="#5A6E8C",
    brass="#D4A961", paper="#121A28", muted_fill="#243246", bar="#5E7593",
    peers=["#8FB6E0", "#4E7EB5", "#A9C6E6", "#6E8FB3", "#C3D6EA", "#3F6490", "#93A3B8", "#D7E3F0"],
    tints={"Green": "#1C3A2C", "Amber": "#453418", "Red": "#44232A", "n/a": "#232E3F"},
    diverging=[[0, "#C96A6D"], [0.5, "#121A28"], [1, "#6E9BC9"]],
    bands={"good": "rgba(110,200,160,0.07)", "bad": "rgba(220,120,125,0.07)"},
    focal_fill="rgba(212,169,97,0.22)",
)
PALETTE = dict(LIGHT)

# Module-level names kept for readability; use_dark() rebinds them so every figure follows the theme.
INK, SLATE, RULE, BRASS, PAPER = (PALETTE["ink"], PALETTE["slate"], PALETTE["rule"],
                                  PALETTE["brass"], PALETTE["paper"])
AXIS, GUIDE, MUTED_FILL, BAR = PALETTE["axis"], PALETTE["guide"], PALETTE["muted_fill"], PALETTE["bar"]
PEER_PALETTE, SIGNAL_TINT = PALETTE["peers"], PALETTE["tints"]
SIGNAL = {"Green": "#2E7D5B", "Amber": "#B7862C", "Red": "#A63D40"}


def use_dark(dark=True):
    """Switch every chart to the dark or light palette. Call once per run, before building figures."""
    global PALETTE, INK, SLATE, RULE, BRASS, PAPER, AXIS, GUIDE, MUTED_FILL, BAR, PEER_PALETTE, SIGNAL_TINT
    PALETTE = dict(DARK if dark else LIGHT)
    INK, SLATE, RULE = PALETTE["ink"], PALETTE["slate"], PALETTE["rule"]
    BRASS, PAPER = PALETTE["brass"], PALETTE["paper"]
    AXIS, GUIDE = PALETTE["axis"], PALETTE["guide"]
    MUTED_FILL, BAR = PALETTE["muted_fill"], PALETTE["bar"]
    PEER_PALETTE, SIGNAL_TINT = PALETTE["peers"], PALETTE["tints"]


def company_colors(companies, focal):
    colors, others = {}, iter(PEER_PALETTE * 3)
    for company in companies:
        colors[company] = BRASS if company == focal else next(others)
    return colors


def _style(fig, height=420, legend=True):
    fig.update_layout(
        height=height, paper_bgcolor=PAPER, plot_bgcolor=PAPER,
        font=dict(family=FONT, color=INK, size=12),
        margin=dict(l=10, r=16, t=36, b=10), showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11, color=SLATE), title_text=""),
        hoverlabel=dict(bgcolor=PAPER, bordercolor=SLATE, font=dict(family=FONT, color=INK, size=12)),
    )
    fig.update_xaxes(gridcolor=RULE, zerolinecolor=AXIS, linecolor=AXIS, ticks="outside",
                     tickcolor=AXIS, tickfont=dict(color=SLATE))
    fig.update_yaxes(gridcolor=RULE, zerolinecolor=AXIS, linecolor=AXIS, tickfont=dict(color=SLATE))
    return fig


def legend_below(fig):
    """For half-width exhibits: legend under the plot so it never collides with the title."""
    return fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.22, x=0, xanchor="left"),
                             margin=dict(b=100))


def exhibit_title(fig, text):
    fig.update_layout(title=dict(text=text, x=0.01, xanchor="left", y=0.985, yanchor="top", yref="container",
                                 font=dict(size=13, color=INK, family=FONT)))
    top = 82 if fig.layout.showlegend is not False else 48
    fig.update_layout(margin=dict(t=max(fig.layout.margin.t or 0, top)))
    return fig


# ---------------------------------------------------------------- market maps
def universe_map(universe, selected_industry=None):
    """Treemap of the Nifty 500: one tile per industry, sized by number of constituents."""
    counts = universe.groupby("industry").size().sort_values(ascending=False)
    colors = [BRASS if i == selected_industry else (MUTED_FILL if selected_industry else PALETTE["peers"][1])
              for i in counts.index]
    text_colors = [PAPER if (i == selected_industry or not selected_industry) else SLATE for i in counts.index]
    fig = go.Figure(go.Treemap(
        labels=list(counts.index), parents=[""] * len(counts), values=list(counts.values),
        marker=dict(colors=colors, line=dict(color=PAPER, width=2)), tiling=dict(pad=0),
        pathbar=dict(visible=False),
        texttemplate="<b>%{label}</b><br>%{value} cos", textfont=dict(family=FONT, color=text_colors, size=12),
        hovertemplate="<b>%{label}</b><br>%{value} constituents<extra></extra>"))
    return _style(fig, height=430, legend=False).update_layout(margin=dict(l=0, r=0, t=0, b=0))


def industry_map(members, peers, focal):
    """Treemap of one industry, tiles sized by market cap. Focal in brass, peers in navy, the rest grey."""
    data = members.copy()
    fill = data["market_cap"].median() if data["market_cap"].notna().any() else 1.0
    data["size"] = data["market_cap"].fillna(fill)
    colors = [BRASS if c == focal else PALETTE["peers"][1] if c in peers else MUTED_FILL for c in data.company]
    fonts = [PAPER if (c == focal or c in peers) else SLATE for c in data.company]
    caps = data["market_cap"].map(lambda v: f"₹{v:,.0f} cr" if pd.notna(v) else "n/a")
    fig = go.Figure(go.Treemap(
        labels=data.company, parents=[""] * len(data), values=data["size"], customdata=caps,
        marker=dict(colors=colors, line=dict(color=PAPER, width=2)), tiling=dict(pad=0),
        pathbar=dict(visible=False),
        texttemplate="<b>%{label}</b><br>%{customdata}", textfont=dict(family=FONT, color=fonts, size=12),
        hovertemplate="<b>%{label}</b><br>Market cap %{customdata}<extra></extra>"))
    return _style(fig, height=460, legend=False).update_layout(margin=dict(l=0, r=0, t=0, b=0))


# ---------------------------------------------------------------- positioning (animated)
def peer_map(ratio_values, clean, focal, x_key="net_debt_to_ebitda", y_key="roce"):
    frame = ratio_values.merge(clean[["symbol", "year", "revenue"]], on=["symbol", "year"])
    frame = frame.dropna(subset=[x_key, y_key, "revenue"]).sort_values(["year", "company"])
    if frame.empty:
        return None
    frame["revenue"] = frame["revenue"].clip(lower=1)
    colors = company_colors(sorted(frame.company.unique()), focal)
    pad_x = (frame[x_key].max() - frame[x_key].min()) * 0.15 + 0.2
    pad_y = (frame[y_key].max() - frame[y_key].min()) * 0.15 + 0.02
    fig = px.scatter(
        frame, x=x_key, y=y_key, size="revenue", color="company", animation_frame="year",
        animation_group="company", color_discrete_map=colors, size_max=58, hover_name="company",
        range_x=[frame[x_key].min() - pad_x, frame[x_key].max() + pad_x],
        range_y=[frame[y_key].min() - pad_y, frame[y_key].max() + pad_y],
        labels={x_key: "Net debt / EBITDA (x)", y_key: "ROCE", "revenue": "Revenue (₹ cr)"})
    fig.update_traces(marker=dict(line=dict(width=1, color=PAPER), opacity=0.9))
    fig.update_yaxes(tickformat=".0%")
    fig.add_vline(x=1.5, line=dict(color=GUIDE, dash="dot", width=1))
    fig.add_hline(y=0.15, line=dict(color=GUIDE, dash="dot", width=1))
    fig.add_annotation(xref="paper", yref="paper", x=0.01, y=0.99, showarrow=False, xanchor="left",
                       text="Higher return, lower leverage", font=dict(color=SLATE, size=11))
    fig.add_annotation(xref="paper", yref="paper", x=0.99, y=0.01, showarrow=False, xanchor="right",
                       text="Lower return, higher leverage", font=dict(color=SLATE, size=11))
    if fig.layout.sliders:
        fig.layout.sliders[0].currentvalue.prefix = ""
        fig.layout.sliders[0].pad = dict(t=50, r=40)
        fig.layout.sliders[0].currentvalue.font = dict(color=INK, size=13)
    if fig.layout.updatemenus:
        play = fig.layout.updatemenus[0].buttons[0].args[1]
        play["frame"]["duration"] = 900
        play["transition"]["duration"] = 600
        play["transition"]["easing"] = "cubic-in-out"
    # open on the latest year, the same year as the rest of the report
    if fig.frames:
        last = len(fig.frames) - 1
        fig = go.Figure(data=fig.frames[last].data, layout=fig.layout, frames=fig.frames)
        if fig.layout.sliders:
            fig.layout.sliders[0].active = last
    fig = _style(fig, height=540)
    return exhibit_title(fig, "Return on capital against leverage (bubble size = revenue)")


# ---------------------------------------------------------------- scorecard
def rag_heatmap(ratio_values, rag, ratios, year, focal=None):
    snapshot = ratio_values[ratio_values.year == year].set_index("company").sort_index()
    status = rag[rag.year == year].set_index("company").sort_index()
    codes = {"Red": 0, "Amber": 1, "Green": 2, "n/a": 3}
    z = [[codes[status.loc[c, r.key]] for r in ratios] for c in snapshot.index]
    text = [[r.format(snapshot.loc[c, r.key]) for r in ratios] for c in snapshot.index]
    tints = PALETTE["tints"]
    scale = [[0, tints["Red"]], [0.25, tints["Red"]], [0.25, tints["Amber"]],
             [0.5, tints["Amber"]], [0.5, tints["Green"]], [0.75, tints["Green"]],
             [0.75, tints["n/a"]], [1, tints["n/a"]]]
    labels = [f"<b>{c}</b>" if c == focal else c for c in snapshot.index]
    fig = go.Figure(go.Heatmap(
        z=z, x=[r.short for r in ratios], y=labels, text=text, texttemplate="%{text}",
        textfont=dict(family=FONT, size=12, color=INK), colorscale=scale, zmin=0, zmax=3, showscale=False,
        xgap=2, ygap=2, hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False, ticks="")
    fig.update_xaxes(side="top", showgrid=False, ticks="", tickfont=dict(color=INK))
    fig = _style(fig, height=110 + 46 * len(snapshot), legend=False)
    return fig.update_layout(margin=dict(l=10, r=36, t=40, b=10))


def health_ranking(health, year, focal):
    snapshot = health[health.year == year].sort_values("health_score")
    colors = [BRASS if c == focal else BAR for c in snapshot.company]
    fig = go.Figure(go.Bar(
        x=snapshot.health_score, y=snapshot.company, orientation="h", marker=dict(color=colors),
        text=snapshot.health_score.map(lambda v: f"{v:.0f}"), textposition="outside",
        textfont=dict(color=INK), width=0.55, hovertemplate="%{y}: %{x:.0f}/100<extra></extra>"))
    fig.update_xaxes(range=[0, 108], title=None)
    fig = _style(fig, height=90 + 40 * len(snapshot), legend=False)
    return exhibit_title(fig, "Composite health score (0 = every ratio red, 100 = every ratio green)")


# ---------------------------------------------------------------- profile
def peer_radar(percentiles, ratios, focal):
    labels = [r.short for r in ratios]
    fig = go.Figure()
    colors = company_colors(list(percentiles.index), focal)
    fig.add_trace(go.Scatterpolar(r=[50] * (len(labels) + 1), theta=labels + labels[:1], name="Peer median",
                                  line=dict(color=GUIDE, dash="dot", width=1), hoverinfo="skip"))
    for company in percentiles.index:
        values = [percentiles.loc[company, r.key] for r in ratios]
        values = [v if pd.notna(v) else 0 for v in values]
        is_focal = company == focal
        fig.add_trace(go.Scatterpolar(
            r=values + values[:1], theta=labels + labels[:1], name=company,
            fill="toself" if is_focal else None, fillcolor=PALETTE["focal_fill"] if is_focal else None,
            line=dict(color=colors[company], width=2.4 if is_focal else 1.2),
            visible=True if is_focal else "legendonly"))
    fig.update_layout(polar=dict(bgcolor=PAPER,
                                 radialaxis=dict(range=[0, 100], gridcolor=RULE, linecolor=RULE,
                                                 tickfont=dict(size=9, color=SLATE)),
                                 angularaxis=dict(gridcolor=RULE, linecolor=AXIS,
                                                  tickfont=dict(size=11, color=INK))))
    fig = _style(fig, height=540)
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.06, x=0.5, xanchor="center"),
                      margin=dict(l=50, r=50, t=50, b=40))
    return exhibit_title(fig, "Percentile rank within the peer set on each ratio (100 = best)")


# ---------------------------------------------------------------- trends
def ratio_trend(ratio_values, ratio, focal):
    frame = ratio_values.dropna(subset=[ratio.key]).sort_values("year")
    colors = company_colors(sorted(frame.company.unique()), focal)
    fig = go.Figure()
    values = frame[ratio.key]
    if len(values):
        low, high = min(values.min(), ratio.amber) * 0.9, max(values.max(), ratio.green) * 1.1
        if ratio.higher_is_better:
            bands = [(ratio.green, high, PALETTE["bands"]["good"]), (low, ratio.amber, PALETTE["bands"]["bad"])]
        else:
            bands = [(low, ratio.green, PALETTE["bands"]["good"]), (ratio.amber, high, PALETTE["bands"]["bad"])]
        for y0, y1, color in bands:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=color, line_width=0, layer="below")
        for level in (ratio.green, ratio.amber):
            fig.add_hline(y=level, line=dict(color=AXIS, dash="dot", width=1))
    for company, group in frame.groupby("company"):
        is_focal = company == focal
        fig.add_trace(go.Scatter(
            x=group.year, y=group[ratio.key], name=company, mode="lines+markers",
            line=dict(color=colors[company], width=3 if is_focal else 1.4),
            marker=dict(size=8 if is_focal else 5, symbol="square" if is_focal else "circle"),
            hovertemplate=f"{company}<br>%{{x}}: %{{y}}<extra></extra>"))
    if ratio.unit == "%":
        fig.update_yaxes(tickformat=".0%")
    fig = _style(fig, height=460)
    return exhibit_title(fig, f"{ratio.name} by financial year (dotted lines = green and amber thresholds)")


def price_performance(prices, names, focal):
    colors = company_colors(sorted(names.values()), focal)
    fig = go.Figure()
    for symbol in prices.columns:
        name = names.get(symbol, symbol)
        is_focal = name == focal
        fig.add_trace(go.Scatter(x=prices.index, y=prices[symbol], name=name, mode="lines",
                                 line=dict(color=colors.get(name, SLATE), width=2.6 if is_focal else 1.2),
                                 hovertemplate=f"{name}<br>%{{x|%d %b %Y}}: %{{y:.1f}}<extra></extra>"))
    fig.add_hline(y=100, line=dict(color=GUIDE, dash="dot", width=1))
    fig = _style(fig, height=460)
    return exhibit_title(fig, "Total return, rebased to 100 twelve months ago")


# ---------------------------------------------------------------- macro sensitivity
def macro_dashboard(macro):
    from plotly.subplots import make_subplots
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for column, name, color, dash in [("gdp_growth", "Real GDP growth", PALETTE["peers"][0], "solid"),
                                      ("cpi_inflation", "CPI inflation", BRASS, "solid"),
                                      ("repo_rate", "Policy repo rate", PALETTE["peers"][1], "dot")]:
        fig.add_trace(go.Scatter(x=macro.year, y=macro[column], name=name, mode="lines+markers",
                                 line=dict(color=color, width=2, dash=dash), marker=dict(size=5),
                                 hovertemplate=f"{name}<br>%{{x}}: %{{y:.1%}}<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=macro.year, y=macro.inr_usd, name="INR per USD (right axis)", mode="lines",
                             line=dict(color=PALETTE["peers"][5], width=1.5),
                             hovertemplate="INR per USD<br>%{x}: %{y:.1f}<extra></extra>"), secondary_y=True)
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    fig.update_yaxes(tickformat=".0%", secondary_y=False)
    fig.update_yaxes(showgrid=False, secondary_y=True, tickfont=dict(color=SLATE))
    fig = _style(fig, height=430)
    return exhibit_title(fig, "Simulated macro environment")


def gdp_scatter(panel, sensitivity, pooled, focal):
    colors = company_colors(sorted(panel.company.unique()), focal)
    fig = go.Figure()
    for company, group in panel.groupby("company"):
        is_focal = company == focal
        fig.add_trace(go.Scatter(
            x=group.gdp_growth, y=group.revenue_growth, mode="markers", name=company,
            marker=dict(color=colors[company], size=10 if is_focal else 7, line=dict(color=PAPER, width=1),
                        symbol="square" if is_focal else "circle"),
            customdata=group.year, hovertemplate=f"{company}<br>%{{customdata}}<br>GDP %{{x:.1%}}, "
                                                 f"revenue %{{y:.1%}}<extra></extra>"))
    if pd.notna(pooled["gdp_beta"]):
        xs = np.linspace(panel.gdp_growth.min(), panel.gdp_growth.max(), 20)
        intercept = panel.revenue_growth.mean() - pooled["gdp_beta"] * panel.gdp_growth.mean()
        fig.add_trace(go.Scatter(x=xs, y=intercept + pooled["gdp_beta"] * xs, mode="lines",
                                 name=f"Industry fit (beta {pooled['gdp_beta']:.2f})",
                                 line=dict(color=PALETTE["peers"][0], width=2, dash="dash"), hoverinfo="skip"))
    fig.update_xaxes(tickformat=".0%", title="Real GDP growth")
    fig.update_yaxes(tickformat=".0%", title="Revenue growth")
    fig = legend_below(_style(fig, height=520))
    fig = exhibit_title(fig, "Revenue growth vs GDP growth")
    return fig.update_layout(margin=dict(t=48))


def beta_bars(sensitivity, focal, true_beta=None):
    data = sensitivity.dropna(subset=["beta"]).sort_values("beta")
    colors = [BRASS if c == focal else BAR for c in data.company]
    fig = go.Figure(go.Bar(
        x=data.beta, y=data.company, orientation="h", marker=dict(color=colors), width=0.55,
        error_x=dict(type="data", array=1.96 * data.se, color=SLATE, thickness=1, width=4),
        customdata=np.stack([data.profile, data.p_value], axis=1),
        hovertemplate="%{y}<br>GDP beta %{x:.2f}<br>%{customdata[0]}, p = %{customdata[1]:.3f}<extra></extra>"))
    fig.add_vline(x=1.0, line=dict(color=GUIDE, dash="dot", width=1))
    fig.add_annotation(x=1.0, y=1.02, yref="paper", text="moves 1:1 with GDP", showarrow=False,
                       font=dict(size=10, color=SLATE))
    if true_beta is not None:
        fig.add_vline(x=true_beta, line=dict(color=BRASS, dash="dash", width=1.5))
        fig.add_annotation(x=true_beta, y=-0.08, yref="paper", text=f"built-in {true_beta:.2f}",
                           showarrow=False, font=dict(size=10, color=BRASS))
    fig.update_xaxes(title="GDP beta, with 95% intervals")
    fig = _style(fig, height=120 + 44 * len(data), legend=False)
    return exhibit_title(fig, "Cyclicality by company")


def correlation_heatmap(corr):
    scale = PALETTE["diverging"]
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=list(corr.columns), y=list(corr.index), zmin=-1, zmax=1, colorscale=scale,
        text=corr.round(2).values, texttemplate="%{text}", textfont=dict(family=FONT, size=12, color=INK),
        xgap=2, ygap=2, colorbar=dict(thickness=10, tickfont=dict(color=SLATE)),
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False, ticks="")
    fig.update_xaxes(showgrid=False, ticks="", tickangle=-30)
    fig = _style(fig, height=470, legend=False)
    return exhibit_title(fig, "Correlation of year-on-year changes")


def moving_average_chart(table, window=3):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=table.year, y=table.industry_growth, name="Industry revenue growth (median)",
                         marker=dict(color=MUTED_FILL)))
    fig.add_trace(go.Scatter(x=table.year, y=table[f"industry_{window}y_ma"], name=f"Industry, {window}-year average",
                             mode="lines", line=dict(color=BRASS, width=2.5)))
    fig.add_trace(go.Scatter(x=table.year, y=table[f"gdp_{window}y_ma"], name=f"GDP, {window}-year average",
                             mode="lines", line=dict(color=PALETTE["peers"][0], width=2.5)))
    fig.update_yaxes(tickformat=".0%")
    fig = legend_below(_style(fig, height=470))
    fig = exhibit_title(fig, f"Industry vs GDP growth, {window}-year moving averages")
    return fig.update_layout(margin=dict(t=48))
