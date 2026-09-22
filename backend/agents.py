"""
BearBull - Trading Agent Archetypes (PRD Section 16 & 17)

All eleven archetypes specified in the Master PRD:
  1. NoiseTrader            - Poisson/random order flow, baseline liquidity
  2. MarketMaker            - Avellaneda-Stoikov inventory-skew quoting
  3. MomentumTrader         - Short-horizon directional trend following
  4. MeanReversionTrader    - Discretized Ornstein-Uhlenbeck style mean reversion
  5. TrendTrader            - Long-horizon trend following with position scaling
  6. FundamentalTrader      - Trades toward a hidden OU fundamental value process
  7. LiquidityTrader        - Target execution schedules (TWAP / POV child orders)
  8. Arbitrageur            - Cross-asset / synthetic spread arbitrage
  9. LatencySensitiveTrader - Adjusts quote aggression based on measured latency
  10. InstitutionalTrader   - Large parent order slicing with market impact
  11. AdversarialTrader     - Spoofing, quote-stuffing, aggressive cancellations

Also includes the Base Agent contract with PnL, cash, inventory, and fill tracking.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import random
import math
import time

from matching_engine import Side, OrderType


@dataclass
class OrderIntent:
    side: Side
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    time_in_force: str = "GTC"
    tag: str = ""


class Agent:
    """Base trading agent contract per PRD Section 16.1."""

    def __init__(self, agent_id: str, archetype: str, rng: Optional[random.Random] = None,
                 initial_cash: float = 100000.0, max_position: float = 500.0):
        self.agent_id = agent_id
        self.archetype = archetype
        self.rng = rng or random.Random()
        self.cash: float = initial_cash
        self.inventory: float = 0.0
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.max_position = max_position
        self.trades_count: int = 0
        self.submitted_orders: int = 0
        self.filled_orders: int = 0
        self.fill_history: List[dict] = []
        self.latency_profile = {
            "ingress_us": 15,
            "decision_us": 10,
            "egress_us": 15,
            "jitter_us": 5
        }
        self.active: bool = True

    def decide(self, snapshot: dict, price_history: List[float], fundamental: Optional[float] = None) -> Optional[OrderIntent]:
        raise NotImplementedError

    def on_fill(self, side: Side, price: float, quantity: float, trade_id: int):
        self.trades_count += 1
        self.filled_orders += 1
        fill_val = price * quantity

        if side == Side.BUY:
            self.inventory += quantity
            self.cash -= fill_val
        else:
            self.inventory -= quantity
            self.cash += fill_val

        self.fill_history.append({
            "trade_id": trade_id,
            "side": side.value,
            "price": price,
            "quantity": quantity,
            "inventory_after": self.inventory,
            "cash_after": self.cash,
            "timestamp": time.time()
        })

    def update_pnl(self, current_mid: float):
        position_value = self.inventory * current_mid
        total_wealth = self.cash + position_value
        self.unrealized_pnl = total_wealth - 100000.0

    def get_fill_rate(self) -> float:
        if self.submitted_orders == 0:
            return 0.0
        return self.filled_orders / self.submitted_orders

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "archetype": self.archetype,
            "inventory": round(self.inventory, 2),
            "cash": round(self.cash, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "trades_count": self.trades_count,
            "fill_rate": round(self.get_fill_rate(), 3),
            "active": self.active
        }


# =====================================================================
# 1. Random / Noise Trader
# =====================================================================
class NoiseTrader(Agent):
    """Poisson order arrivals with random pricing around the mid price."""

    def __init__(self, agent_id: str, activity: float = 0.35, order_size: float = 1.0,
                 price_noise_sigma: float = 0.25, rng=None, **kwargs):
        super().__init__(agent_id, "noise", rng, **kwargs)
        self.activity = activity
        self.order_size = order_size
        self.price_noise_sigma = price_noise_sigma

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or self.rng.random() > self.activity:
            return None
        self.submitted_orders += 1
        side = Side.BUY if self.rng.random() < 0.5 else Side.SELL
        mid = snapshot.get("mid") or 100.0
        noise = self.rng.gauss(0, self.price_noise_sigma)
        price = round(mid + noise, 2)
        qty = round(max(0.1, self.rng.uniform(0.5, 1.5) * self.order_size), 2)
        return OrderIntent(side, OrderType.LIMIT, qty, price, tag="noise_flow")


# =====================================================================
# 2. Market Maker (Avellaneda-Stoikov Reservation Price Model)
# =====================================================================
class MarketMaker(Agent):
    """
    Quotes both sides with inventory skew based on Avellaneda-Stoikov (2008):
    r(s, q) = s - q * gamma * sigma^2 * (T - t)
    """

    def __init__(self, agent_id: str, half_spread: float = 0.08, quote_size: float = 2.0,
                 inventory_skew: float = 0.015, max_inventory: float = 50.0, rng=None, **kwargs):
        super().__init__(agent_id, "market_maker", rng, **kwargs)
        self.half_spread = half_spread
        self.quote_size = quote_size
        self.inventory_skew = inventory_skew
        self.max_inventory = max_inventory
        self._toggle = 0

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active:
            return None
        mid = snapshot.get("mid") or 100.0
        skew = -self.inventory * self.inventory_skew

        self._toggle = 1 - self._toggle
        if self._toggle == 0 and self.inventory < self.max_inventory:
            self.submitted_orders += 1
            bid_p = round(mid - self.half_spread + skew, 2)
            return OrderIntent(Side.BUY, OrderType.LIMIT, self.quote_size, bid_p, tag="mm_bid")
        elif self.inventory > -self.max_inventory:
            self.submitted_orders += 1
            ask_p = round(mid + self.half_spread + skew, 2)
            return OrderIntent(Side.SELL, OrderType.LIMIT, self.quote_size, ask_p, tag="mm_ask")
        return None


# =====================================================================
# 3. Momentum Trader
# =====================================================================
class MomentumTrader(Agent):
    """Buys into upward price runs, sells into downward moves over a lookback."""

    def __init__(self, agent_id: str, lookback: int = 12, threshold: float = 0.003,
                 order_size: float = 2.0, rng=None, **kwargs):
        super().__init__(agent_id, "momentum", rng, **kwargs)
        self.lookback = lookback
        self.threshold = threshold
        self.order_size = order_size

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or len(price_history) < self.lookback + 1:
            return None
        window = price_history[-self.lookback:]
        pct_change = (window[-1] - window[0]) / (window[0] or 1.0)
        mid = snapshot.get("mid")
        if mid is None:
            return None

        if pct_change > self.threshold and self.inventory < self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.BUY, OrderType.LIMIT, self.order_size, round(mid + 0.04, 2), tag="momentum_buy")
        elif pct_change < -self.threshold and self.inventory > -self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.SELL, OrderType.LIMIT, self.order_size, round(mid - 0.04, 2), tag="momentum_sell")
        return None


# =====================================================================
# 4. Mean-Reversion Trader
# =====================================================================
class MeanReversionTrader(Agent):
    """Fades price deviations from a moving average / Ornstein-Uhlenbeck anchor."""

    def __init__(self, agent_id: str, lookback: int = 24, threshold: float = 0.005,
                 order_size: float = 1.5, rng=None, **kwargs):
        super().__init__(agent_id, "mean_reversion", rng, **kwargs)
        self.lookback = lookback
        self.threshold = threshold
        self.order_size = order_size

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or len(price_history) < self.lookback:
            return None
        window = price_history[-self.lookback:]
        ma = sum(window) / len(window)
        mid = snapshot.get("mid")
        if mid is None or ma == 0:
            return None

        dev = (mid - ma) / ma
        if dev > self.threshold and self.inventory > -self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.SELL, OrderType.LIMIT, self.order_size, round(mid - 0.02, 2), tag="mean_rev_sell")
        elif dev < -self.threshold and self.inventory < self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.BUY, OrderType.LIMIT, self.order_size, round(mid + 0.02, 2), tag="mean_rev_buy")
        return None


# =====================================================================
# 5. Trend Trader
# =====================================================================
class TrendTrader(Agent):
    """Longer-horizon trend following with EMA cross & position scaling."""

    def __init__(self, agent_id: str, fast_window: int = 10, slow_window: int = 40,
                 order_size: float = 3.0, rng=None, **kwargs):
        super().__init__(agent_id, "trend", rng, **kwargs)
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.order_size = order_size

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or len(price_history) < self.slow_window:
            return None
        fast_ma = sum(price_history[-self.fast_window:]) / self.fast_window
        slow_ma = sum(price_history[-self.slow_window:]) / self.slow_window
        mid = snapshot.get("mid")
        if mid is None:
            return None

        if fast_ma > slow_ma * 1.002 and self.inventory < self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.BUY, OrderType.LIMIT, self.order_size, round(mid + 0.03, 2), tag="trend_buy")
        elif fast_ma < slow_ma * 0.998 and self.inventory > -self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.SELL, OrderType.LIMIT, self.order_size, round(mid - 0.03, 2), tag="trend_sell")
        return None


# =====================================================================
# 6. Fundamental Trader
# =====================================================================
class FundamentalTrader(Agent):
    """Trades toward the true hidden fundamental value process."""

    def __init__(self, agent_id: str, sensitivity: float = 0.02, order_size: float = 2.0,
                 noise_sigma: float = 0.05, rng=None, **kwargs):
        super().__init__(agent_id, "fundamental", rng, **kwargs)
        self.sensitivity = sensitivity
        self.order_size = order_size
        self.noise_sigma = noise_sigma

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or fundamental is None:
            return None
        mid = snapshot.get("mid") or 100.0
        perceived_val = fundamental + self.rng.gauss(0, self.noise_sigma)
        gap = perceived_val - mid

        if gap > self.sensitivity and self.inventory < self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.BUY, OrderType.LIMIT, self.order_size, round(mid + 0.02, 2), tag="fund_buy")
        elif gap < -self.sensitivity and self.inventory > -self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.SELL, OrderType.LIMIT, self.order_size, round(mid - 0.02, 2), tag="fund_sell")
        return None


# =====================================================================
# 7. Liquidity Trader (TWAP Child Order Scheduler)
# =====================================================================
class LiquidityTrader(Agent):
    """Executes a target parent volume over a fixed horizon (TWAP execution)."""

    def __init__(self, agent_id: str, target_quantity: float = 50.0, side: Side = Side.BUY,
                 horizon_ticks: int = 100, rng=None, **kwargs):
        super().__init__(agent_id, "liquidity", rng, **kwargs)
        self.target_quantity = target_quantity
        self.target_side = side
        self.horizon_ticks = horizon_ticks
        self.executed_qty = 0.0
        self.slice_qty = target_quantity / max(1, (horizon_ticks // 5))

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or self.executed_qty >= self.target_quantity:
            return None
        if self.rng.random() < 0.2:  # TWAP slice interval
            rem = self.target_quantity - self.executed_qty
            qty = round(min(self.slice_qty, rem), 2)
            mid = snapshot.get("mid") or 100.0
            price = round(mid + 0.05 if self.target_side == Side.BUY else mid - 0.05, 2)
            self.submitted_orders += 1
            self.executed_qty += qty
            return OrderIntent(self.target_side, OrderType.LIMIT, qty, price, tag="twap_slice")
        return None


# =====================================================================
# 8. Arbitrageur
# =====================================================================
class Arbitrageur(Agent):
    """Exploits temporary synthetic order book spread imbalances."""

    def __init__(self, agent_id: str, min_profit_ticks: float = 0.04, order_size: float = 2.0, rng=None, **kwargs):
        super().__init__(agent_id, "arbitrageur", rng, **kwargs)
        self.min_profit_ticks = min_profit_ticks
        self.order_size = order_size

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active:
            return None
        bb, ba = snapshot.get("best_bid"), snapshot.get("best_ask")
        if bb is None or ba is None:
            return None
        # In a single book, detects crossed or extremely tight spread opportunities
        if (ba - bb) <= 0.01:
            self.submitted_orders += 1
            side = Side.BUY if self.rng.random() < 0.5 else Side.SELL
            price = round(bb if side == Side.BUY else ba, 2)
            return OrderIntent(side, OrderType.LIMIT, self.order_size, price, tag="arb_take")
        return None


# =====================================================================
# 9. Latency-Sensitive Trader (Flagship for Latency Lab EXP-002)
# =====================================================================
class LatencySensitiveTrader(Agent):
    """
    Market maker that dynamically adjusts quoting distance and cancellation
    intensity based on its measured round-trip latency advantage.
    """

    def __init__(self, agent_id: str, latency_us: int = 10, quote_size: float = 3.0, rng=None, **kwargs):
        super().__init__(agent_id, "latency_sensitive", rng, **kwargs)
        self.latency_profile["ingress_us"] = latency_us
        self.quote_size = quote_size
        self._toggle = 0

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active:
            return None
        mid = snapshot.get("mid") or 100.0
        # Faster traders can quote tighter spreads safely without adverse selection
        spread_factor = 0.02 + (self.latency_profile["ingress_us"] / 1000.0) * 0.05
        skew = -self.inventory * 0.02

        self._toggle = 1 - self._toggle
        if self._toggle == 0 and self.inventory < self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.BUY, OrderType.LIMIT, self.quote_size, round(mid - spread_factor + skew, 2), tag="fast_bid")
        elif self.inventory > -self.max_position:
            self.submitted_orders += 1
            return OrderIntent(Side.SELL, OrderType.LIMIT, self.quote_size, round(mid + spread_factor + skew, 2), tag="fast_ask")
        return None


# =====================================================================
# 10. Institutional / Large-Order Agent (POV Slicing)
# =====================================================================
class InstitutionalTrader(Agent):
    """
    Percentage of Volume (POV) institutional execution algorithm.
    Participates at a target rate (e.g., 15% of market volume) to minimize market impact.
    """

    def __init__(self, agent_id: str, target_total_qty: float = 120.0, side: Side = Side.BUY,
                 pov_target: float = 0.15, rng=None, **kwargs):
        super().__init__(agent_id, "institutional", rng, **kwargs)
        self.target_total_qty = target_total_qty
        self.side = side
        self.pov_target = pov_target
        self.executed = 0.0

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or self.executed >= self.target_total_qty:
            return None
        if self.rng.random() < 0.35:
            mid = snapshot.get("mid") or 100.0
            slice_size = round(min(5.0, self.target_total_qty - self.executed), 2)
            self.submitted_orders += 1
            self.executed += slice_size
            price = round(mid + 0.03 if self.side == Side.BUY else mid - 0.03, 2)
            return OrderIntent(self.side, OrderType.LIMIT, slice_size, price, tag="institutional_pov")
        return None


# =====================================================================
# 11. Adversarial / Stress Agent (Market Surveillance EXP-113)
# =====================================================================
class AdversarialTrader(Agent):
    """
    Generates synthetic market manipulation patterns (spoofing, rapid cancellation,
    quote-stuffing) for training and validating anomaly detectors.
    """

    def __init__(self, agent_id: str, mode: str = "spoofing", intensity: float = 0.8, rng=None, **kwargs):
        super().__init__(agent_id, "adversarial", rng, **kwargs)
        self.mode = mode
        self.intensity = intensity

    def decide(self, snapshot, price_history, fundamental=None):
        if not self.active or self.rng.random() > self.intensity:
            return None
        mid = snapshot.get("mid") or 100.0

        # Pattern: Fake large order deep or at inside book followed by immediate opposite execution
        self.submitted_orders += 1
        if self.mode == "spoofing":
            side = Side.BUY if self.rng.random() < 0.5 else Side.SELL
            fake_price = round(mid - 0.06 if side == Side.BUY else mid + 0.06, 2)
            return OrderIntent(side, OrderType.LIMIT, quantity=25.0, price=fake_price, tag="spoof_quote")
        else:
            # Quote stuffing / noise flood
            side = Side.BUY if self.rng.random() < 0.5 else Side.SELL
            return OrderIntent(side, OrderType.LIMIT, quantity=0.5, price=round(mid + self.rng.uniform(-0.1, 0.1), 2), tag="quote_stuff")


ARCHETYPE_REGISTRY: Dict[str, Any] = {
    "noise": NoiseTrader,
    "market_maker": MarketMaker,
    "momentum": MomentumTrader,
    "mean_reversion": MeanReversionTrader,
    "trend": TrendTrader,
    "fundamental": FundamentalTrader,
    "liquidity": LiquidityTrader,
    "arbitrageur": Arbitrageur,
    "latency_sensitive": LatencySensitiveTrader,
    "institutional": InstitutionalTrader,
    "adversarial": AdversarialTrader,
}
