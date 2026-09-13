// InnVetrix Interactive SaaS Engine - Powered by Ultoxy Technologies
document.addEventListener('DOMContentLoaded', function() {
  
  // ==========================================================================
  // 1. STICKY NAVBAR TRANSITION
  // ==========================================================================
  const navbar = document.querySelector('.navbar-glass');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 25) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    });
  }

  // ==========================================================================
  // 2. SCROLL REVEAL ANIMATIONS (INTERSECTION OBSERVER)
  // ==========================================================================
  const revealElements = document.querySelectorAll('.reveal-on-scroll, .reveal-left, .reveal-right, .reveal-scale');
  
  if ('IntersectionObserver' in window && revealElements.length > 0) {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          observer.unobserve(entry.target); // Trigger once
        }
      });
    }, {
      threshold: 0.12,
      rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(el => revealObserver.observe(el));
  } else {
    // Fallback if IntersectionObserver not supported
    revealElements.forEach(el => el.classList.add('is-revealed'));
  }

  // ==========================================================================
  // 3. DYNAMIC NUMBER COUNTER ANIMATION ON SCROLL
  // ==========================================================================
  const counterElements = document.querySelectorAll('[data-counter-target]');
  
  function runCounterAnimation(el) {
    const target = parseFloat(el.getAttribute('data-counter-target'));
    const prefix = el.getAttribute('data-counter-prefix') || '';
    const suffix = el.getAttribute('data-counter-suffix') || '';
    const decimals = parseInt(el.getAttribute('data-counter-decimals') || '0', 10);
    const duration = 2000; // ms
    const startTime = performance.now();

    function updateCounter(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
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
    }, { threshold: 0.2 });

    counterElements.forEach(el => counterObserver.observe(el));
  }

  // ==========================================================================
  // 4. MOUSE-TRACKING SPOTLIGHT GLOW ON GLASS CARDS
  // ==========================================================================
  const glassCards = document.querySelectorAll('.glass-card');
  glassCards.forEach(card => {
    card.addEventListener('mousemove', function(e) {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      card.style.setProperty('--mouse-x', ${x}px);
      card.style.setProperty('--mouse-y', ${y}px);
    });
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
        // Annual billing (20% discount applied)
        starterPrice.textContent = '799';
        boutiquePrice.textContent = '1,999';
        if (starterPeriod) starterPeriod.textContent = '/ month, billed annually';
        if (boutiquePeriod) boutiquePeriod.textContent = '/ month, billed annually';
        if (billingAnnualLabel) billingAnnualLabel.classList.add('active');
        if (billingMonthlyLabel) billingMonthlyLabel.classList.remove('active');
      } else {
        // Monthly billing
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
  // 8. INTERACTIVE ROI SAVINGS CALCULATOR
  // ==========================================================================
  const roomSlider = document.getElementById('roiRoomsSlider');
  const rateSlider = document.getElementById('roiRateSlider');
  const roomDisplay = document.getElementById('roiRoomsVal');
  const rateDisplay = document.getElementById('roiRateVal');
  const savingsDisplay = document.getElementById('roiMonthlySavings');
  const annualSavingsDisplay = document.getElementById('roiAnnualSavings');

  function updateROI() {
    if (!roomSlider || !rateSlider || !savingsDisplay) return;
    
    const rooms = parseInt(roomSlider.value, 10);
    const rate = parseInt(rateSlider.value, 10);
    
    if (roomDisplay) roomDisplay.textContent = rooms;
    if (rateDisplay) rateDisplay.textContent = '₹' + rate.toLocaleString('en-IN');
    
    // Average 70% occupancy * 30 days
    const monthlyGrossRevenue = rooms * rate * 30 * 0.70;
    // Industry baseline 4.5% leakage prevented + Rs 4,000 saved in front-desk paperwork/errors
    const leakagePrevented = monthlyGrossRevenue * 0.045;
    const laborSaved = 4000;
    const totalMonthly = Math.round(leakagePrevented + laborSaved);
    const totalAnnual = totalMonthly * 12;

    savingsDisplay.textContent = '₹' + totalMonthly.toLocaleString('en-IN');
    if (annualSavingsDisplay) {
      annualSavingsDisplay.textContent = '₹' + totalAnnual.toLocaleString('en-IN');
    }
  }

  if (roomSlider && rateSlider) {
    roomSlider.addEventListener('input', updateROI);
    rateSlider.addEventListener('input', updateROI);
    updateROI(); // Initial run
  }

  // ==========================================================================
  // 9. AUTO-DISMISS ALERT MESSAGES
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

});
