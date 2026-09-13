// InnVetrix Interactive Engine - Powered by Ultoxy Technologies
document.addEventListener('DOMContentLoaded', function() {
  
  // 1. Sticky Navbar Transition
  const navbar = document.querySelector('.navbar-glass');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 30) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    });
  }

  // 2. Pricing Frequency Toggle (Monthly vs Annual)
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

  // 3. Interactive ROI Savings Calculator
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

  // 4. Quick Demo Modal Opener (if any)
  const demoButtons = document.querySelectorAll('.open-demo-trigger');
  demoButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      const demoModal = document.getElementById('demoInquiryModal');
      if (demoModal && window.bootstrap) {
        e.preventDefault();
        const modalInstance = new bootstrap.Modal(demoModal);
        modalInstance.show();
      }
    });
  });

  // 5. Auto dismiss alert messages after 7 seconds
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
