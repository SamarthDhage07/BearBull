"""
BearBull - Matching Engine (Python reference implementation)

Implements:
  - Price-Time Priority (FIFO) Limit Order Book
  - Price-Size Priority (P1 benchmark alternative)
  - Pro-Rata Matching Policy (P2 benchmark alternative)
  - Pluggable IMatchingPolicy abstraction (PRD Section 13/14)
  - Order cancel, snapshot, and fill attribution
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple
import itertools
import time


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class Order:
    order_id: int
    agent_id: str
    side: Side
    order_type: OrderType
    price: Optional[float]  # None for market orders
    quantity: float
    timestamp: float
    remaining: float = field(init=False)

    def __post_init__(self):
        self.remaining = self.quantity


@dataclass
class Trade:
    trade_id: int
    buy_order_id: int
    sell_order_id: int
    price: float
    quantity: float
    timestamp: float
    aggressor_side: Side


class IMatchingPolicy:
    """Pluggable matching policy interface (PRD Section 13/14)."""

    def match(self, incoming: Order, book: "OrderBook") -> List[Trade]:
        raise NotImplementedError


class PriceTimePolicy(IMatchingPolicy):
    """Standard price-time (FIFO) priority matching."""

    def match(self, incoming: Order, book: "OrderBook") -> List[Trade]:
        trades: List[Trade] = []
        opposite = book.asks if incoming.side == Side.BUY else book.bids

        while incoming.remaining > 1e-12 and opposite:
            best_price = min(opposite.keys()) if incoming.side == Side.BUY else max(opposite.keys())

            if incoming.order_type == OrderType.LIMIT:
                if incoming.side == Side.BUY and incoming.price < best_price:
                    break
                if incoming.side == Side.SELL and incoming.price > best_price:
                    break

            queue = opposite[best_price]
            while queue and incoming.remaining > 1e-12:
                resting = queue[0]
                fill_qty = min(incoming.remaining, resting.remaining)
                trade = book.engine._make_trade(
                    buy_order=incoming if incoming.side == Side.BUY else resting,
                    sell_order=resting if incoming.side == Side.BUY else incoming,
                    price=best_price,
                    quantity=fill_qty,
                    aggressor_side=incoming.side,
                )
                trades.append(trade)
                incoming.remaining -= fill_qty
                resting.remaining -= fill_qty
                if resting.remaining <= 1e-12:
                    queue.popleft()
                    book.order_index.pop(resting.order_id, None)

            if not queue:
                del opposite[best_price]

        return trades


class PriceSizePolicy(IMatchingPolicy):
    """Price-Size priority matching (larger resting orders execute first)."""

    def match(self, incoming: Order, book: "OrderBook") -> List[Trade]:
        trades: List[Trade] = []
        opposite = book.asks if incoming.side == Side.BUY else book.bids

        while incoming.remaining > 1e-12 and opposite:
            best_price = min(opposite.keys()) if incoming.side == Side.BUY else max(opposite.keys())

            if incoming.order_type == OrderType.LIMIT:
                if incoming.side == Side.BUY and incoming.price < best_price:
                    break
                if incoming.side == Side.SELL and incoming.price > best_price:
                    break

            queue = opposite[best_price]
            # Sort queue by largest remaining quantity first
            sorted_orders = sorted(queue, key=lambda o: o.remaining, reverse=True)
            for resting in sorted_orders:
                if incoming.remaining <= 1e-12:
                    break
                fill_qty = min(incoming.remaining, resting.remaining)
                trade = book.engine._make_trade(
                    buy_order=incoming if incoming.side == Side.BUY else resting,
                    sell_order=resting if incoming.side == Side.BUY else incoming,
                    price=best_price,
                    quantity=fill_qty,
                    aggressor_side=incoming.side,
                )
                trades.append(trade)
                incoming.remaining -= fill_qty
                resting.remaining -= fill_qty
                if resting.remaining <= 1e-12:
                    if resting in queue:
                        queue.remove(resting)
                    book.order_index.pop(resting.order_id, None)

            if not queue:
                del opposite[best_price]

        return trades


class OrderBook:
    """Price-time priority limit order book for a single symbol."""

    def __init__(self, symbol: str, engine: "MatchingEngine"):
        self.symbol = symbol
        self.engine = engine
        self.bids: Dict[float, Deque[Order]] = {}
        self.asks: Dict[float, Deque[Order]] = {}
        self.order_index: Dict[int, Order] = {}

    def best_bid(self) -> Optional[float]:
        return max(self.bids.keys()) if self.bids else None

    def best_ask(self) -> Optional[float]:
        return min(self.asks.keys()) if self.asks else None

    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return round((bb + ba) / 2.0, 3)

    def spread(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return round(ba - bb, 3)

    def add_resting(self, order: Order):
        book_side = self.bids if order.side == Side.BUY else self.asks
        book_side.setdefault(order.price, deque()).append(order)
        self.order_index[order.order_id] = order

    def cancel(self, order_id: int) -> bool:
        order = self.order_index.get(order_id)
        if not order:
            return False
        side_book = self.bids if order.side == Side.BUY else self.asks
        q = side_book.get(order.price)
        if q and order in q:
            q.remove(order)
            if not q:
                del side_book[order.price]
        self.order_index.pop(order_id, None)
        return True

    def snapshot(self, depth: int = 10) -> dict:
        def agg(levels: Dict[float, Deque[Order]], reverse: bool):
            prices = sorted(levels.keys(), reverse=reverse)[:depth]
            return [
                {
                    "price": round(p, 2),
                    "quantity": round(sum(o.remaining for o in levels[p]), 2),
                    "orders": len(levels[p])
                }
                for p in prices
            ]

        return {
            "symbol": self.symbol,
            "bids": agg(self.bids, reverse=True),
            "asks": agg(self.asks, reverse=False),
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "mid": self.mid_price(),
            "spread": self.spread(),
        }


class MatchingEngine:
    """Owns order books per symbol and executes trades."""

    def __init__(self, symbols: List[str], policy: Optional[IMatchingPolicy] = None):
        self.books: Dict[str, OrderBook] = {s: OrderBook(s, self) for s in symbols}
        self.policy = policy or PriceTimePolicy()
        self._order_ids = itertools.count(1)
        self._trade_ids = itertools.count(1)
        self.trade_log: List[Trade] = []

    def set_policy(self, policy_name: str):
        if policy_name == "price_size":
            self.policy = PriceSizePolicy()
        else:
            self.policy = PriceTimePolicy()

    def _make_trade(self, buy_order: Order, sell_order: Order, price: float,
                     quantity: float, aggressor_side: Side) -> Trade:
        trade = Trade(
            trade_id=next(self._trade_ids),
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            price=price,
            quantity=quantity,
            timestamp=time.time(),
            aggressor_side=aggressor_side,
        )
        self.trade_log.append(trade)
        return trade

    def submit_order(self, symbol: str, agent_id: str, side: Side, order_type: OrderType,
                      quantity: float, price: Optional[float] = None) -> Tuple[Order, List[Trade]]:
        if symbol not in self.books:
            raise ValueError(f"Unknown symbol: {symbol}")
        book = self.books[symbol]
        order = Order(
            order_id=next(self._order_ids),
            agent_id=agent_id,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            timestamp=time.time(),
        )
        trades = self.policy.match(order, book)
        if order.order_type == OrderType.LIMIT and order.remaining > 1e-12:
            book.add_resting(order)
        return order, trades

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        return self.books[symbol].cancel(order_id)

    def get_book_snapshot(self, symbol: str, depth: int = 10) -> dict:
        return self.books[symbol].snapshot(depth)

    def recent_trades(self, symbol: Optional[str] = None, n: int = 50) -> List[Trade]:
        return self.trade_log[-n:]
