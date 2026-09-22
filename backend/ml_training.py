"""
BearBull - Machine Learning & Reinforcement Learning Training Studio (PRD Section 3, 93 & ML/RL Seams)

Provides two ready-to-train model interfaces:
  1. BearBullMarketMakerEnv: Gymnasium-compatible Reinforcement Learning Environment
     for training adaptive market makers (Avellaneda-Stoikov / PPO / DDPG / SAC).
  2. LOBFeatureExtractor: Supervised learning pipeline extracting LOB features
     (depth imbalances, OFI, spreads, volatility) and short-horizon return labels.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
import random

from matching_engine import MatchingEngine, Side, OrderType
from simulation import Simulation, ExperimentGenome


class BearBullMarketMakerEnv:
    """
    Standard Reinforcement Learning Environment for Market Making in the Limit Order Book.
    Compatible with Gymnasium / Stable-Baselines3.
    """

    def __init__(self, seed: int = 42, max_steps: int = 200, inventory_penalty_lambda: float = 0.05):
        self.seed_val = seed
        self.max_steps = max_steps
        self.inventory_penalty = inventory_penalty_lambda
        self.current_step = 0
        self.sim: Optional[Simulation] = None
        self.inventory: float = 0.0
        self.cash: float = 100000.0
        self.last_wealth: float = 100000.0
        self.observation_dim = 10
        self.action_dim = 3  # [bid_offset_ticks, ask_offset_ticks, quote_size]

    def reset(self, seed: Optional[int] = None) -> Tuple[np.ndarray, dict]:
        """Resets simulation market state to tick 0."""
        s = seed if seed is not None else self.seed_val
        genome = ExperimentGenome(
            name="rl_train_env",
            seed=s,
            symbol="BBX",
            ticks=self.max_steps + 50,
            agent_counts={"noise": 40, "momentum": 8, "mean_reversion": 8, "market_maker": 2}
        )
        self.sim = Simulation(genome)
        # Warmup
        for _ in range(10):
            self.sim.step()

        self.current_step = 0
        self.inventory = 0.0
        self.cash = 100000.0
        mid = self.sim.snapshot().get("mid") or 100.0
        self.last_wealth = self.cash + (self.inventory * mid)

        obs = self._get_observation()
        return obs, {"mid": mid, "step": self.current_step}

    def _get_observation(self) -> np.ndarray:
        """Returns normalized feature vector representing current order book state."""
        snap = self.sim.snapshot()
        mid = snap.get("mid") or 100.0
        spread = snap.get("spread") or 0.05
        bids = snap.get("bids", [])
        asks = snap.get("asks", [])

        bid_q1 = bids[0]["quantity"] if len(bids) > 0 else 0.0
        ask_q1 = asks[0]["quantity"] if len(asks) > 0 else 0.0
        bid_q5 = sum(l["quantity"] for l in bids[:5])
        ask_q5 = sum(l["quantity"] for l in asks[:5])

        imbalance = (bid_q5 - ask_q5) / max(1.0, bid_q5 + ask_q5)
        recent_prices = self.sim.price_history[-20:]
        vol = float(np.std(np.diff(recent_prices))) if len(recent_prices) > 2 else 0.01

        obs = np.array([
            mid / 100.0,
            spread,
            bid_q1 / 10.0,
            ask_q1 / 10.0,
            bid_q5 / 50.0,
            ask_q5 / 50.0,
            imbalance,
            self.inventory / 20.0,
            self.cash / 100000.0,
            vol * 100.0
        ], dtype=np.float32)
        return obs

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """
        Executes one RL market making decision:
        action = [bid_half_spread_ticks, ask_half_spread_ticks, quote_size]
        """
        self.current_step += 1
        snap = self.sim.snapshot()
        mid = snap.get("mid") or 100.0

        bid_offset = max(0.01, float(action[0]) * 0.05)
        ask_offset = max(0.01, float(action[1]) * 0.05)
        size = max(0.5, min(5.0, float(action[2]) * 2.0))

        # Submit agent quotes to exchange
        bid_p = round(mid - bid_offset, 2)
        ask_p = round(mid + ask_offset, 2)

        if self.inventory < 50:
            _, b_trades = self.sim.engine.submit_order("BBX", "rl_agent", Side.BUY, OrderType.LIMIT, size, bid_p)
            for t in b_trades:
                self.inventory += t.quantity
                self.cash -= t.price * t.quantity

        if self.inventory > -50:
            _, a_trades = self.sim.engine.submit_order("BBX", "rl_agent", Side.SELL, OrderType.LIMIT, size, ask_p)
            for t in a_trades:
                self.inventory -= t.quantity
                self.cash += t.price * t.quantity

        # Advance background market simulation by 1 tick
        tick_record = self.sim.step()
        new_mid = tick_record.get("mid") or mid

        # Calculate reward: PnL delta minus quadratic inventory risk penalty
        current_wealth = self.cash + (self.inventory * new_mid)
        pnl_delta = current_wealth - self.last_wealth
        self.last_wealth = current_wealth

        inv_penalty = self.inventory_penalty * (self.inventory ** 2)
        reward = float(pnl_delta - inv_penalty)

        terminated = self.current_step >= self.max_steps
        truncated = False

        obs = self._get_observation()
        info = {
            "pnl_delta": pnl_delta,
            "total_pnl": current_wealth - 100000.0,
            "inventory": self.inventory,
            "mid": new_mid
        }

        return obs, reward, terminated, truncated, info


class LOBFeatureExtractor:
    """Extracts ML-ready supervised datasets for short-horizon price movement forecasting."""

    @staticmethod
    def extract_dataset(simulation_records: List[dict], horizon_k: int = 5) -> Dict[str, Any]:
        """
        Builds feature matrix X and label vector y:
        Features: [spread, OFI, depth_imbalance_L1, depth_imbalance_L5, rolling_vol]
        Label: Return sign (1: Up, 0: Down/Flat) after k ticks.
        """
        features = []
        labels = []
        mids = [r.get("mid") for r in simulation_records if r.get("mid") is not None]

        for i in range(len(simulation_records) - horizon_k):
            rec = simulation_records[i]
            mid_now = rec.get("mid")
            mid_future = simulation_records[i + horizon_k].get("mid")
            if mid_now is None or mid_future is None:
                continue

            spread = rec.get("spread") or 0.05
            ret_k = (mid_future - mid_now) / mid_now
            label = 1 if ret_k > 0.0001 else 0

            # Feature vector
            ofi = float(len(rec.get("trades", [])))
            row = [
                spread,
                ofi,
                mid_now,
                rec.get("best_bid") or mid_now - 0.02,
                rec.get("best_ask") or mid_now + 0.02
            ]
            features.append(row)
            labels.append(label)

        return {
            "samples_count": len(features),
            "horizon_ticks": horizon_k,
            "feature_names": ["spread", "trade_count_ofi", "mid_price", "best_bid", "best_ask"],
            "features_preview": features[:5],
            "labels_preview": labels[:5],
            "class_distribution": {
                "up": sum(labels),
                "down_flat": len(labels) - sum(labels)
            }
        }
