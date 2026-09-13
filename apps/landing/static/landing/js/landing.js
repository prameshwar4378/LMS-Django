// InnVetrix Interactive SaaS Engine - Powered by Ultoxy Technologies
(function() {
  'use strict';

  // Mark document as JS-enabled for progressive animation enhancement
  if (typeof document !== 'undefined') {
    document.documentElement.classList.add('js-reveal');
  }

  // ==========================================================================
  // 0. LUXURY FULL-PAGE PRELOADER CONTROLLER (Immediate Kickoff)
  // ==========================================================================
  (function initPreloader() {
    const preloader = document.getElementById('page-preloader');
    const progressBar = document.getElementById('preloaderProgressBar');
    const percentLabel = document.getElementById('preloaderPercent');
    const statusText = document.getElementById('preloaderStatusText');

    if (!preloader) return;

    let currentProgress = 14;
    let isPageLoaded = false;
    const startTime = Date.now();

    const statusMilestones = [
      { at: 20, text: 'Initializing Cloud Architecture...' },
      { at: 50, text: 'Calibrating Front-Desk Tape Chart...' },
      { at: 75, text: 'Connecting Secure PMS Pipeline...' },
      { at: 96, text: 'Welcome to InnVetrix' },
    ];

    function setProgress(val) {
      currentProgress = Math.min(100, Math.max(currentProgress, val));
      if (progressBar) progressBar.style.width = `${currentProgress}%`;
      if (percentLabel) percentLabel.textContent = `${Math.round(currentProgress)}%`;
      if (statusText) {
        for (let i = statusMilestones.length - 1; i >= 0; i--) {
          if (currentProgress >= statusMilestones[i].at) {
            statusText.textContent = statusMilestones[i].text;
            break;
          }
        }
      }
    }

    setProgress(currentProgress);

    // Dynamic progression simulation while assets load
    const progressTimer = setInterval(() => {
      if (isPageLoaded) {
        clearInterval(progressTimer);
        return;
      }
      if (currentProgress < 88) {
        const increment = Math.random() * 9 + 5;
        setProgress(currentProgress + increment);
      }
    }, 60);

    function dismissPreloader() {
      if (isPageLoaded) return;
      isPageLoaded = true;
      clearInterval(progressTimer);

      setProgress(100);

      // Smooth eye-pleasing pause at 100% (min 350ms total run time)
      const elapsed = Date.now() - startTime;
      const finishDelay = Math.max(0, 350 - elapsed) + 160;

      setTimeout(() => {
        preloader.classList.add('is-loaded');
        document.body.classList.remove('loading');

        // Cleanup display after transition completes
        setTimeout(() => {
          preloader.style.display = 'none';
        }, 600);
      }, finishDelay);
    }

    if (document.readyState === 'complete') {
      dismissPreloader();
    } else {
      window.addEventListener('load', dismissPreloader);
    }

    // Safety fallback: Dismiss after 1.8s max under any condition
    setTimeout(dismissPreloader, 1800);
  })();

  function initInnVetrix() {

    // ==========================================================================
    // 1. STICKY NAVBAR TRANSITION
    // ==========================================================================
    const navbar = document.querySelector('.navbar-glass');
    if (navbar) {
      const handleScroll = () => {
        if (window.scrollY > 25) {
          navbar.classList.add('scrolled');
        } else {
          navbar.classList.remove('scrolled');
        }
      };
      window.addEventListener('scroll', handleScroll, { passive: true });
      handleScroll(); // Initial check
    }

    // ==========================================================================
    // 2. BULLETPROOF SCROLL REVEAL (PROGRESSIVE ENHANCEMENT)
    // ==========================================================================
    const revealElements = document.querySelectorAll('.reveal-on-scroll, .reveal-left, .reveal-right, .reveal-scale');

    // Immediately reveal all elements currently inside or near the viewport
    function revealVisibleElements() {
      const windowHeight = window.innerHeight || document.documentElement.clientHeight;
      revealElements.forEach(el => {
        if (el.classList.contains('is-revealed')) return;
        const rect = el.getBoundingClientRect();
        // If element top is within viewport + 80px buffer, reveal immediately
        if (rect.top <= windowHeight + 80 && rect.bottom >= -50) {
          el.classList.add('is-revealed');
        }
      });
    }

    revealVisibleElements();

    if ('IntersectionObserver' in window && revealElements.length > 0) {
      const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            observer.unobserve(entry.target); // Trigger once
          }
        });
      }, {
        threshold: 0.05,
        rootMargin: '0px 0px 60px 0px'
      });

      revealElements.forEach(el => {
        if (!el.classList.contains('is-revealed')) {
          revealObserver.observe(el);
        }
      });
    } else {
      // Fallback: reveal all immediately
      revealElements.forEach(el => el.classList.add('is-revealed'));
    }

    // Safety failsafe: reveal any remaining hidden elements after 1.2 seconds
    setTimeout(() => {
      revealElements.forEach(el => el.classList.add('is-revealed'));
    }, 1200);

    // ==========================================================================
    // 3. DYNAMIC NUMBER COUNTER ANIMATION ON SCROLL
    // ==========================================================================
    const counterElements = document.querySelectorAll('[data-counter-target]');

    function runCounterAnimation(el) {
      const target = parseFloat(el.getAttribute('data-counter-target'));
      if (isNaN(target)) return;
      const prefix = el.getAttribute('data-counter-prefix') || '';
      const suffix = el.getAttribute('data-counter-suffix') || '';
      const decimals = parseInt(el.getAttribute('data-counter-decimals') || '0', 10);
      const duration = 1800; // ms
      const startTime = performance.now();

      function updateCounter(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3);
        const currentVal = target * easeProgress;

        let formattedNumber;
        if (decimals > 0) {
          formattedNumber = currentVal.toFixed(decimals);
        } else {
          formattedNumber = Math.floor(currentVal).toLocaleString('en-IN');
        }

        el.textContent = prefix + formattedNumber + suffix;

        if (progress < 1) {
          requestAnimationFrame(updateCounter);
        } else {
          if (decimals > 0) {
            el.textContent = prefix + target.toFixed(decimals) + suffix;
          } else {
            el.textContent = prefix + target.toLocaleString('en-IN') + suffix;
          }
        }
      }

      requestAnimationFrame(updateCounter);
    }

    if ('IntersectionObserver' in window && counterElements.length > 0) {
      const counterObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            runCounterAnimation(entry.target);
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.15 });

      counterElements.forEach(el => counterObserver.observe(el));
    } else {
      counterElements.forEach(el => runCounterAnimation(el));
    }

    // ==========================================================================
    // 4. MOUSE-TRACKING SPOTLIGHT GLOW ON GLASS CARDS
    // ==========================================================================
    const glassCards = document.querySelectorAll('.glass-card');
    glassCards.forEach(card => {
      card.addEventListener('mousemove', function(e) {
        const rect = card.getBoundingClientRect();
        const x = Math.round(e.clientX - rect.left);
        const y = Math.round(e.clientY - rect.top);
        card.style.setProperty('--mouse-x', x + 'px');
        card.style.setProperty('--mouse-y', y + 'px');
      }, { passive: true });
    });

    // ==========================================================================
    // 5. HERO PRODUCT SHOWCASE TABS SWITCHER
    // ==========================================================================
    const tabBtns = document.querySelectorAll('.mockup-tab-btn');
    const tabPanes = document.querySelectorAll('.mockup-tab-pane');

    tabBtns.forEach(btn => {
      btn.addEventListener('click', function() {
        const targetTab = this.getAttribute('data-target-tab');

        tabBtns.forEach(b => b.classList.remove('active'));
        tabPanes.forEach(p => p.classList.remove('active'));

        this.classList.add('active');
        const activePane = document.getElementById(targetTab);
        if (activePane) {
          activePane.classList.add('active');
        }
      });
    });

    // ==========================================================================
    // 6. LIVE ACTIVITY TICKER (DYNAMIC LODGE UPDATES)
    // ==========================================================================
    const tickerText = document.getElementById('activityTickerText');
    const liveUpdates = [
      "Hilltop Residency (32 Rooms, Pune) verified morning shift handover • ₹0.00 discrepancy.",
      "Grand Heritage Inn registered express walk-in check-in for Deluxe 204 in 38 seconds.",
      "Royal Palace Stays generated 80mm GST thermal receipt roll for ₹4,850.",
      "Guest in Room 102 ordered room service via Dynamic QR Standee.",
      "Sunrise Boutique Lodge completed full daily night audit and revenue reconciliation."
    ];
    let updateIndex = 0;

    if (tickerText) {
      setInterval(() => {
        tickerText.style.opacity = '0';
        tickerText.style.transform = 'translateY(-6px)';

        setTimeout(() => {
          updateIndex = (updateIndex + 1) % liveUpdates.length;
          tickerText.textContent = liveUpdates[updateIndex];
          tickerText.style.opacity = '1';
          tickerText.style.transform = 'translateY(0)';
        }, 300);
      }, 4500);
    }

    // ==========================================================================
    // 7. PRICING FREQUENCY TOGGLE (MONTHLY VS ANNUAL)
    // ==========================================================================
    const billingCheckbox = document.getElementById('billingFrequencyToggle');
    const starterPrice = document.getElementById('starterPrice');
    const boutiquePrice = document.getElementById('boutiquePrice');
    const starterPeriod = document.getElementById('starterPeriod');
    const boutiquePeriod = document.getElementById('boutiquePeriod');
    const billingMonthlyLabel = document.getElementById('labelMonthly');
    const billingAnnualLabel = document.getElementById('labelAnnual');

    if (billingCheckbox && starterPrice && boutiquePrice) {
      billingCheckbox.addEventListener('change', function() {
        if (this.checked) {
          starterPrice.textContent = '799';
          boutiquePrice.textContent = '1,999';
          if (starterPeriod) starterPeriod.textContent = '/ month, billed annually';
          if (boutiquePeriod) boutiquePeriod.textContent = '/ month, billed annually';
          if (billingAnnualLabel) billingAnnualLabel.classList.add('active');
          if (billingMonthlyLabel) billingMonthlyLabel.classList.remove('active');
        } else {
          starterPrice.textContent = '999';
          boutiquePrice.textContent = '2,499';
          if (starterPeriod) starterPeriod.textContent = '/ month';
          if (boutiquePeriod) boutiquePeriod.textContent = '/ month';
          if (billingMonthlyLabel) billingMonthlyLabel.classList.add('active');
          if (billingAnnualLabel) billingAnnualLabel.classList.remove('active');
        }
      });
    }

    // ==========================================================================
    // 8. AUTO-DISMISS ALERT MESSAGES
    // ==========================================================================
    const autoAlerts = document.querySelectorAll('.alert-dismissible');
    autoAlerts.forEach(alert => {
      setTimeout(() => {
        if (alert && alert.parentNode) {
          alert.classList.remove('show');
          setTimeout(() => alert.remove(), 400);
        }
      }, 7000);
    });

    // ==========================================================================
    // 9. CAPTCHA 1-CLICK AJAX REFRESH
    // ==========================================================================
    const refreshCaptchaBtns = document.querySelectorAll('.btn-refresh-captcha');
    refreshCaptchaBtns.forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        const icon = btn.querySelector('i');
        if (icon) icon.classList.add('spin-fast');

        fetch('/api/captcha/refresh/')
          .then(res => res.json())
          .then(data => {
            if (data.status === 'success') {
              const targetImgSelector = btn.getAttribute('data-target-img');
              const targetTokenSelector = btn.getAttribute('data-target-token');
              
              if (targetImgSelector) {
                const img = document.querySelector(targetImgSelector);
                if (img) img.src = data.challenge_svg;
              }
              if (targetTokenSelector) {
                const tokenInputs = document.querySelectorAll(targetTokenSelector);
                tokenInputs.forEach(input => { input.value = data.token; });
              }
            }
          })
          .catch(err => {
            console.error('Error refreshing captcha challenge:', err);
          })
          .finally(() => {
            setTimeout(() => {
              if (icon) icon.classList.remove('spin-fast');
            }, 400);
          });
      });
    });

    // ==========================================================================
    // 10. ANIMATED POPUP FEEDBACK DIALOGUE MODAL
    // ==========================================================================
    const feedbackModalEl = document.getElementById('innvetrixFeedbackModal');
    if (feedbackModalEl && typeof bootstrap !== 'undefined') {
      const feedbackModal = new bootstrap.Modal(feedbackModalEl, {
        backdrop: 'static',
        keyboard: true
      });
      // Small timeout to allow smooth scale-in spring animation
      setTimeout(() => {
        feedbackModal.show();
      }, 150);
    }

    // ==========================================================================
    // 11. TOP NAVIGATION PROGRESS BAR (PAGE TRANSITION LOADER)
    // ==========================================================================
    const topBar = document.getElementById('top-progress-bar');
    if (topBar) {
      document.querySelectorAll('a[href]').forEach(link => {
        link.addEventListener('click', function(e) {
          const href = this.getAttribute('href');
          if (
            !href ||
            href.startsWith('#') ||
            href.startsWith('javascript:') ||
            href.startsWith('tel:') ||
            href.startsWith('mailto:') ||
            this.target === '_blank' ||
            e.metaKey || e.ctrlKey || e.shiftKey
          ) {
            return;
          }

          try {
            const destUrl = new URL(this.href, window.location.origin);
            if (destUrl.origin === window.location.origin && destUrl.pathname !== window.location.pathname) {
              topBar.classList.add('is-active');
              topBar.style.width = '65%';
              setTimeout(() => {
                if (topBar.classList.contains('is-active')) {
                  topBar.style.width = '88%';
                }
              }, 250);
            }
          } catch (err) {}
        });
      });
    }

    // ==========================================================================
    // 12. FORM SUBMISSION LOADING STATE
    // ==========================================================================
    document.querySelectorAll('form').forEach(form => {
      form.addEventListener('submit', function(e) {
        if (form.checkValidity && !form.checkValidity()) {
          return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn && !submitBtn.classList.contains('is-submitting')) {
          submitBtn.classList.add('is-submitting');
          submitBtn.setAttribute('data-original-html', submitBtn.innerHTML);
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Securing & Submitting...';

          if (topBar) {
            topBar.classList.add('is-active');
            topBar.style.width = '80%';
          }

          // Safety reset after 10s if submission was interrupted
          setTimeout(() => {
            if (submitBtn.classList.contains('is-submitting')) {
              submitBtn.classList.remove('is-submitting');
              submitBtn.disabled = false;
              const origHtml = submitBtn.getAttribute('data-original-html');
              if (origHtml) submitBtn.innerHTML = origHtml;
            }
          }, 10000);
        }
      });
    });

    // ==========================================================================
    // 13. DARK & LIGHT THEME TOGGLE CONTROLLER
    // ==========================================================================
    const themeButtons = document.querySelectorAll('#themeToggleBtn, .mobile-theme-btn');

    function getCurrentTheme() {
      return document.documentElement.getAttribute('data-theme') || 'dark';
    }

    function applyTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      try {
        localStorage.setItem('innvetrix_theme', theme);
      } catch (err) {}

      themeButtons.forEach(btn => {
        const nextMode = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
        btn.setAttribute('title', `Switch to ${nextMode}`);
        btn.setAttribute('aria-label', `Switch to ${nextMode}`);
      });
    }

    // Initialize aria-labels for buttons
    const currentActiveTheme = getCurrentTheme();
    themeButtons.forEach(btn => {
      const nextMode = currentActiveTheme === 'dark' ? 'Light Mode' : 'Dark Mode';
      btn.setAttribute('title', `Switch to ${nextMode}`);
      btn.setAttribute('aria-label', `Switch to ${nextMode}`);
    });

    themeButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const nextTheme = getCurrentTheme() === 'dark' ? 'light' : 'dark';
        applyTheme(nextTheme);
      });
    });

  }

  // Focus helper for error modal CTA
  window.focusFirstFormError = function() {
    const errorField = document.querySelector('.text-danger, .is-invalid, [aria-invalid="true"]');
    if (errorField) {
      errorField.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const input = errorField.tagName === 'INPUT' || errorField.tagName === 'SELECT' || errorField.tagName === 'TEXTAREA' ? errorField : errorField.closest('.col-md-6, .col-12')?.querySelector('input, select, textarea');
      if (input) {
        setTimeout(() => input.focus(), 400);
      }
    } else {
      const form = document.querySelector('form');
      if (form) form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Initialize on DOM ready or immediately if already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initInnVetrix);
  } else {
    initInnVetrix();
  }

})();
