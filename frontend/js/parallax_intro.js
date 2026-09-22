/**
 * BearBull - Interactive Parallax Stock Graph Scroll Intro
 * Pinned scroll experience tracing a stock market graph with a glowing green dot,
 * price telemetry, and smooth reveal into the Home Page.
 */

(function(global) {
  'use strict';

  class ParallaxIntro {
    constructor() {
      this.wrapper = document.getElementById('scrollIntroWrapper');
      this.canvas = document.getElementById('parallaxChartCanvas');
      this.hudPrice = document.getElementById('introHudPrice');
      this.hudGain = document.getElementById('introHudGain');
      this.hudStage = document.getElementById('introHudStage');
      this.progressBar = document.getElementById('introProgressBar');
      this.homeView = document.getElementById('view-home');

      this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
      this.progress = 0; // 0.0 to 1.0
      this.targetProgress = 0;
      this.active = true;

      // Stock path points (normalized x: 0..1, y: 0..1)
      this.chartPoints = [
        { x: 0.00, y: 0.65, p: 100.00 },
        { x: 0.12, y: 0.58, p: 101.40 },
        { x: 0.20, y: 0.72, p: 99.20 },
        { x: 0.32, y: 0.48, p: 103.80 },
        { x: 0.44, y: 0.55, p: 102.10 },
        { x: 0.56, y: 0.35, p: 106.50 },
        { x: 0.68, y: 0.42, p: 104.90 },
        { x: 0.80, y: 0.22, p: 109.80 },
        { x: 0.92, y: 0.28, p: 108.40 },
        { x: 1.00, y: 0.15, p: 112.50 }
      ];

      this.init();
    }

    init() {
      if (!this.wrapper || !this.canvas) return;

      this.resizeCanvas();
      window.addEventListener('resize', () => this.resizeCanvas());

      // Listen for scroll & wheel events
      window.addEventListener('scroll', () => this.onScroll());
      window.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });

      // Skip intro on ESC or Skip button click
      const skipBtn = document.getElementById('btnSkipIntro');
      if (skipBtn) {
        skipBtn.addEventListener('click', () => this.completeIntro());
      }
      window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.active) this.completeIntro();
      });

      // Start animation render loop
      this.renderLoop();
    }

    resizeCanvas() {
      if (!this.canvas) return;
      const dpr = window.devicePixelRatio || 1;
      const w = window.innerWidth;
      const h = window.innerHeight;
      this.canvas.width = w * dpr;
      this.canvas.height = h * dpr;
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
      if (this.ctx) this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    onWheel(e) {
      if (!this.active) return;

      // If intro is active, hijack initial scroll delta to drive market graph tracing
      if (this.progress < 1.0) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.08 : -0.08;
        this.targetProgress = Math.max(0, Math.min(1.0, this.targetProgress + delta));
        if (this.targetProgress >= 0.99) {
          setTimeout(() => this.completeIntro(), 200);
        }
      }
    }

    onScroll() {
      if (!this.active || !this.wrapper) return;
      const rect = this.wrapper.getBoundingClientRect();
      const scrollDist = -rect.top;
      const totalScroll = rect.height - window.innerHeight;
      if (totalScroll > 0) {
        this.targetProgress = Math.max(0, Math.min(1.0, scrollDist / totalScroll));
        if (this.targetProgress >= 0.99) {
          this.completeIntro();
        }
      }
    }

    completeIntro() {
      if (!this.active) return;
      this.active = false;
      this.progress = 1.0;
      if (this.wrapper) {
        this.wrapper.style.transition = 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)';
        this.wrapper.style.opacity = '0';
        this.wrapper.style.transform = 'translateY(-40px)';
        this.wrapper.style.pointerEvents = 'none';
        setTimeout(() => {
          this.wrapper.style.display = 'none';
        }, 600);
      }
      window.scrollTo({ top: 0, behavior: 'instant' });
    }

    getInterpolatedPoint(t) {
      const n = this.chartPoints.length - 1;
      const indexFloat = t * n;
      const i0 = Math.floor(indexFloat);
      const i1 = Math.min(n, i0 + 1);
      const f = indexFloat - i0;

      const p0 = this.chartPoints[i0];
      const p1 = this.chartPoints[i1];

      return {
        x: p0.x + (p1.x - p0.x) * f,
        y: p0.y + (p1.y - p0.y) * f,
        p: p0.p + (p1.p - p0.p) * f
      };
    }

    renderLoop() {
      // Smooth lerp progress
      this.progress += (this.targetProgress - this.progress) * 0.12;

      if (this.ctx && this.active) {
        const w = window.innerWidth;
        const h = window.innerHeight;
        this.ctx.clearRect(0, 0, w, h);

        // Grid background lines
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        this.ctx.lineWidth = 1;
        const padX = 80;
        const padY = 120;
        const chartW = w - padX * 2;
        const chartH = h - padY * 2;

        for (let i = 0; i <= 4; i++) {
          const y = padY + (chartH / 4) * i;
          this.ctx.beginPath();
          this.ctx.moveTo(padX, y);
          this.ctx.lineTo(w - padX, y);
          this.ctx.stroke();
        }

        // Draw green trajectory curve up to current progress
        if (this.progress > 0.01) {
          const steps = Math.floor(this.progress * 120);
          this.ctx.beginPath();
          this.ctx.strokeStyle = '#25f284';
          this.ctx.lineWidth = 3;
          this.ctx.shadowColor = '#25f284';
          this.ctx.shadowBlur = 18;

          for (let s = 0; s <= steps; s++) {
            const t = s / 120;
            const pt = this.getInterpolatedPoint(t);
            const cx = padX + pt.x * chartW;
            const cy = padY + pt.y * chartH;
            if (s === 0) this.ctx.moveTo(cx, cy);
            else this.ctx.lineTo(cx, cy);
          }
          this.ctx.stroke();
          this.ctx.shadowBlur = 0;

          // Glowing Head Particle (Green Dot)
          const currPt = this.getInterpolatedPoint(this.progress);
          const dotX = padX + currPt.x * chartW;
          const dotY = padY + currPt.y * chartH;

          // Pulsing Glow Ring
          const pulse = Math.sin(Date.now() * 0.008) * 4 + 10;
          this.ctx.fillStyle = 'rgba(37, 242, 132, 0.25)';
          this.ctx.beginPath();
          this.ctx.arc(dotX, dotY, pulse + 6, 0, Math.PI * 2);
          this.ctx.fill();

          // Solid Center Dot
          this.ctx.fillStyle = '#25f284';
          this.ctx.shadowColor = '#25f284';
          this.ctx.shadowBlur = 20;
          this.ctx.beginPath();
          this.ctx.arc(dotX, dotY, 7, 0, Math.PI * 2);
          this.ctx.fill();
          this.ctx.shadowBlur = 0;

          // Update HUD values
          if (this.hudPrice) this.hudPrice.textContent = `₹${currPt.p.toFixed(2)}`;
          if (this.hudGain) {
            const pct = ((currPt.p - 100.0) / 100.0) * 100;
            this.hudGain.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
          }
          if (this.hudStage) {
            const stageNum = Math.min(5, Math.floor(this.progress * 5) + 1);
            this.hudStage.textContent = `STAGE 0${stageNum} / 05 // TRACING LOB MATCHING TRAJECTORY`;
          }
          if (this.progressBar) {
            this.progressBar.style.width = `${(this.progress * 100).toFixed(0)}%`;
          }
        }
      }

      if (this.active) {
        requestAnimationFrame(() => this.renderLoop());
      }
    }
  }

  global.ParallaxIntro = ParallaxIntro;
})(window);
