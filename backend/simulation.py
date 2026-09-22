"""
BearBull - Simulation Orchestrator & Experiment Engine (PRD Sections 15, 19, 20 & 25)

Core features:
  - Discrete-Event Simulation with deterministic per-agent PRNG substreams
  - ExperimentGenome with SHA256 cryptographic lineage & reproducibility
  - 8 Market Regimes (Calm, Bull, Bear, High Volatility, Liquidity Crisis, Flash Crash, Recovery)
  - Dynamic Market Shock Engine (News, Volatility spike, Liquidity withdrawal)
  - Causal Event Graph Logging (click any trade to trace exact parent origin)
  - Monte Carlo multi-seed execution & Counterfactual branching
"""

from __future__ import annotations
import json
import hashlib
import random
import time
import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

from matching_engine import MatchingEngine, Side, OrderType, Order, Trade
from agents import ARCHETYPE_REGISTRY, Agent
from risk_engine import RiskEngine
from analytics import MicrostructureAnalytics, ExecutionAnalytics


@dataclass
class ExperimentGenome:
    """A fully-specified, reproducible simulation configuration per PRD Section 25.3."""
    name: str = "default_experiment"
    seed: int = 42
    symbol: str = "BBX"
    ticks: int = 500
    initial_price: float = 100.0
    matching_policy: str = "price_time"
    agent_counts: Dict[str, int] = field(default_factory=lambda: {
        "noise": 40,
        "market_maker": 4,
        "momentum": 8,
        "mean_reversion": 8,
        "trend": 4,
        "fundamental": 4,
        "latency_sensitive": 2,
        "institutional": 1,
        "arbitrageur": 2,
        "adversarial": 1
    })
    agent_params: Dict[str, dict] = field(default_factory=dict)
    latency_config: Dict[str, dict] = field(default_factory=dict)
    parent_genome_hash: Optional[str] = None
    changed_field: Optional[str] = None

    def genome_hash(self) -> str:
        s = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

    def to_json(self) -> str:
        return json.dumps(asdict(self) | {"genome_hash": self.genome_hash()}, indent=2)

    @staticmethod
    def from_dict(d: dict) -> "ExperimentGenome":
        valid_keys = {
            "name", "seed", "symbol", "ticks", "initial_price",
            "matching_policy", "agent_counts", "agent_params",
            "latency_config", "parent_genome_hash", "changed_field"
        }
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return ExperimentGenome(**filtered)


class Simulation:
    """Deterministic, discrete-tick market simulation laboratory."""

    def __init__(self, genome: ExperimentGenome):
        self.genome = genome
        self.master_rng = random.Random(genome.seed)
        self.engine = MatchingEngine(symbols=[genome.symbol])
        self.risk_engine = RiskEngine()
        self.agents: List[Agent] = []
        self.agent_map: Dict[str, Agent] = {}
        self.price_history: List[float] = [genome.initial_price]
        self.fundamental_value: float = genome.initial_price
        self.regime: str = "Calm"
        self.tick: int = 0
        self.event_log: List[dict] = []
        self.causal_dag: List[dict] = []
        self.active_shocks: List[dict] = []

        self._build_agents()
        self._seed_book()

    def _build_agents(self):
        """Builds agents with isolated PRNG substreams to prevent cross-agent confounding."""
        for archetype, count in self.genome.agent_counts.items():
            if archetype not in ARCHETYPE_REGISTRY:
                continue
            cls = ARCHETYPE_REGISTRY[archetype]
            params = self.genome.agent_params.get(archetype, {})

            for i in range(count):
                agent_id = f"{archetype}_{i+1}"
                # Pinned substream PRNG derived from master seed + agent identity string
                sub_seed = int(hashlib.md5(f"{self.genome.seed}:{agent_id}".encode()).hexdigest(), 16) % (2**31)
                agent_rng = random.Random(sub_seed)

                agent = cls(agent_id=agent_id, rng=agent_rng, **params)
                if agent_id in self.genome.latency_config:
                    agent.latency_profile.update(self.genome.latency_config[agent_id])

                self.agents.append(agent)
                self.agent_map[agent_id] = agent

    def _seed_book(self):
        """Initial resting liquidity to seed order book."""
        p = self.genome.initial_price
        for i in range(6):
            self.engine.submit_order(self.genome.symbol, "seed_sys", Side.BUY, OrderType.LIMIT,
                                      3.0, round(p - 0.04 * (i + 1), 2))
            self.engine.submit_order(self.genome.symbol, "seed_sys", Side.SELL, OrderType.LIMIT,
                                      3.0, round(p + 0.04 * (i + 1), 2))

    def inject_shock(self, shock_type: str, magnitude: float, duration_ticks: int = 40):
        """Injects a timestamped exogenous market shock."""
        self.active_shocks.append({
            "type": shock_type,
            "magnitude": magnitude,
            "remaining_ticks": duration_ticks,
            "start_tick": self.tick
        })
        if shock_type == "flash_crash":
            self.regime = "Flash Crash"
        elif shock_type == "liquidity_crisis":
            self.regime = "Liquidity Crisis"
        elif shock_type == "volatility_spike":
            self.regime = "High Volatility"

    def _update_regime_and_fundamental(self):
        """Evolves hidden fundamental process via Ornstein-Uhlenbeck drift + shocks."""
        dt = 0.05
        theta = 0.15  # mean reversion speed
        mu = self.genome.initial_price
        sigma = 0.08

        # Apply active shocks
        shock_drift = 0.0
        active = []
        for sh in self.active_shocks:
            sh["remaining_ticks"] -= 1
            if sh["type"] == "negative_news":
                shock_drift -= sh["magnitude"] * 0.1
            elif sh["type"] == "positive_news":
                shock_drift += sh["magnitude"] * 0.1
            elif sh["type"] == "flash_crash":
                shock_drift -= 0.8
                sigma = 0.45
            elif sh["type"] == "volatility_spike":
                sigma = 0.35

            if sh["remaining_ticks"] > 0:
                active.append(sh)
            else:
                self.regime = "Recovery"
        self.active_shocks = active

        # OU increment
        dW = self.master_rng.gauss(0, math.sqrt(dt))
        self.fundamental_value += theta * (mu - self.fundamental_value) * dt + sigma * dW + shock_drift

    def step(self) -> dict:
        """Advances the discrete-event simulation by exactly one tick."""
        self._update_regime_and_fundamental()
        symbol = self.genome.symbol
        snapshot = self.engine.get_book_snapshot(symbol)
        tick_trades: List[Trade] = []
        rejected_orders = []

        # Shuffle agents to eliminate systematic first-mover bias
        order_agents = self.agents[:]
        self.master_rng.shuffle(order_agents)

        for agent in order_agents:
            intent = agent.decide(snapshot, self.price_history, fundamental=self.fundamental_value)
            if intent is None:
                continue

            # Pre-trade Risk Validation
            risk_res = self.risk_engine.validate_order(
                agent_id=agent.agent_id,
                side=intent.side,
                order_type=intent.order_type,
                qty=intent.quantity,
                price=intent.price,
                current_inventory=agent.inventory,
                current_cash=agent.cash
            )

            if not risk_res.passed:
                rejected_orders.append({
                    "agent_id": agent.agent_id,
                    "reason": risk_res.reason,
                    "code": risk_res.rejection_code,
                    "tick": self.tick
                })
                continue

            # Submit valid order to matching engine
            placed_order, trades = self.engine.submit_order(
                symbol=symbol,
                agent_id=agent.agent_id,
                side=intent.side,
                order_type=intent.order_type,
                quantity=intent.quantity,
                price=intent.price
            )

            # Record fill execution and causal link
            for t in trades:
                tick_trades.append(t)
                # Attrib fills
                if intent.side == Side.BUY:
                    agent.on_fill(Side.BUY, t.price, t.quantity, t.trade_id)
                else:
                    agent.on_fill(Side.SELL, t.price, t.quantity, t.trade_id)

                # Find resting counterpart
                counter_agent_id = "seed_sys"
                resting_order = self.engine.books[symbol].order_index.get(t.sell_order_id if intent.side == Side.BUY else t.buy_order_id)
                if resting_order and resting_order.agent_id in self.agent_map:
                    counter_agent = self.agent_map[resting_order.agent_id]
                    counter_agent_id = counter_agent.agent_id
                    c_side = Side.SELL if intent.side == Side.BUY else Side.BUY
                    counter_agent.on_fill(c_side, t.price, t.quantity, t.trade_id)

                # Latency waterfall calculation
                tot_latency = (
                    agent.latency_profile.get("ingress_us", 15) +
                    agent.latency_profile.get("decision_us", 10) +
                    agent.latency_profile.get("egress_us", 15)
                )

                # Log to Causal Event DAG
                self.causal_dag.append({
                    "trade_id": t.trade_id,
                    "tick": self.tick,
                    "aggressor_id": agent.agent_id,
                    "maker_id": counter_agent_id,
                    "price": t.price,
                    "quantity": t.quantity,
                    "side": t.aggressor_side.value,
                    "latency_waterfall": {
                        "network_ingress_us": agent.latency_profile.get("ingress_us", 15),
                        "validation_us": 2,
                        "matching_us": 3,
                        "queue_wait_us": max(1, self.master_rng.randint(2, 12)),
                        "network_egress_us": agent.latency_profile.get("egress_us", 15),
                        "total_us": tot_latency + 10
                    }
                })

            snapshot = self.engine.get_book_snapshot(symbol)

        mid = snapshot.get("mid")
        if mid is not None:
            self.price_history.append(mid)
            for ag in self.agents:
                ag.update_pnl(mid)

        # Microstructure metrics
        ofi = MicrostructureAnalytics.compute_ofi(
            self.event_log[-1]["snapshot"] if self.event_log else None,
            {"best_bid": snapshot.get("best_bid"), "best_ask": snapshot.get("best_ask"),
             "bid_qty": snapshot["bids"][0]["quantity"] if snapshot.get("bids") else 0.0,
             "ask_qty": snapshot["asks"][0]["quantity"] if snapshot.get("asks") else 0.0}
        )
        microprice = MicrostructureAnalytics.compute_stoikov_microprice(snapshot)
        health = ExecutionAnalytics.market_health_diagnosis(snapshot, [])

        record = {
            "tick": self.tick,
            "timestamp": time.time(),
            "mid": mid,
            "microprice": microprice,
            "spread": snapshot.get("spread"),
            "best_bid": snapshot.get("best_bid"),
            "best_ask": snapshot.get("best_ask"),
            "ofi": ofi,
            "regime": self.regime,
            "fundamental": round(self.fundamental_value, 2),
            "trades": [{
                "trade_id": t.trade_id,
                "price": t.price,
                "quantity": t.quantity,
                "side": t.aggressor_side.value if hasattr(t.aggressor_side, "value") else str(t.aggressor_side)
            } for t in tick_trades],
            "rejected_count": len(rejected_orders),
            "market_health": health,
            "snapshot": snapshot
        }

        self.event_log.append(record)
        self.tick += 1
        return record

    def run(self, ticks: Optional[int] = None) -> List[dict]:
        n = ticks or self.genome.ticks
        for _ in range(n):
            self.step()
        return self.event_log

    def snapshot(self) -> dict:
        return self.engine.get_book_snapshot(self.genome.symbol)

    def get_agent_leaderboard(self) -> List[dict]:
        return sorted([a.to_dict() for a in self.agents], key=lambda x: x["unrealized_pnl"], reverse=True)


class MonteCarloRunner:
    """Orchestrates repeated trials across seeds for statistical claims (PRD Section 26)."""

    @staticmethod
    def run_suite(base_genome: ExperimentGenome, n_trials: int = 30) -> Dict[str, Any]:
        spreads = []
        volatilities = []
        trade_counts = []
        mm_pnls = []

        for trial in range(n_trials):
            g = ExperimentGenome.from_dict(asdict(base_genome))
            g.seed = base_genome.seed + trial * 101
            sim = Simulation(g)
            sim.run()

            mids = [r["mid"] for r in sim.event_log if r.get("mid") is not None]
            sp = [r["spread"] for r in sim.event_log if r.get("spread") is not None]
            spreads.append(float(np.mean(sp)) if sp else 0.05)
            volatilities.append(MicrostructureAnalytics.calculate_realized_volatility(mids))
            trade_counts.append(len(sim.engine.trade_log))

            mms = [a.unrealized_pnl for a in sim.agents if a.archetype == "market_maker"]
            mm_pnls.append(float(np.mean(mms)) if mms else 0.0)

        def stat_pack(arr: List[float]) -> dict:
            a = np.array(arr)
            return {
                "mean": round(float(np.mean(a)), 4),
                "median": round(float(np.median(a)), 4),
                "std": round(float(np.std(a)), 4),
                "ci_95": [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)],
                "samples": [round(x, 3) for x in arr[:10]]
            }

        return {
            "n_trials": n_trials,
            "genome_hash": base_genome.genome_hash(),
            "spread_stats": stat_pack(spreads),
            "volatility_stats": stat_pack(volatilities),
            "trades_stats": stat_pack(trade_counts),
            "market_maker_pnl_stats": stat_pack(mm_pnls)
        }
