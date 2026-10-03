"""Order book and strategy tests. Run with:  python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from peerlens.market import (OPEN_PRICE, OrderBook, Portfolio, candles, fundamental_anchor,
                             microstructure, performance_table, run_session, session_ticks)


def test_price_time_priority():
    """Two orders at the same price fill in arrival order; a better price always fills first."""
    book = OrderBook()
    first = book.submit("sell", 101, 10, 0, "A")
    second = book.submit("sell", 101, 10, 1, "B")
    better = book.submit("sell", 100, 5, 2, "C")
    book.submit("buy", 101, 20, 3, "taker")
    assert [t.seller for t in book.trades] == ["C", "A", "B"]
    assert better.remaining == 0 and first.remaining == 0 and second.filled == 5


def test_book_never_crosses_and_rests_the_remainder():
    book = OrderBook()
    book.submit("sell", 101, 10, 0, "A")
    book.submit("buy", 102, 25, 1, "B")        # crosses, fills 10, rests 15 at 102
    assert book.best_ask is None and book.best_bid == 102
    book.submit("sell", 100, 5, 2, "C")        # crosses into the resting bid
    assert book.best_bid == 102 and book.best_ask is None
    for trade in book.trades:
        assert trade.quantity > 0


def test_market_order_walks_the_book_and_does_not_rest():
    book = OrderBook()
    book.submit("sell", 100, 10, 0, "A")
    book.submit("sell", 101, 10, 0, "B")
    order = book.submit("buy", None, 25, 1, "taker")
    assert [t.price for t in book.trades] == [100, 101]
    assert order.filled == 20 and book.best_ask is None      # the unfilled 5 is discarded, not rested


def test_cancel_removes_liquidity_and_is_idempotent():
    book = OrderBook()
    order = book.submit("buy", 99, 10, 0, "A")
    assert book.cancel(order.id) is True
    assert book.cancel(order.id) is False and book.best_bid is None


def test_rejects_bad_orders():
    book = OrderBook()
    with pytest.raises(ValueError):
        book.submit("hold", 100, 10, 0, "A")
    with pytest.raises(ValueError):
        book.submit("buy", 100, 0, 0, "A")


def test_every_trade_conserves_shares_and_cash():
    """Across the whole session, positions must net to zero and cash must net to minus the fees."""
    result = run_session("TEST", 70, 1500, pd.Timestamp("2026-10-02"))
    portfolios = result["portfolios"].values()
    assert sum(p.position for p in portfolios) == 0
    total_cash = sum(p.cash for p in portfolios)
    total_fees = sum(p.fees for p in portfolios)
    assert abs(total_cash + total_fees) < 1e-6


def test_session_is_reproducible():
    a = run_session("TEST", 70, 800, pd.Timestamp("2026-10-02"))
    b = run_session("TEST", 70, 800, pd.Timestamp("2026-10-02"))
    pd.testing.assert_frame_equal(a["prices"], b["prices"])
    assert performance_table(a).equals(performance_table(b))


def test_fundamentals_set_fair_value_and_the_bot_follows_them():
    """A sound company should trade up to its anchor with the bot long; a weak one the other way."""
    assert fundamental_anchor(50) == pytest.approx(OPEN_PRICE)
    assert fundamental_anchor(85) > OPEN_PRICE > fundamental_anchor(15)
    strong = run_session("STRONG", 88, 4000, pd.Timestamp("2026-10-02"))
    weak = run_session("WEAK", 12, 4000, pd.Timestamp("2026-10-02"))
    assert strong["prices"].mid.iloc[-1] > OPEN_PRICE > weak["prices"].mid.iloc[-1]
    assert strong["portfolios"]["Fundamental bot"].position > 0
    assert weak["portfolios"]["Fundamental bot"].position < 0


def test_market_maker_earns_the_spread_from_uninformed_flow():
    result = run_session("TEST", 55, 4000, pd.Timestamp("2026-10-02"))
    table = performance_table(result).set_index("strategy")
    assert table.loc["Market maker", "pnl"] > table.loc["Noise flow", "pnl"]
    assert table.loc["Market maker", "fills"] > 100


def test_candles_and_microstructure_are_well_formed():
    result = run_session("TEST", 60, 2000, pd.Timestamp("2026-10-02"))
    bars = candles(result["prices"])
    assert (bars.high >= bars.low).all() and (bars.high >= bars.open).all() and (bars.high >= bars.close).all()
    stats = microstructure(result)
    assert stats["volume"] > 0 and 0 <= stats["buy_share"] <= 1
    assert np.isfinite(stats["vwap"])


def test_session_clock_stays_inside_trading_hours():
    for stamp, expected in [("2026-10-02 08:00", "before open"), ("2026-10-02 12:00", "mid-session"),
                            ("2026-10-02 18:00", "after close"), ("2026-10-04 12:00", "weekend")]:
        ticks, _, day = session_ticks(pd.Timestamp(stamp, tz="Asia/Kolkata"))
        assert 1 <= ticks <= 11250, expected
        assert day.weekday() < 5, expected


def test_portfolio_marks_to_market():
    portfolio = Portfolio("x")
    portfolio.fill("buy", 100, 10, fee_rate=0)
    assert portfolio.position == 10 and portfolio.cash == -1000
    assert portfolio.equity(110) == pytest.approx(100)


def test_trade_tape_renders_as_a_table():
    result = run_session("TEST", 60, 1200, pd.Timestamp("2026-10-02"))
    tape = result["book"].tape(20)
    assert list(tape.columns) == ["tick", "price", "quantity", "aggressor", "buyer", "seller"]
    assert len(tape) > 0 and tape.quantity.gt(0).all()
