"""
BearBull - Risk Engine (PRD Section 21)

Pre-trade risk verification running before matching execution:
  - Max Position Limit check
  - Max Order Quantity Limit check
  - Max Notional Value Limit check
  - Cash / Collateral Constraint check
  - Order Rate Throttling / Flooding check
  - Emergency Agent Kill Switch
  - Structured rejection reasons with limit telemetry
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import time

from matching_engine import Side, OrderType


@dataclass
class RiskCheckResult:
    passed: bool
    rejection_code: Optional[str] = None
    reason: Optional[str] = None
    limit_val: Optional[float] = None
    current_val: Optional[float] = None
    requested_val: Optional[float] = None


class RiskEngine:
    """High-speed pre-trade risk filter."""

    def __init__(self, max_position: float = 1000.0, max_order_qty: float = 100.0,
                 max_notional: float = 25000.0, max_order_rate_per_sec: int = 50):
        self.max_position = max_position
        self.max_order_qty = max_order_qty
        self.max_notional = max_notional
        self.max_order_rate_per_sec = max_order_rate_per_sec
        self.agent_order_timestamps: Dict[str, list] = {}
        self.killed_agents: set = set()

    def kill_agent(self, agent_id: str):
        self.killed_agents.add(agent_id)

    def revive_agent(self, agent_id: str):
        self.killed_agents.discard(agent_id)

    def validate_order(self, agent_id: str, side: Side, order_type: OrderType,
                       qty: float, price: Optional[float], current_inventory: float,
                       current_cash: float) -> RiskCheckResult:
        # 1. Kill Switch Check
        if agent_id in self.killed_agents:
            return RiskCheckResult(
                passed=False,
                rejection_code="AGENT_SUSPENDED",
                reason=f"Agent {agent_id} has been suspended via risk kill switch.",
                limit_val=0.0,
                current_val=0.0,
                requested_val=qty
            )

        # 2. Max Order Size Check
        if qty > self.max_order_qty:
            return RiskCheckResult(
                passed=False,
                rejection_code="ORDER_SIZE_EXCEEDED",
                reason=f"Order quantity ({qty:.2f}) exceeds maximum allowed single order size ({self.max_order_qty:.2f}).",
                limit_val=self.max_order_qty,
                current_val=0.0,
                requested_val=qty
            )

        # 3. Max Notional Value Check
        effective_price = price or 100.0
        notional = qty * effective_price
        if notional > self.max_notional:
            return RiskCheckResult(
                passed=False,
                rejection_code="MAX_NOTIONAL_EXCEEDED",
                reason=f"Order notional ₹{notional:.2f} exceeds threshold of ₹{self.max_notional:.2f}.",
                limit_val=self.max_notional,
                current_val=0.0,
                requested_val=notional
            )

        # 4. Position Limit Check
        potential_inventory = current_inventory + (qty if side == Side.BUY else -qty)
        if abs(potential_inventory) > self.max_position:
            return RiskCheckResult(
                passed=False,
                rejection_code="POSITION_LIMIT_EXCEEDED",
                reason=f"Projected position ({potential_inventory:.1f}) exceeds max position limit (±{self.max_position:.1f}).",
                limit_val=self.max_position,
                current_val=current_inventory,
                requested_val=qty
            )

        # 5. Cash / Capital Check (For Buyers)
        if side == Side.BUY and current_cash < notional:
            return RiskCheckResult(
                passed=False,
                rejection_code="INSUFFICIENT_CASH",
                reason=f"Available cash (₹{current_cash:.2f}) is insufficient for buy order (₹{notional:.2f}).",
                limit_val=current_cash,
                current_val=current_cash,
                requested_val=notional
            )

        # 6. Rate Limit / Flooding Check
        now = time.time()
        timestamps = self.agent_order_timestamps.setdefault(agent_id, [])
        # prune older than 1 sec
        self.agent_order_timestamps[agent_id] = [t for t in timestamps if now - t < 1.0]
        if len(self.agent_order_timestamps[agent_id]) >= self.max_order_rate_per_sec:
            return RiskCheckResult(
                passed=False,
                rejection_code="RATE_LIMIT_EXCEEDED",
                reason=f"Agent exceeded maximum allowed {self.max_order_rate_per_sec} orders/sec rate limit.",
                limit_val=float(self.max_order_rate_per_sec),
                current_val=float(len(self.agent_order_timestamps[agent_id])),
                requested_val=1.0
            )

        self.agent_order_timestamps[agent_id].append(now)
        return RiskCheckResult(passed=True)
