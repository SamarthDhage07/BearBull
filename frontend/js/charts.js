/**
 * BearBull - High-Performance Financial Charts Renderer
 * Real-time Canvas Candlestick + Volume + Depth Curves + Latency Waterfall
 */

(function(global) {
  'use strict';

  class ChartRenderer {
    constructor() {
      this.candlesticks = [];
      this.currentCandle = null;
      this.candleIntervalTicks = 10;
      this.tickCount = 0;
    }

    onTick(price, volume = 1.0) {
      this.tickCount++;
      if (!this.currentCandle) {
        this.currentCandle = {
          open: price,
          high: price,
          low: price,
          close: price,
          volume: volume,
          ticks: 1
        };
      } else {
        this.currentCandle.high = Math.max(this.currentCandle.high, price);
        this.currentCandle.low = Math.min(this.currentCandle.low, price);
        this.currentCandle.close = price;
        this.currentCandle.volume += volume;
        this.currentCandle.ticks++;
      }

      if (this.currentCandle.ticks >= this.candleIntervalTicks) {
        this.candlesticks.push({ ...this.currentCandle });
        if (this.candlesticks.length > 80) this.candlesticks.shift();
        this.currentCandle = null;
      }
    }

    renderCandleChart(canvasId, rawHistory = []) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const data = this.candlesticks.length > 5 ? this.candlesticks : rawHistory.map((p, i) => ({
        open: p, high: p + 0.03, low: p - 0.03, close: p, volume: 2.0
      }));

      if (data.length < 2) return;

      // Min & Max bounds
      let minP = Math.min(...data.map(d => d.low));
      let maxP = Math.max(...data.map(d => d.high));
      const pad = (maxP - minP) * 0.12 || 0.5;
      minP -= pad; maxP += pad;

      const chartH = h - 35; // Reserve bottom 35px for volume
      const candleW = Math.max(3, (w / data.length) * 0.7);
      const gap = (w / data.length);

      // Grid Lines
      ctx.strokeStyle = '#141c28';
      ctx.lineWidth = 1;
      for (let i = 1; i <= 4; i++) {
        const y = (chartH / 5) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();

        // Price label
        const pVal = maxP - (i / 5) * (maxP - minP);
        ctx.fillStyle = '#4e5d6c';
        ctx.font = '10px "JetBrains Mono", monospace';
        ctx.fillText(pVal.toFixed(2), w - 45, y - 3);
      }

      // Draw Candlesticks & Volume Bars
      data.forEach((c, i) => {
        const x = i * gap + gap * 0.15;
        const isUp = c.close >= c.open;
        const color = isUp ? '#00f090' : '#ff3355';

        const yOpen = chartH - ((c.open - minP) / (maxP - minP)) * chartH;
        const yClose = chartH - ((c.close - minP) / (maxP - minP)) * chartH;
        const yHigh = chartH - ((c.high - minP) / (maxP - minP)) * chartH;
        const yLow = chartH - ((c.low - minP) / (maxP - minP)) * chartH;

        // Wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(x + candleW / 2, yHigh);
        ctx.lineTo(x + candleW / 2, yLow);
        ctx.stroke();

        // Body
        ctx.fillStyle = color;
        const bodyY = Math.min(yOpen, yClose);
        const bodyH = Math.max(2, Math.abs(yClose - yOpen));
        ctx.fillRect(x, bodyY, candleW, bodyH);

        // Volume bar
        const volH = Math.min(25, (c.volume / 10.0) * 20);
        ctx.fillStyle = isUp ? 'rgba(0, 240, 144, 0.25)' : 'rgba(255, 51, 85, 0.25)';
        ctx.fillRect(x, h - volH, candleW, volH);
      });

      // Moving Average (MA9)
      if (data.length > 9) {
        ctx.strokeStyle = '#00b4ff';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let i = 8; i < data.length; i++) {
          const slice = data.slice(i - 8, i + 1);
          const ma = slice.reduce((sum, d) => sum + d.close, 0) / 9;
          const x = i * gap + gap * 0.15 + candleW / 2;
          const y = chartH - ((ma - minP) / (maxP - minP)) * chartH;
          if (i === 8) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    }

    renderDepthCurve(canvasId, bids = [], asks = []) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      if (bids.length === 0 || asks.length === 0) return;

      // Cumulative sums
      let cumBid = 0;
      const bidPoints = bids.map(b => { cumBid += b.quantity; return { price: b.price, cum: cumBid }; }).reverse();
      let cumAsk = 0;
      const askPoints = asks.map(a => { cumAsk += a.quantity; return { price: a.price, cum: cumAsk }; });

      const maxCum = Math.max(cumBid, cumAsk, 10);
      const minP = bidPoints[0].price;
      const maxP = askPoints[askPoints.length - 1].price;

      // Draw Bid Green Area
      ctx.fillStyle = 'rgba(0, 240, 144, 0.2)';
      ctx.strokeStyle = '#00f090';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, h);
      bidPoints.forEach((pt, i) => {
        const x = ((pt.price - minP) / (maxP - minP)) * (w * 0.5);
        const y = h - (pt.cum / maxCum) * (h * 0.85);
        if (i === 0) ctx.lineTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineTo(w * 0.5, h);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Draw Ask Red Area
      ctx.fillStyle = 'rgba(255, 51, 85, 0.2)';
      ctx.strokeStyle = '#ff3355';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(w * 0.5, h);
      askPoints.forEach((pt, i) => {
        const x = (w * 0.5) + ((pt.price - (bids[0].price || 100)) / (maxP - minP)) * (w * 0.5);
        const y = h - (pt.cum / maxCum) * (h * 0.85);
        ctx.lineTo(x, y);
      });
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
  }

  global.ChartRenderer = ChartRenderer;
})(window);
