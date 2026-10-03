"""A limit order book, a matching engine, and the agents that trade on it.

Why this sits inside PeerLens: the rest of the app answers "is this company sound?" from annual
statements. That answer is slow-moving. This module asks the opposite question on the opposite
timescale — "what is the market doing to this company right now?" — and then lets a strategy trade on
the slow answer. The fundamental agent's fair value comes from the composite health score the peer
analysis already produces, so the two halves of the app are joined: better fundamentals, higher fair
value, and the agent buys when the market trades below it.

Design notes
  * The book is a real price-time priority book: orders rest at a price, the earliest order at a
    price fills first, and an incoming order walks the opposite side until it is filled or priced out.
  * The market is **deterministic replay**, not a background process. Every tick is generated from a
    seed plus the tick number, so the state at any moment of the trading day is well defined and
    identical for every viewer. That gives a market that appears to run continuously without a server
    process, and makes a bug reproducible instead of a one-off.
  * Prices are index levels (the day opens at 100), matching the rebased price charts elsewhere.
"""
from collections import deque
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

TICK_SECONDS = 2                       # one simulated tick every two seconds of wall-clock time
SESSION_START = "09:15"                # NSE trading hours
SESSION_END = "15:30"
TICKS_PER_SESSION = int(((15 * 60 + 30) - (9 * 60 + 15)) * 60 / TICK_SECONDS)   # 11,250
PRICE_STEP = 0.05                      # minimum price increment (one paisa on a ₹100 index)
OPEN_PRICE = 100.0
BOOK_REPLAY_TICKS = 400                # how much of the tape is replayed for the live book view


def round_to_step(price):
    return round(round(price / PRICE_STEP) * PRICE_STEP, 2)


# --------------------------------------------------------------------------- order book
@dataclass(slots=True)
class Order:
    id: int
    side: str               # "buy" or "sell"
    price: float            # limit price; None for a market order
    quantity: int
    tick: int
    agent: str
    filled: int = 0

    @property
    def remaining(self):
        return self.quantity - self.filled


@dataclass(slots=True)
class Trade:
    tick: int
    price: float
    quantity: int
    aggressor: str          # the side that crossed the spread
    buyer: str
    seller: str


class OrderBook:
    """Price-time priority book. Resting orders are queued per price level in arrival order."""

    def __init__(self):
        self.bids: dict[float, deque[Order]] = {}
        self.asks: dict[float, deque[Order]] = {}
        self.orders: dict[int, Order] = {}
        self.trades: list[Trade] = []
        self._next_id = 1

    # -- inspection -------------------------------------------------------
    @property
    def best_bid(self):
        return max(self.bids) if self.bids else None

    @property
    def best_ask(self):
        return min(self.asks) if self.asks else None

    @property
    def mid(self):
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return self.trades[-1].price if self.trades else OPEN_PRICE
        return (bid + ask) / 2

    @property
    def spread(self):
        bid, ask = self.best_bid, self.best_ask
        return None if bid is None or ask is None else round(ask - bid, 2)

    def depth(self, levels=8):
        """Top `levels` price levels on each side, aggregated by price."""
        rows = []
        for price in sorted(self.bids, reverse=True)[:levels]:
            rows.append(dict(side="bid", price=price, quantity=sum(o.remaining for o in self.bids[price])))
        for price in sorted(self.asks)[:levels]:
            rows.append(dict(side="ask", price=price, quantity=sum(o.remaining for o in self.asks[price])))
        return pd.DataFrame(rows, columns=["side", "price", "quantity"])

    def open_orders(self, agent):
        return [o for o in self.orders.values() if o.agent == agent and o.remaining > 0]

    # -- mutation ---------------------------------------------------------
    def cancel(self, order_id):
        order = self.orders.pop(order_id, None)
        if order is None or order.remaining == 0:
            return False
        book = self.bids if order.side == "buy" else self.asks
        queue = book.get(order.price)
        if queue is not None:
            try:
                queue.remove(order)
            except ValueError:
                pass
            if not queue:
                del book[order.price]
        return True

    def cancel_all(self, agent):
        for order in list(self.open_orders(agent)):
            self.cancel(order.id)

    def submit(self, side, price, quantity, tick, agent):
        """Submit a limit order (price=None for a market order). Returns the Order."""
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        order = Order(id=self._next_id, side=side, price=None if price is None else round_to_step(price),
                      quantity=int(quantity), tick=tick, agent=agent)
        self._next_id += 1
        self._match(order)
        if order.remaining > 0 and order.price is not None:        # rest the unfilled remainder
            book = self.bids if side == "buy" else self.asks
            book.setdefault(order.price, deque()).append(order)
            self.orders[order.id] = order
        return order

    def _match(self, incoming):
        book = self.asks if incoming.side == "buy" else self.bids
        while incoming.remaining > 0 and book:
            best = min(book) if incoming.side == "buy" else max(book)
            if incoming.price is not None:
                crosses = incoming.price >= best if incoming.side == "buy" else incoming.price <= best
                if not crosses:
                    break
            queue = book[best]
            while queue and incoming.remaining > 0:
                resting = queue[0]
                size = min(incoming.remaining, resting.remaining)
                incoming.filled += size
                resting.filled += size
                buyer = incoming.agent if incoming.side == "buy" else resting.agent
                seller = resting.agent if incoming.side == "buy" else incoming.agent
                self.trades.append(Trade(tick=incoming.tick, price=best, quantity=size,
                                         aggressor=incoming.side, buyer=buyer, seller=seller))
                if resting.remaining == 0:
                    queue.popleft()
                    self.orders.pop(resting.id, None)
            if not queue:
                del book[best]

    def tape(self, last=50):
        return pd.DataFrame([asdict(t) for t in self.trades[-last:]])


# --------------------------------------------------------------------------- portfolio
@dataclass
class Portfolio:
    name: str
    cash: float = 0.0
    position: int = 0
    fees: float = 0.0
    trades: int = 0
    history: list = field(default_factory=list)       # (tick, equity)

    def fill(self, side, price, quantity, fee_rate=0.0002):
        value = price * quantity
        fee = value * fee_rate
        self.cash += -value - fee if side == "buy" else value - fee
        self.position += quantity if side == "buy" else -quantity
        self.fees += fee
        self.trades += 1

    def equity(self, mark):
        return self.cash + self.position * mark


# --------------------------------------------------------------------------- agents
class Agent:
    name = "agent"

    def act(self, book, tick, context, rng):
        raise NotImplementedError


class MarketMaker(Agent):
    """Quotes both sides around its fair value and skews the quote against its own inventory, which is
    how a real maker avoids accumulating a one-sided position."""

    name = "Market maker"

    def __init__(self, half_spread=0.12, size=35, inventory_limit=400, skew=0.0006, levels=5):
        self.half_spread, self.size = half_spread, size
        self.inventory_limit, self.skew = inventory_limit, skew
        self.levels = levels                      # quotes a ladder, not just the touch

    def act(self, book, tick, context, rng):
        portfolio = context["portfolios"][self.name]
        book.cancel_all(self.name)
        fair = context["fair_value"] - self.skew * portfolio.position
        width = self.half_spread * (1 + context["volatility_multiple"])
        for level in range(self.levels):
            offset = width + level * PRICE_STEP * 2
            size = int(self.size * (1 + level * 0.6))            # more size further from the touch
            if portfolio.position < self.inventory_limit:
                book.submit("buy", fair - offset, size, tick, self.name)
            if portfolio.position > -self.inventory_limit:
                book.submit("sell", fair + offset, size, tick, self.name)


class NoiseTrader(Agent):
    """Uninformed flow: arrives at random, crosses the spread, and is what the maker earns from."""

    name = "Noise flow"

    def __init__(self, arrival_rate=0.55, max_size=25, passive_share=0.4, cancel_after=90):
        self.arrival_rate, self.max_size = arrival_rate, max_size
        self.passive_share, self.cancel_after = passive_share, cancel_after

    def act(self, book, tick, context, rng):
        for order in book.open_orders(self.name):                 # stale passive orders are pulled
            if tick - order.tick > self.cancel_after:
                book.cancel(order.id)
        for _ in range(rng.poisson(self.arrival_rate)):
            side = "buy" if rng.random() < 0.5 else "sell"
            size = int(rng.integers(5, self.max_size))
            if rng.random() < self.passive_share:                 # rest inside the book
                away = PRICE_STEP * rng.integers(1, 6)
                price = book.mid - away if side == "buy" else book.mid + away
                book.submit(side, price, size, tick, self.name)
            else:
                book.submit(side, None, size, tick, self.name)


class MomentumBot(Agent):
    """Technical strategy: buys when the fast moving average crosses above the slow one."""

    name = "Momentum bot"

    def __init__(self, fast=20, slow=120, size=30, max_position=300):
        self.fast, self.slow, self.size, self.max_position = fast, slow, size, max_position

    def act(self, book, tick, context, rng):
        prices = context["mid_history"]
        if len(prices) < self.slow + 1:
            return
        fast = float(np.mean(prices[-self.fast:]))
        slow = float(np.mean(prices[-self.slow:]))
        previous = context["signals"].get(self.name, 0)
        signal = 1 if fast > slow else -1
        if signal == previous:
            return
        context["signals"][self.name] = signal
        portfolio = context["portfolios"][self.name]
        if signal > 0 and portfolio.position < self.max_position:
            book.submit("buy", None, self.size, tick, self.name)
        elif signal < 0 and portfolio.position > -self.max_position:
            book.submit("sell", None, self.size, tick, self.name)


class FundamentalBot(Agent):
    """The bridge to the rest of PeerLens. Its fair value comes from the company's composite health
    score, so it buys when the market trades below what the fundamentals justify and sells above.
    It will not add to a position once it is at its risk limit, and it trades at a limit price so it
    never pays the spread."""

    name = "Fundamental bot"

    def __init__(self, anchor=100.0, band=0.012, size=35, max_position=350, patience=45):
        self.anchor, self.band = anchor, band
        self.size, self.max_position, self.patience = size, max_position, patience

    def act(self, book, tick, context, rng):
        if tick % self.patience:
            return
        portfolio = context["portfolios"][self.name]
        mid = book.mid
        cheap, rich = self.anchor * (1 - self.band), self.anchor * (1 + self.band)
        book.cancel_all(self.name)
        if mid < cheap and portfolio.position < self.max_position:
            book.submit("buy", mid + PRICE_STEP, self.size, tick, self.name)
        elif mid > rich and portfolio.position > -self.max_position:
            book.submit("sell", mid - PRICE_STEP, self.size, tick, self.name)


# --------------------------------------------------------------------------- simulation
def fundamental_anchor(health_score, premium=0.35):
    """Turn a 0-100 composite health score into a fair-value index level around the 100 open.

    A score of 50 is fair value; every point above or below moves fair value by `premium`% of the
    open, so a 75-score company is worth about 9% more than a 50-score one."""
    if health_score is None or pd.isna(health_score):
        health_score = 50.0
    return OPEN_PRICE * (1 + (float(health_score) - 50.0) / 100.0 * premium)


def fair_value_path(ticks, anchor, seed, daily_vol=0.012, reversion=0.004):
    """An Ornstein-Uhlenbeck path: random walk that is pulled back toward the fundamental anchor.

    Mean reversion is what makes the fundamental bot profitable in the long run and is the standard
    model for a price that has an anchor it cannot drift away from forever."""
    rng = np.random.default_rng([seed, 11])
    step_vol = daily_vol * OPEN_PRICE / np.sqrt(max(ticks, 1))
    shocks = rng.normal(0, step_vol, ticks)
    path = np.empty(ticks)
    level = OPEN_PRICE
    for i in range(ticks):
        level += reversion * (anchor - level) + shocks[i]
        path[i] = level
    return path


def session_ticks(now=None, ticks_per_session=TICKS_PER_SESSION):
    """How many ticks of today's session have elapsed, in Indian market hours.

    Before the open the session is empty; after the close it is complete; at the weekend the last
    full session is shown. This is what makes the market look continuously live without a process
    running in the background."""
    now = pd.Timestamp.now(tz="Asia/Kolkata") if now is None else now
    if now.tzinfo is None:
        now = now.tz_localize("Asia/Kolkata")
    day = now.normalize()
    while day.weekday() >= 5:                                   # roll back over the weekend
        day -= pd.Timedelta(days=1)
    open_time = day + pd.Timedelta(hours=9, minutes=15)
    close_time = day + pd.Timedelta(hours=15, minutes=30)
    if now >= close_time or day != now.normalize():
        return ticks_per_session, close_time, day
    if now < open_time:                                          # before the bell: show yesterday
        previous = day - pd.Timedelta(days=1)
        while previous.weekday() >= 5:
            previous -= pd.Timedelta(days=1)
        return ticks_per_session, previous + pd.Timedelta(hours=15, minutes=30), previous
    elapsed = int((now - open_time).total_seconds() // TICK_SECONDS)
    return max(min(elapsed, ticks_per_session), 1), now, day


def day_seed(symbol, day, seed=42):
    import zlib
    return [seed, zlib.crc32(f"{symbol}|{day:%Y-%m-%d}".encode())]


def run_session(symbol, health_score, ticks, day, seed=42, agents=None):
    """Replay one trading session tick by tick through the matching engine.

    Returns a dict with the book, per-agent portfolios, the mid-price series and the trade tape."""
    anchor = fundamental_anchor(health_score)
    rng = np.random.default_rng(day_seed(symbol, day, seed))
    path = fair_value_path(ticks, anchor, seed=int(abs(hash((symbol, str(day)))) % (2**31)))

    agents = agents or [MarketMaker(), NoiseTrader(), MomentumBot(), FundamentalBot(anchor=anchor)]
    book = OrderBook()
    portfolios = {a.name: Portfolio(a.name) for a in agents}
    context = dict(portfolios=portfolios, signals={}, fair_value=path[0], mid_history=[OPEN_PRICE],
                   volatility_multiple=0.0, anchor=anchor)

    seen_trades, mids, equity_rows = 0, [], []
    recent = np.full(30, OPEN_PRICE)
    for tick in range(ticks):
        context["fair_value"] = path[tick]
        context["volatility_multiple"] = float(np.std(recent) / OPEN_PRICE * 60)
        for agent in agents:
            agent.act(book, tick, context, rng)
        for trade in book.trades[seen_trades:]:                  # settle the fills from this tick
            portfolios[trade.buyer].fill("buy", trade.price, trade.quantity)
            portfolios[trade.seller].fill("sell", trade.price, trade.quantity)
        seen_trades = len(book.trades)
        mid = book.mid
        mids.append(mid)
        context["mid_history"].append(mid)
        recent[tick % 30] = mid
        if tick % 60 == 0 or tick == ticks - 1:
            equity_rows.append(dict(tick=tick, **{name: p.equity(mid) for name, p in portfolios.items()}))

    open_time = pd.Timestamp(day) + pd.Timedelta(hours=9, minutes=15)
    times = open_time + pd.to_timedelta(np.arange(ticks) * TICK_SECONDS, unit="s")
    prices = pd.DataFrame({"time": times, "mid": mids, "fair_value": path[:ticks]})
    equity = pd.DataFrame(equity_rows)
    if len(equity):
        equity["time"] = open_time + pd.to_timedelta(equity["tick"] * TICK_SECONDS, unit="s")
    return dict(book=book, portfolios=portfolios, prices=prices, equity=equity, anchor=anchor,
                trades=book.trades, day=day, ticks=ticks)


def performance_table(result):
    """Per-strategy result: realised and unrealised money, inventory, fills and return on the day."""
    mark = result["prices"]["mid"].iloc[-1] if len(result["prices"]) else OPEN_PRICE
    rows = []
    for name, portfolio in result["portfolios"].items():
        notional = max(abs(portfolio.position) * mark, 1.0)
        rows.append(dict(strategy=name, fills=portfolio.trades, position=portfolio.position,
                         cash=portfolio.cash, fees=portfolio.fees, pnl=portfolio.equity(mark),
                         pnl_per_fill=portfolio.equity(mark) / portfolio.trades if portfolio.trades else np.nan,
                         exposure=notional))
    return pd.DataFrame(rows).sort_values("pnl", ascending=False).reset_index(drop=True)


def candles(prices, bucket="5min"):
    """Resample the tick mids into OHLC bars for a candlestick chart."""
    if prices.empty:
        return prices
    frame = prices.set_index("time")["mid"].resample(bucket).ohlc().dropna()
    return frame.reset_index()


def microstructure(result):
    """Headline order-book statistics an execution desk would quote."""
    book, prices = result["book"], result["prices"]
    trades = result["trades"]
    volume = sum(t.quantity for t in trades)
    turnover = sum(t.quantity * t.price for t in trades)
    buy_volume = sum(t.quantity for t in trades if t.aggressor == "buy")
    returns = prices["mid"].pct_change().dropna()
    return dict(
        last=prices["mid"].iloc[-1] if len(prices) else np.nan,
        fair_value=result["anchor"],
        spread=book.spread,
        best_bid=book.best_bid, best_ask=book.best_ask,
        trades=len(trades), volume=volume, turnover=turnover,
        vwap=turnover / volume if volume else np.nan,
        buy_share=buy_volume / volume if volume else np.nan,
        realised_vol=float(returns.std() * np.sqrt(len(returns))) if len(returns) > 2 else np.nan,
        day_return=(prices["mid"].iloc[-1] / OPEN_PRICE - 1) if len(prices) else np.nan,
    )
