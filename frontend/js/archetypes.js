/**
 * BearBull - Agent Archetypes, RL Training Studio & Strategy DSL Controller
 */

(function(global) {
  'use strict';

  class ArchetypeManager {
    constructor() {
      this.rlState = {
        training: false,
        episodes: 0,
        rewards: [],
        currentReward: 0,
        inventoryPenalty: 0.05
      };

      this.visualStrategyRules = [
        { ifMetric: 'ofi', op: '>', val: '0.4', thenAction: 'buy_passive' },
        { ifMetric: 'spread', op: '>', val: '0.10', thenAction: 'mm_widen' }
      ];
    }

    renderAgentLeaderboard(containerId, agents = []) {
      const el = document.getElementById(containerId);
      if (!el) return;

      if (agents.length === 0) {
        el.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">No active agent metrics</td></tr>';
        return;
      }

      el.innerHTML = agents.map((a, idx) => {
        const pnl = a.unrealizedPnl !== undefined ? a.unrealizedPnl : (a.unrealized_pnl || 0);
        const pnlCls = pnl >= 0 ? 'color:var(--bid-green);' : 'color:var(--ask-red);';
        const fillRate = a.submitted ? ((a.filled / a.submitted) * 100).toFixed(0) : 0;

        return `
          <tr>
            <td>#${idx + 1} <b>${a.id || a.agent_id}</b></td>
            <td><span class="badge-tag">${a.archetype}</span></td>
            <td>${a.inventory || 0}</td>
            <td style="${pnlCls}">₹${pnl.toFixed(2)}</td>
            <td>${fillRate}%</td>
            <td>${a.latencyUs || 15}μs</td>
          </tr>
        `;
      }).join('');
    }

    stepRLTraining() {
      this.rlState.episodes++;
      const baseReward = (Math.random() - 0.42) * 5.0;
      const penalty = Math.random() * 0.5 * this.rlState.inventoryPenalty;
      const stepReward = +(baseReward - penalty).toFixed(2);
      this.rlState.currentReward = +(this.rlState.currentReward + stepReward).toFixed(2);
      this.rlState.rewards.push(this.rlState.currentReward);
      if (this.rlState.rewards.length > 50) this.rlState.rewards.shift();

      this.renderRLVisualizer();
    }

    renderRLVisualizer() {
      const epEl = document.getElementById('rlEpisodeNum');
      const rewEl = document.getElementById('rlCumulativeRew');
      if (epEl) epEl.textContent = this.rlState.episodes;
      if (rewEl) {
        rewEl.textContent = `₹${this.rlState.currentReward.toFixed(2)}`;
        rewEl.style.color = this.rlState.currentReward >= 0 ? 'var(--bid-green)' : 'var(--ask-red)';
      }

      const canvas = document.getElementById('rlRewardChart');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const w = canvas.clientWidth, h = canvas.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      if (this.rlState.rewards.length < 2) return;
      const min = Math.min(...this.rlState.rewards);
      const max = Math.max(...this.rlState.rewards);
      const pad = (max - min) * 0.1 || 1;

      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 2;
      ctx.beginPath();
      this.rlState.rewards.forEach((r, i) => {
        const x = (i / (this.rlState.rewards.length - 1)) * w;
        const y = h - ((r - (min - pad)) / ((max + pad) - (min - pad))) * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
  }

  global.ArchetypeManager = ArchetypeManager;
})(window);
