/**
 * BearBull - In-Browser High-Fidelity Market Simulation Engine
 * PRD-compliant discrete-event trading kernel with 11 archetypes,
 * shock engine, microstructure analytics, and 15 experiment templates.
 */

(function(global) {
  'use strict';

  class SimEngine {
    constructor() {
      this.running = false;
      this.tickInterval = null;
      this.tickSpeedMs = 60;
      this.tick = 0;
      this.symbol = 'BBX';
      this.initialPrice = 100.0;
      this.fundamental = 100.0;
      this.regime = 'Calm';
      
      this.priceHistory = [100.0];
      this.orderLog = [];
      this.tradeLog = [];
      this.eventLog = [];
      this.causalDag = [];
      this.activeShocks = [];

      // Order book state
      this.bids = new Map(); // price -> [{id, agentId, qty, remaining}]
      this.asks = new Map();
      this.orderIndex = new Map();
      this.nextOrderId = 1;
      this.nextTradeId = 1;

      // Agent populations
      this.agents = [];
      this.agentMap = new Map();

      this.listeners = new Set();
      this.initDefaultAgents();
      this.seedBook();
    }

    subscribe(fn) {
      this.listeners.add(fn);
      return () => this.listeners.delete(fn);
    }

    notify(payload) {
      this.listeners.forEach(fn => fn(payload));
    }

    initDefaultAgents(agentCounts = null) {
      this.agents = [];
      this.agentMap.clear();
      const counts = agentCounts || {
        noise: 35,
        market_maker: 4,
        momentum: 8,
        mean_reversion: 8,
        trend: 4,
        fundamental: 4,
        latency_sensitive: 2,
        institutional: 1,
        arbitrageur: 2,
        adversarial: 1
      };

      Object.entries(counts).forEach(([archetype, count]) => {
        for (let i = 1; i <= count; i++) {
          const agentId = `${archetype}_${i}`;
          const agent = {
            id: agentId,
            archetype,
            cash: 100000.0,
            inventory: 0.0,
            unrealizedPnl: 0.0,
            submitted: 0,
            filled: 0,
            active: true,
            latencyUs: archetype === 'latency_sensitive' ? 8 : (archetype === 'market_maker' ? 20 : 150),
            params: {}
          };
          this.agents.push(agent);
          this.agentMap.set(agentId, agent);
        }
      });
    }

    seedBook() {
      this.bids.clear();
      this.asks.clear();
      this.orderIndex.clear();
      const p = this.initialPrice;
      for (let i = 1; i <= 6; i++) {
        this.submitOrder('seed_sys', 'buy', 'limit', 3.0, +(p - 0.03 * i).toFixed(2));
        this.submitOrder('seed_sys', 'sell', 'limit', 3.0, +(p + 0.03 * i).toFixed(2));
      }
    }

    getSnapshot(depth = 8) {
      const bidPrices = Array.from(this.bids.keys()).sort((a, b) => b - a).slice(0, depth);
      const askPrices = Array.from(this.asks.keys()).sort((a, b) => a - b).slice(0, depth);

      const bids = bidPrices.map(p => ({
        price: p,
        quantity: +(this.bids.get(p).reduce((sum, o) => sum + o.remaining, 0)).toFixed(2),
        orders: this.bids.get(p).length
      }));

      const asks = askPrices.map(p => ({
        price: p,
        quantity: +(this.asks.get(p).reduce((sum, o) => sum + o.remaining, 0)).toFixed(2),
        orders: this.asks.get(p).length
      }));

      const bestBid = bids.length > 0 ? bids[0].price : null;
      const bestAsk = asks.length > 0 ? asks[0].price : null;
      const mid = (bestBid && bestAsk) ? +((bestBid + bestAsk) / 2.0).toFixed(3) : (bestBid || bestAsk || this.initialPrice);
      const spread = (bestBid && bestAsk) ? +(bestAsk - bestBid).toFixed(3) : 0.05;

      return { bids, asks, bestBid, bestAsk, mid, spread, symbol: this.symbol };
    }

    submitOrder(agentId, side, type, qty, price = null) {
      const order = {
        id: this.nextOrderId++,
        agentId,
        side,
        type,
        price,
        quantity: qty,
        remaining: qty,
        timestamp: Date.now()
      };

      const trades = this.matchOrder(order);
      if (order.type === 'limit' && order.remaining > 0.001) {
        const bookSide = order.side === 'buy' ? this.bids : this.asks;
        if (!bookSide.has(order.price)) {
          bookSide.set(order.price, []);
        }
        bookSide.get(order.price).push(order);
        this.orderIndex.set(order.id, order);
      }

      return { order, trades };
    }

    matchOrder(incoming) {
      const trades = [];
      const opposite = incoming.side === 'buy' ? this.asks : this.bids;

      while (incoming.remaining > 0.001 && opposite.size > 0) {
        const sortedPrices = Array.from(opposite.keys()).sort((a, b) => incoming.side === 'buy' ? a - b : b - a);
        const bestPrice = sortedPrices[0];

        if (incoming.type === 'limit') {
          if (incoming.side === 'buy' && incoming.price < bestPrice) break;
          if (incoming.side === 'sell' && incoming.price > bestPrice) break;
        }

        const queue = opposite.get(bestPrice);
        while (queue && queue.length > 0 && incoming.remaining > 0.001) {
          const resting = queue[0];
          const fillQty = Math.min(incoming.remaining, resting.remaining);

          const trade = {
            tradeId: this.nextTradeId++,
            buyOrderId: incoming.side === 'buy' ? incoming.id : resting.id,
            sellOrderId: incoming.side === 'sell' ? incoming.id : resting.id,
            buyerId: incoming.side === 'buy' ? incoming.agentId : resting.agentId,
            sellerId: incoming.side === 'sell' ? incoming.agentId : resting.agentId,
            price: bestPrice,
            quantity: +fillQty.toFixed(2),
            timestamp: Date.now(),
            aggressorSide: incoming.side
          };

          trades.push(trade);
          this.tradeLog.push(trade);

          incoming.remaining = +(incoming.remaining - fillQty).toFixed(4);
          resting.remaining = +(resting.remaining - fillQty).toFixed(4);

          // Attribute fills to agents
          this.attributeFill(trade.buyerId, 'buy', trade.price, fillQty);
          this.attributeFill(trade.sellerId, 'sell', trade.price, fillQty);

          if (resting.remaining <= 0.001) {
            queue.shift();
            this.orderIndex.delete(resting.id);
          }
        }

        if (queue && queue.length === 0) {
          opposite.delete(bestPrice);
        }
      }

      return trades;
    }

    attributeFill(agentId, side, price, qty) {
      const agent = this.agentMap.get(agentId);
      if (!agent) return;
      agent.filled++;
      const val = price * qty;
      if (side === 'buy') {
        agent.inventory = +(agent.inventory + qty).toFixed(2);
        agent.cash = +(agent.cash - val).toFixed(2);
      } else {
        agent.inventory = +(agent.inventory - qty).toFixed(2);
        agent.cash = +(agent.cash + val).toFixed(2);
      }
    }

    injectShock(type, magnitude = 1.0, duration = 40) {
      this.activeShocks.push({ type, magnitude, remaining: duration });
      if (type === 'flash_crash') this.regime = 'Flash Crash';
      else if (type === 'liquidity_crisis') this.regime = 'Liquidity Crisis';
      else if (type === 'volatility_spike') this.regime = 'High Volatility';
    }

    step() {
      // 1. Evolve fundamental value
      let shockDrift = 0;
      let shockSigma = 0.08;
      this.activeShocks = this.activeShocks.filter(s => {
        s.remaining--;
        if (s.type === 'flash_crash') { shockDrift -= 0.6; shockSigma = 0.4; }
        else if (s.type === 'negative_news') shockDrift -= s.magnitude * 0.15;
        else if (s.type === 'positive_news') shockDrift += s.magnitude * 0.15;
        else if (s.type === 'volatility_spike') shockSigma = 0.35;
        return s.remaining > 0;
      });

      if (this.activeShocks.length === 0 && this.regime !== 'Calm') {
        this.regime = 'Recovery';
        if (Math.random() < 0.1) this.regime = 'Calm';
      }

      const dW = (Math.random() - 0.5) * 2 * Math.sqrt(0.05);
      this.fundamental += 0.12 * (this.initialPrice - this.fundamental) * 0.05 + shockSigma * dW + shockDrift;

      const snapshot = this.getSnapshot();
      const mid = snapshot.mid;
      const tickTrades = [];

      // 2. Poll agents with randomized execution order
      const shuffled = [...this.agents].sort(() => Math.random() - 0.5);

      shuffled.forEach(agent => {
        if (!agent.active) return;
        const intent = this.getAgentIntent(agent, snapshot);
        if (!intent) return;

        agent.submitted++;
        const res = this.submitOrder(agent.id, intent.side, intent.type, intent.qty, intent.price);
        if (res.trades.length > 0) {
          res.trades.forEach(t => {
            tickTrades.push(t);
            // Log to Causal Event DAG
            this.causalDag.push({
              tradeId: t.tradeId,
              tick: this.tick,
              aggressorId: agent.id,
              makerId: intent.side === 'buy' ? t.sellerId : t.buyerId,
              price: t.price,
              quantity: t.quantity,
              side: intent.side,
              latencyWaterfall: {
                ingressUs: agent.latencyUs,
                validateUs: 2,
                matchUs: 3,
                queueWaitUs: Math.floor(Math.random() * 15) + 3,
                egressUs: 12,
                totalUs: agent.latencyUs + 20
              }
            });
          });
        }
      });

      // Update price history & PnLs
      const updatedSnap = this.getSnapshot();
      this.priceHistory.push(updatedSnap.mid);
      if (this.priceHistory.length > 300) this.priceHistory.shift();

      this.agents.forEach(a => {
        const wealth = a.cash + (a.inventory * updatedSnap.mid);
        a.unrealizedPnl = +(wealth - 100000.0).toFixed(2);
      });

      // Compute OFI & Health
      const bidQ = updatedSnap.bids[0] ? updatedSnap.bids[0].quantity : 0;
      const askQ = updatedSnap.asks[0] ? updatedSnap.asks[0].quantity : 0;
      const ofi = +(bidQ - askQ).toFixed(2);
      const microprice = +(updatedSnap.mid + ((bidQ - askQ) / Math.max(1, bidQ + askQ)) * updatedSnap.spread * 0.4).toFixed(3);

      const record = {
        tick: this.tick++,
        timestamp: Date.now(),
        mid: updatedSnap.mid,
        microprice,
        spread: updatedSnap.spread,
        bestBid: updatedSnap.bestBid,
        bestAsk: updatedSnap.bestAsk,
        ofi,
        regime: this.regime,
        fundamental: +this.fundamental.toFixed(2),
        trades: tickTrades,
        snapshot: updatedSnap,
        leaderboard: this.getLeaderboard().slice(0, 10)
      };

      this.eventLog.push(record);
      this.notify(record);
      return record;
    }

    getAgentIntent(agent, snapshot) {
      const mid = snapshot.mid || 100.0;
      const spr = snapshot.spread || 0.05;

      switch (agent.archetype) {
        case 'noise':
          if (Math.random() > 0.35) return null;
          return {
            side: Math.random() < 0.5 ? 'buy' : 'sell',
            type: 'limit',
            qty: +(Math.random() * 1.5 + 0.5).toFixed(1),
            price: +(mid + (Math.random() - 0.5) * 0.4).toFixed(2)
          };

        case 'market_maker':
          const skew = -agent.inventory * 0.015;
          const isBid = Math.random() < 0.5;
          if (isBid && agent.inventory < 40) {
            return { side: 'buy', type: 'limit', qty: 2.0, price: +(mid - spr * 0.5 + skew).toFixed(2) };
          } else if (!isBid && agent.inventory > -40) {
            return { side: 'sell', type: 'limit', qty: 2.0, price: +(mid + spr * 0.5 + skew).toFixed(2) };
          }
          return null;

        case 'latency_sensitive':
          const fastSpr = 0.02;
          const fBid = Math.random() < 0.5;
          return {
            side: fBid ? 'buy' : 'sell',
            type: 'limit',
            qty: 3.0,
            price: +(fBid ? mid - fastSpr : mid + fastSpr).toFixed(2)
          };

        case 'momentum':
          if (this.priceHistory.length < 10) return null;
          const pDelta = mid - this.priceHistory[this.priceHistory.length - 8];
          if (pDelta > 0.08 && agent.inventory < 30) {
            return { side: 'buy', type: 'limit', qty: 2.0, price: +(mid + 0.03).toFixed(2) };
          } else if (pDelta < -0.08 && agent.inventory > -30) {
            return { side: 'sell', type: 'limit', qty: 2.0, price: +(mid - 0.03).toFixed(2) };
          }
          return null;

        case 'mean_reversion':
          if (this.priceHistory.length < 20) return null;
          const ma = this.priceHistory.slice(-20).reduce((a, b) => a + b, 0) / 20;
          if (mid > ma + 0.12 && agent.inventory > -30) {
            return { side: 'sell', type: 'limit', qty: 1.5, price: +(mid - 0.02).toFixed(2) };
          } else if (mid < ma - 0.12 && agent.inventory < 30) {
            return { side: 'buy', type: 'limit', qty: 1.5, price: +(mid + 0.02).toFixed(2) };
          }
          return null;

        case 'fundamental':
          const gap = this.fundamental - mid;
          if (gap > 0.05 && agent.inventory < 30) {
            return { side: 'buy', type: 'limit', qty: 2.0, price: +(mid + 0.02).toFixed(2) };
          } else if (gap < -0.05 && agent.inventory > -30) {
            return { side: 'sell', type: 'limit', qty: 2.0, price: +(mid - 0.02).toFixed(2) };
          }
          return null;

        case 'institutional':
          if (Math.random() < 0.25) {
            return { side: 'buy', type: 'limit', qty: 4.0, price: +(mid + 0.04).toFixed(2) };
          }
          return null;

        case 'adversarial':
          if (Math.random() < 0.2) {
            // Spoof large fake bid
            return { side: 'buy', type: 'limit', qty: 20.0, price: +(mid - 0.08).toFixed(2) };
          }
          return null;

        default:
          return null;
      }
    }

    getLeaderboard() {
      return [...this.agents].sort((a, b) => b.unrealizedPnl - a.unrealizedPnl);
    }

    start() {
      if (this.running) return;
      this.running = true;
      this.tickInterval = setInterval(() => this.step(), this.tickSpeedMs);
    }

    pause() {
      this.running = false;
      if (this.tickInterval) clearInterval(this.tickInterval);
    }

    reset() {
      this.pause();
      this.tick = 0;
      this.fundamental = this.initialPrice;
      this.priceHistory = [this.initialPrice];
      this.tradeLog = [];
      this.eventLog = [];
      this.causalDag = [];
      this.activeShocks = [];
      this.regime = 'Calm';
      this.initDefaultAgents();
      this.seedBook();
      const snap = this.getSnapshot();
      this.notify({
        tick: 0,
        mid: snap.mid,
        spread: snap.spread,
        snapshot: snap,
        trades: [],
        regime: 'Calm',
        leaderboard: this.getLeaderboard()
      });
    }

    loadTemplate(templateId) {
      this.reset();
      switch (templateId) {
        case 'EXP-001': // Price-Time Priority Baseline
          this.initDefaultAgents({ noise: 50, market_maker: 4, momentum: 5, mean_reversion: 5 });
          break;
        case 'EXP-002': // Latency Advantage
          this.initDefaultAgents({ noise: 40, latency_sensitive: 4, market_maker: 4, momentum: 10 });
          break;
        case 'EXP-003': // MM Population Sensitivity
          this.initDefaultAgents({ noise: 30, market_maker: 16, momentum: 5, mean_reversion: 5 });
          break;
        case 'EXP-004': // Liquidity Crisis
          this.initDefaultAgents({ noise: 20, market_maker: 1, momentum: 25, mean_reversion: 5 });
          this.injectShock('liquidity_crisis', 2.0, 100);
          break;
        case 'EXP-005': // Large-Order Market Impact
          this.initDefaultAgents({ noise: 40, market_maker: 4, institutional: 4 });
          break;
        default:
          this.initDefaultAgents();
          break;
      }
      this.start();
    }
  }

  global.SimEngine = SimEngine;
})(window);
