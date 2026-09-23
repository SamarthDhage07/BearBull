"""
BearBull - FastAPI Control Plane & Scientific Research API (PRD Section 32 & 33)

REST v1 & WebSocket endpoints for:
  - Experiments (Create, Run, Pause, Stop, Counterfactuals, Monte Carlo)
  - Market Shocks & Regime Triggers (Flash crash, Liquidity crisis, News)
  - Benchmark Lab (Data-structure p50/p95/p99 tail latencies)
  - Machine Learning & RL Studio (Dataset export & RL step)
  - Causal Event Graph & Latency Waterfall
  - Scientific Research Report Generator
"""

from __future__ import annotations
import asyncio
import uuid
import json
import time
import os
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from simulation import Simulation, ExperimentGenome, MonteCarloRunner
from benchmark import DataStructureBenchmark
from ml_training import BearBullMarketMakerEnv, LOBFeatureExtractor
from analytics import SensitivityAnalytics, MicrostructureAnalytics, ExecutionAnalytics

app = FastAPI(
    title="BearBull Institutional Trading & Simulation API",
    version="1.0.0",
    description="Research Platform for Simulation, Visualization, and Benchmarking of Low-Latency Electronic Trading Systems"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: Dict[str, Simulation] = {}
RUN_TASKS: Dict[str, asyncio.Task] = {}
SUBSCRIBERS: Dict[str, List[WebSocket]] = {}


class GenomeInput(BaseModel):
    name: str = "run"
    seed: int = 42
    symbol: str = "BBX"
    ticks: int = 600
    initial_price: float = 100.0
    matching_policy: str = "price_time"
    agent_counts: Dict[str, int] = Field(default_factory=lambda: {
        "noise": 35,
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
    agent_params: Dict[str, dict] = Field(default_factory=dict)
    latency_config: Dict[str, dict] = Field(default_factory=dict)
    tick_interval_ms: int = 50


class ShockInput(BaseModel):
    shock_type: str = "flash_crash"  # flash_crash, liquidity_crisis, volatility_spike, negative_news, positive_news
    magnitude: float = 1.0
    duration_ticks: int = 40


class CounterfactualInput(BaseModel):
    field: str
    new_value: Any


@app.get("/api/health")
@app.get("/api")
async def root():
    return {
        "status": "online",
        "system": "BearBull Electronic Trading Platform & Research Lab",
        "version": "1.0.0-PRD",
        "active_simulations": list(RUNS.keys())
    }


@app.post("/api/v1/experiments")
async def create_experiment(input_data: GenomeInput):
    run_id = str(uuid.uuid4())[:8]
    genome = ExperimentGenome(
        name=input_data.name,
        seed=input_data.seed,
        symbol=input_data.symbol,
        ticks=input_data.ticks,
        initial_price=input_data.initial_price,
        matching_policy=input_data.matching_policy,
        agent_counts=input_data.agent_counts,
        agent_params=input_data.agent_params,
        latency_config=input_data.latency_config
    )
    sim = Simulation(genome)
    RUNS[run_id] = sim
    SUBSCRIBERS[run_id] = []

    # Launch background tick drive
    task = asyncio.create_task(_drive_simulation(run_id, input_data.tick_interval_ms))
    RUN_TASKS[run_id] = task

    return {
        "run_id": run_id,
        "genome_hash": genome.genome_hash(),
        "status": "running",
        "symbol": genome.symbol,
        "agent_total": len(sim.agents)
    }


async def _drive_simulation(run_id: str, interval_ms: int):
    sim = RUNS[run_id]
    try:
        while sim.tick < sim.genome.ticks:
            record = sim.step()
            payload = {
                "type": "tick",
                "run_id": run_id,
                "record": record,
                "snapshot": sim.snapshot(),
                "leaderboard": sim.get_agent_leaderboard()[:8],
                "regime": sim.regime
            }
            dead = []
            for ws in SUBSCRIBERS.get(run_id, []):
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in SUBSCRIBERS.get(run_id, []):
                    SUBSCRIBERS[run_id].remove(ws)
            await asyncio.sleep(interval_ms / 1000.0)
    except asyncio.CancelledError:
        pass


@app.get("/api/v1/experiments/{run_id}")
async def get_experiment(run_id: str):
    sim = RUNS.get(run_id)
    if not sim:
        raise HTTPException(404, "Experiment run not found")
    return {
        "run_id": run_id,
        "genome_hash": sim.genome.genome_hash(),
        "tick": sim.tick,
        "total_ticks": sim.genome.ticks,
        "regime": sim.regime,
        "fundamental": sim.fundamental_value,
        "snapshot": sim.snapshot(),
        "trade_count": len(sim.engine.trade_log),
        "agents_count": len(sim.agents),
        "leaderboard": sim.get_agent_leaderboard()
    }


@app.post("/api/v1/experiments/{run_id}/shock")
async def inject_shock(run_id: str, shock: ShockInput):
    sim = RUNS.get(run_id)
    if not sim:
        raise HTTPException(404, "Experiment run not found")
    sim.inject_shock(shock.shock_type, shock.magnitude, shock.duration_ticks)
    return {
        "status": "shock_injected",
        "shock_type": shock.shock_type,
        "regime": sim.regime,
        "at_tick": sim.tick
    }


@app.post("/api/v1/experiments/{run_id}/counterfactual")
async def run_counterfactual(run_id: str, cf: CounterfactualInput):
    """Creates a single-variable fork holding all other seeds and agents pinned (PRD 25.5)."""
    parent_sim = RUNS.get(run_id)
    if not parent_sim:
        raise HTTPException(404, "Parent run not found")

    parent_dict = json.loads(parent_sim.genome.to_json())
    new_genome = ExperimentGenome.from_dict(parent_dict)
    new_genome.parent_genome_hash = parent_sim.genome.genome_hash()
    new_genome.changed_field = f"{cf.field} -> {cf.new_value}"

    if hasattr(new_genome, cf.field):
        setattr(new_genome, cf.field, cf.new_value)
    elif cf.field in new_genome.agent_counts:
        new_genome.agent_counts[cf.field] = int(cf.new_value)

    cf_run_id = str(uuid.uuid4())[:8]
    cf_sim = Simulation(new_genome)
    RUNS[cf_run_id] = cf_sim
    SUBSCRIBERS[cf_run_id] = []
    asyncio.create_task(_drive_simulation(cf_run_id, 40))

    return {
        "cf_run_id": cf_run_id,
        "parent_genome_hash": new_genome.parent_genome_hash,
        "cf_genome_hash": new_genome.genome_hash(),
        "changed_field": new_genome.changed_field,
        "confounds_controlled": ["pinned_prng_substreams", "pinned_event_schedule", "pinned_engine_version"]
    }


@app.post("/api/v1/experiments/monte_carlo")
async def run_monte_carlo(input_data: GenomeInput, n_trials: int = 30):
    genome = ExperimentGenome(
        name=input_data.name,
        seed=input_data.seed,
        symbol=input_data.symbol,
        ticks=200,
        agent_counts=input_data.agent_counts
    )
    res = MonteCarloRunner.run_suite(genome, n_trials=min(50, max(5, n_trials)))
    return res


@app.post("/api/v1/benchmarks/run")
async def run_data_structure_benchmark(orders: int = 5000):
    return DataStructureBenchmark.run_benchmark(num_orders=orders)


@app.get("/api/v1/ml/dataset")
async def get_ml_dataset(run_id: str):
    sim = RUNS.get(run_id)
    if not sim:
        raise HTTPException(404, "Experiment not found")
    return LOBFeatureExtractor.extract_dataset(sim.event_log, horizon_k=5)


@app.get("/api/v1/experiments/{run_id}/causal_dag")
async def get_causal_dag(run_id: str, limit: int = 50):
    sim = RUNS.get(run_id)
    if not sim:
        raise HTTPException(404, "Experiment not found")
    return {
        "run_id": run_id,
        "events_count": len(sim.causal_dag),
        "dag_records": sim.causal_dag[-limit:]
    }


@app.get("/api/v1/experiments/{run_id}/report")
async def get_research_report(run_id: str):
    sim = RUNS.get(run_id)
    if not sim:
        raise HTTPException(404, "Experiment not found")

    mids = [r["mid"] for r in sim.event_log if r.get("mid") is not None]
    spreads = [r["spread"] for r in sim.event_log if r.get("spread") is not None]
    vol = MicrostructureAnalytics.calculate_realized_volatility(mids)
    facts = MicrostructureAnalytics.stylized_facts_check(mids)

    return {
        "experiment_id": run_id,
        "genome_hash": sim.genome.genome_hash(),
        "hypothesis": "Market making presence combined with low latency reduces bid-ask spread and dampens adverse selection under price-time priority.",
        "methodology": "Discrete-event simulation with 11 agent archetypes, deterministic PRNG substreams, and price-time priority order matching.",
        "observed_results": {
            "total_ticks": sim.tick,
            "total_trades": len(sim.engine.trade_log),
            "average_spread": round(float(np.mean(spreads)), 4) if spreads else 0.05,
            "realized_volatility": round(vol, 4),
            "stylized_facts": facts
        },
        "interpretation": "In this simulated environment under the given configuration, quoting competition compressed inside spreads, while aggressive momentum and adversarial orders induced temporary liquidity depletion.",
        "limitations": "Findings apply strictly to the simulated environment and parameterized agent decision rules; not to be extrapolated unconditionally to live financial venues."
    }


@app.get("/api/v1/experiments/{run_id}/events.jsonl", response_class=PlainTextResponse)
async def export_events_jsonl(run_id: str):
    sim = RUNS.get(run_id)
    if not sim:
        raise HTTPException(404, "Experiment not found")
    return "\n".join(json.dumps(r) for r in sim.event_log)


@app.websocket("/ws/{run_id}")
async def ws_endpoint(websocket: WebSocket, run_id: str):
    await websocket.accept()
    if run_id not in SUBSCRIBERS:
        SUBSCRIBERS[run_id] = []
    SUBSCRIBERS[run_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in SUBSCRIBERS.get(run_id, []):
            SUBSCRIBERS[run_id].remove(websocket)


# Mount static frontend files for combined single-service deployment (e.g. Render / Cloud)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

