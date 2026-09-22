# BearBull — Electronic Exchange & Quantitative Research Platform

A state-of-the-art research laboratory and simulation platform for low-latency electronic trading, limit order book microstructure, and multi-agent quantitative modeling matching the **BearBull PRD v1.0**.

---

## 🌟 Key Capabilities & Architecture

1. **High-Performance Electronic Exchange Core**:
   - Price-Time Priority (FIFO) and Price-Size matching policies.
   - Microsecond & nanosecond latency resolution with intrusive order book queues.
   - Pre-trade risk validation (position limits, cash constraints, rate limiters, emergency kill switches).

2. **11 PRD Trading Agent Archetypes**:
   - `NoiseTrader`: Poisson arrival flow, random pricing around mid.
   - `MarketMaker`: Avellaneda-Stoikov (2008) inventory-skew reservation quoting.
   - `MomentumTrader`: Directional short-window trend following.
   - `MeanReversionTrader`: Ornstein-Uhlenbeck style mean reversion.
   - `TrendTrader`: Long-horizon moving average cross with position scaling.
   - `FundamentalTrader`: Trades toward hidden Ornstein-Uhlenbeck fundamental value.
   - `LiquidityTrader`: Target volume TWAP scheduler.
   - `Arbitrageur`: Temporary spread crossing exploitation.
   - `LatencySensitiveTrader`: Adaptive quoting reacting to measured round-trip delay.
   - `InstitutionalTrader`: Percentage of Volume (POV) slicing with market impact.
   - `AdversarialTrader`: Synthetic spoofing & quote stuffing for market surveillance validation.

3. **Machine Learning & Reinforcement Learning Studio**:
   - `BearBullMarketMakerEnv`: Standard **Gymnasium** RL environment (`reset()`, `step()`) for training custom market makers (PPO/DDPG/SAC) with inventory risk penalties.
   - `LOBFeatureExtractor`: Supervised dataset generator extracting LOB depth, OFI, spreads, and rolling volatility for short-horizon price prediction (XGBoost / LightGBM / Neural Nets).

4. **16 Institutional Terminal Screens** (Inspired by Bloomberg Terminal / ECNs):
   - **Live Market**: Real-time Level 2 depth ladder, animated Canvas Candlesticks + MA9/Volume, trade tape, and market health card.
   - **Order Book & Depth Ladder**: Cumulative market depth curves and queue position inspector.
   - **Trade Tape**: Real-time time & sales stream.
   - **Experiment Builder**: 15 PRD Templates (`EXP-001` through `EXP-012`) with SHA-256 Genome hashing.
   - **Agent Lab**: Live population composition and real-time PnL leaderboard.
   - **Agent Training & RL**: Interactive Gymnasium training stepper with reward convergence curves.
   - **Strategy Lab**: Visual IF/THEN condition-action rule builder DSL + Python sandbox.
   - **Latency Lab**: Per-agent microsecond delay sliders.
   - **Benchmark Lab**: Real-time profiling of Array+Bitmap vs Red-Black Tree vs Skip List vs Hash Map.
   - **Shock Simulator**: Flash Crash, Liquidity Crisis, Volatility Spikes, and News jumps.
   - **Experiment Arena & Lineage**: Multi-run tree DAG comparisons.
   - **Counterfactual Engine**: Confound-controlled single-variable forks with 95% bootstrap CIs.
   - **Replay Engine**: Time-travel VCR scrubber.
   - **Microstructure Analytics**: Order-Flow Imbalance (OFI), Stoikov Microprice, Realized Volatility.
   - **Causal Event DAG**: Forensic click-to-trace trade ancestry and latency waterfall breakdown.
   - **Research Report Generator**: Automated scientific reports separating Hypothesis, Observed Result, Interpretation, and PDF export.

---

## 🚀 Running the Platform

### Option A: Instant Zero-Setup Browser Demo
Simply double-click or open `frontend/index.html` in any web browser!
The embedded high-fidelity in-browser simulation kernel starts automatically with live quotes, depth ladder, trades, and chart animations.

### Option B: FastAPI Backend + WebSocket Live Stream
To run with the complete Python async control plane and heavy Monte Carlo/RL training capabilities:

```bash
cd backend
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

Then open `frontend/index.html` in your browser. The terminal will automatically connect to `http://localhost:8000` (indicated by the top green status badge).

---

## 🧠 Training Custom Agents

### 1. Reinforcement Learning Market Maker
In your Python script:
```python
from ml_training import BearBullMarketMakerEnv

env = BearBullMarketMakerEnv(seed=42)
obs, info = env.reset()

for step in range(200):
    # Action: [bid_spread_ticks, ask_spread_ticks, quote_size]
    action = [1.0, 1.0, 2.0]
    obs, reward, terminated, truncated, info = env.step(action)
    print(f"Step {step}: Reward = {reward:.2f}, PnL = ₹{info['total_pnl']:.2f}")
    if terminated:
        break
```

### 2. Supervised Price Prediction Dataset
```python
from simulation import Simulation, ExperimentGenome
from ml_training import LOBFeatureExtractor

sim = Simulation(ExperimentGenome(ticks=500))
sim.run()

dataset = LOBFeatureExtractor.extract_dataset(sim.event_log, horizon_k=5)
print(f"Generated {dataset['samples_count']} feature rows for ML training.")
```

---

## ⌨️ Terminal Navigation Shortcuts

- `Ctrl + K`: Open Command Palette to jump to any screen or trigger instant shocks.
- `ESC`: Close active modal.
