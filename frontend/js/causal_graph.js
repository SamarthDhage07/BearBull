/**
 * BearBull - Causal Event Graph & Latency Waterfall Inspector (PRD Section 25.6 & 63)
 */

(function(global) {
  'use strict';

  class CausalGraphViewer {
    constructor() {
      this.selectedTrade = null;
    }

    inspectTrade(tradeRecord, containerId = 'causalDetailPanel') {
      this.selectedTrade = tradeRecord;
      const el = document.getElementById(containerId);
      if (!el) return;

      if (!tradeRecord) {
        el.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px;">Click any trade in the tape to trace its causal ancestry and latency footprint.</div>';
        return;
      }

      const wf = tradeRecord.latencyWaterfall || {
        ingressUs: 15,
        validateUs: 2,
        matchUs: 3,
        queueWaitUs: 8,
        egressUs: 12,
        totalUs: 40
      };

      const total = wf.totalUs || (wf.ingressUs + wf.validateUs + wf.matchUs + wf.queueWaitUs + wf.egressUs);
      const pIngress = ((wf.ingressUs / total) * 100).toFixed(0);
      const pVal = ((wf.validateUs / total) * 100).toFixed(0);
      const pMatch = ((wf.matchUs / total) * 100).toFixed(0);
      const pQueue = ((wf.queueWaitUs / total) * 100).toFixed(0);
      const pEgress = ((wf.egressUs / total) * 100).toFixed(0);

      el.innerHTML = `
        <div style="background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:8px;padding:14px;font-family:var(--font-sans);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <div style="font-size:15px;font-weight:700;color:var(--text-main);">
              Trade #<b>${tradeRecord.tradeId || tradeRecord.trade_id}</b> Causal Ancestry
            </div>
            <span class="badge-tag" style="background:var(--bid-green-bg);color:var(--bid-green);">EXECUTED</span>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;font-size:12px;font-family:var(--font-mono);">
            <div style="background:var(--bg-tertiary);padding:8px;border-radius:5px;">
              <span style="color:var(--text-muted);">Aggressor (Taker):</span><br/>
              <b>${tradeRecord.aggressorId || tradeRecord.aggressor_id || 'noise_1'}</b> (${(tradeRecord.side || 'BUY').toUpperCase()})
            </div>
            <div style="background:var(--bg-tertiary);padding:8px;border-radius:5px;">
              <span style="color:var(--text-muted);">Resting Counterpart (Maker):</span><br/>
              <b>${tradeRecord.makerId || tradeRecord.maker_id || 'market_maker_1'}</b>
            </div>
            <div style="background:var(--bg-tertiary);padding:8px;border-radius:5px;">
              <span style="color:var(--text-muted);">Execution Price:</span><br/>
              <b>₹${Number(tradeRecord.price).toFixed(2)}</b>
            </div>
            <div style="background:var(--bg-tertiary);padding:8px;border-radius:5px;">
              <span style="color:var(--text-muted);">Quantity Matched:</span><br/>
              <b>${tradeRecord.quantity} units</b>
            </div>
          </div>

          <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px;">
            End-to-End Latency Footprint: <span style="color:var(--accent-cyan);">${total} μs</span>
          </div>

          <div class="waterfall-bar-wrap">
            <div class="wf-segment wf-ingress" style="width:${pIngress}%;" title="Simulated Network Ingress: ${wf.ingressUs}μs">${wf.ingressUs}μs Ingress</div>
            <div class="wf-segment wf-validate" style="width:${pVal}%;" title="Risk Engine Check: ${wf.validateUs}μs">${wf.validateUs}μs</div>
            <div class="wf-segment wf-match" style="width:${pMatch}%;" title="Order Book Matching: ${wf.matchUs}μs">${wf.matchUs}μs</div>
            <div class="wf-segment wf-queue" style="width:${pQueue}%;" title="Queue Wait Time: ${wf.queueWaitUs}μs">${wf.queueWaitUs}μs Queue</div>
            <div class="wf-segment wf-egress" style="width:${pEgress}%;" title="Trade Ack Egress: ${wf.egressUs}μs">${wf.egressUs}μs</div>
          </div>

          <div style="display:flex;gap:12px;font-size:10px;font-family:var(--font-mono);color:var(--text-muted);flex-wrap:wrap;margin-top:6px;">
            <span><span style="color:#3b82f6;">■</span> Ingress</span>
            <span><span style="color:#10b981;">■</span> Risk Validate</span>
            <span><span style="color:#f59e0b;">■</span> Book Match</span>
            <span><span style="color:#ef4444;">■</span> Queue Wait</span>
            <span><span style="color:#8b5cf6;">■</span> Ack Egress</span>
          </div>
        </div>
      `;
    }
  }

  global.CausalGraphViewer = CausalGraphViewer;
})(window);
