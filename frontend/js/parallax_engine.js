/**
 * BearBull - Creative Parallax & Floating Ball Engine
 * Inspired by format.obys.agency:
 * - Dynamic 3D interactive floating/sliding ball with spring physics & scroll trajectory
 * - Toggleable on/off control for the cursor ball
 * - Multi-layer parallax scroll controller for cards, headers, badges, and charts
 * - Kinetic horizontal typography sliding in opposite directions on scroll
 * - 3D card perspective tilt with magnetic spotlight illumination
 */

(function(global) {
  'use strict';

  class CreativeParallaxEngine {
    constructor() {
      this.scrollY = window.scrollY || 0;
      this.targetScrollY = this.scrollY;
      this.mouseX = window.innerWidth / 2;
      this.mouseY = window.innerHeight / 2;
      this.ballX = this.mouseX;
      this.ballY = this.mouseY;
      this.ballAngle = 0;
      this.ballScale = 1;
      this.targetScale = 1;
      this.isHoveringCard = false;
      this.hoverText = '';

      // Check user preference (defaults to true)
      const savedState = localStorage.getItem('bearbull_orb_enabled');
      this.ballEnabled = savedState !== null ? savedState === 'true' : true;

      this.initBall();
      this.initToggleButton();
      this.initParallaxElements();
      this.initTiltCards();
      this.initKineticText();
      this.bindEvents();
      this.startLoop();
    }

    initBall() {
      // Create DOM element for the creative floating ball
      let ball = document.getElementById('creativeFloatingBall');
      if (!ball) {
        ball = document.createElement('div');
        ball.id = 'creativeFloatingBall';
        ball.className = 'creative-floating-ball';
        ball.innerHTML = `
          <div class="ball-inner-sphere">
            <div class="ball-specular"></div>
            <div class="ball-core-glow"></div>
            <div class="ball-ring-orbit"></div>
          </div>
          <div class="ball-cursor-label" id="ballCursorLabel">EXPLORE</div>
        `;
        document.body.appendChild(ball);
      }
      this.ballEl = ball;
      this.ballLabelEl = document.getElementById('ballCursorLabel');
      this.updateBallVisibility();
    }

    initToggleButton() {
      const toggleBtn = document.getElementById('btnToggleOrb');
      if (toggleBtn) {
        this.updateButtonUI(toggleBtn);
        toggleBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleBall();
        });
      }
    }

    toggleBall() {
      this.ballEnabled = !this.ballEnabled;
      localStorage.setItem('bearbull_orb_enabled', this.ballEnabled);
      this.updateBallVisibility();
      const toggleBtn = document.getElementById('btnToggleOrb');
      if (toggleBtn) {
        this.updateButtonUI(toggleBtn);
      }
    }

    updateButtonUI(btn) {
      if (this.ballEnabled) {
        btn.innerHTML = '🟢 ORB: ON';
        btn.style.color = 'var(--acid-green)';
        btn.style.borderColor = 'rgba(37, 242, 132, 0.4)';
      } else {
        btn.innerHTML = '⚪ ORB: OFF';
        btn.style.color = 'var(--text-muted)';
        btn.style.borderColor = 'var(--border-line)';
      }
    }

    updateBallVisibility() {
      if (!this.ballEl) return;
      if (this.ballEnabled) {
        this.ballEl.style.display = 'flex';
        this.ballEl.style.opacity = '1';
      } else {
        this.ballEl.style.display = 'none';
        this.ballEl.style.opacity = '0';
      }
    }

    initParallaxElements() {
      this.parallaxItems = document.querySelectorAll('[data-parallax-speed]');
    }

    initTiltCards() {
      const tiltCards = document.querySelectorAll('.obys-card, .parallax-gallery-card, .agent-box, .shock-card, .parallax-float-card');
      tiltCards.forEach(card => {
        card.addEventListener('mousemove', (e) => this.handleCardTilt(e, card));
        card.addEventListener('mouseleave', () => this.resetCardTilt(card));
        card.addEventListener('mouseenter', () => {
          if (!this.ballEnabled) return;
          this.isHoveringCard = true;
          this.targetScale = 1.35;
          const customText = card.getAttribute('data-orb-text') || 'EXPLORE';
          if (this.ballLabelEl) {
            this.ballLabelEl.textContent = customText;
            this.ballLabelEl.classList.add('visible');
          }
          if (this.ballEl) this.ballEl.classList.add('magnet-hover');
        });
        card.addEventListener('mouseleave', () => {
          this.isHoveringCard = false;
          this.targetScale = 1.0;
          if (this.ballLabelEl) {
            this.ballLabelEl.classList.remove('visible');
          }
          if (this.ballEl) this.ballEl.classList.remove('magnet-hover');
        });
      });
    }

    handleCardTilt(e, card) {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;

      const rotateX = ((y - centerY) / centerY) * -8;
      const rotateY = ((x - centerX) / centerX) * 8;

      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-3px)`;

      // Dynamic sheen reflection
      card.style.setProperty('--sheen-x', `${(x / rect.width) * 100}%`);
      card.style.setProperty('--sheen-y', `${(y / rect.height) * 100}%`);
    }

    resetCardTilt(card) {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0)';
    }

    initKineticText() {
      this.kineticRowLeft = document.querySelectorAll('.kinetic-slide-left');
      this.kineticRowRight = document.querySelectorAll('.kinetic-slide-right');
    }

    bindEvents() {
      window.addEventListener('scroll', () => {
        this.targetScrollY = window.scrollY || window.pageYOffset;
      }, { passive: true });

      window.addEventListener('mousemove', (e) => {
        this.mouseX = e.clientX;
        this.mouseY = e.clientY;
      }, { passive: true });

      window.addEventListener('resize', () => {
        this.initParallaxElements();
      });
    }

    startLoop() {
      const tick = () => {
        // Smooth lerp scroll interpolation
        this.scrollY += (this.targetScrollY - this.scrollY) * 0.12;

        // Calculate scroll velocity & trajectory
        const scrollDelta = this.targetScrollY - this.scrollY;

        // Ball physics
        if (this.ballEnabled && this.ballEl) {
          const scrollDisplacementX = Math.sin(this.scrollY * 0.003) * 160;
          const scrollDisplacementY = Math.cos(this.scrollY * 0.002) * 80;

          const targetBallX = this.mouseX + scrollDisplacementX * 0.35;
          const targetBallY = this.mouseY + scrollDisplacementY * 0.35;

          this.ballX += (targetBallX - this.ballX) * 0.12;
          this.ballY += (targetBallY - this.ballY) * 0.12;
          this.ballScale += (this.targetScale - this.ballScale) * 0.15;
          this.ballAngle += scrollDelta * 0.25 + 0.5;

          this.ballEl.style.transform = `translate3d(${this.ballX}px, ${this.ballY}px, 0) scale(${this.ballScale}) rotate(${this.ballAngle}deg)`;
        }

        // Update Multi-Layer Parallax Elements
        const viewportHeight = window.innerHeight;
        this.parallaxItems.forEach(el => {
          const speed = parseFloat(el.getAttribute('data-parallax-speed')) || 0.2;
          const rect = el.getBoundingClientRect();
          
          if (rect.top < viewportHeight + 300 && rect.bottom > -300) {
            const distanceFromCenter = (rect.top + rect.height / 2) - (viewportHeight / 2);
            const translateY = distanceFromCenter * speed * -1;
            const rotate = el.getAttribute('data-parallax-rotate') ? (distanceFromCenter * 0.015 * speed) : 0;
            const translateX = el.getAttribute('data-parallax-x') ? (distanceFromCenter * speed * 0.4) : 0;

            if (rotate !== 0 || translateX !== 0) {
              el.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) rotate(${rotate}deg)`;
            } else {
              el.style.transform = `translate3d(0, ${translateY}px, 0)`;
            }
          }
        });

        // Update Kinetic Typographic Rows
        const scrollOffset = this.scrollY * 0.4;
        if (this.kineticRowLeft) {
          this.kineticRowLeft.forEach(row => {
            row.style.transform = `translateX(${-scrollOffset % 1200}px)`;
          });
        }
        if (this.kineticRowRight) {
          this.kineticRowRight.forEach(row => {
            row.style.transform = `translateX(${(scrollOffset % 1200) - 600}px)`;
          });
        }

        requestAnimationFrame(tick);
      };

      requestAnimationFrame(tick);
    }
  }

  // Auto-instantiate when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      global.creativeParallax = new CreativeParallaxEngine();
    });
  } else {
    global.creativeParallax = new CreativeParallaxEngine();
  }

  global.CreativeParallaxEngine = CreativeParallaxEngine;

})(window);
