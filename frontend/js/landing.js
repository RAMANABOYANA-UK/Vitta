/* ============================================================
   VITTA — Landing Page Interactions
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Mobile menu toggle ---------- */
  const toggleBtn = document.getElementById("mobileToggle");
  const mobileMenu = document.getElementById("mobileMenu");

  if (toggleBtn && mobileMenu) {
    toggleBtn.addEventListener("click", () => {
      const isOpen = mobileMenu.hidden === false;
      mobileMenu.hidden = isOpen;
      toggleBtn.setAttribute("aria-expanded", String(!isOpen));
      toggleBtn.innerHTML = isOpen
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    });

    // Close menu when a link is clicked
    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileMenu.hidden = true;
        toggleBtn.setAttribute("aria-expanded", "false");
        toggleBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
      });
    });
  }

  /* ---------- FAQ accordion ---------- */
  const faqItems = document.querySelectorAll(".faq-item");

  faqItems.forEach((item) => {
    const btn = item.querySelector(".faq-btn");
    const answer = item.querySelector(".faq-answer");

    btn.addEventListener("click", () => {
      const isOpen = item.classList.contains("open");

      // Close all
      faqItems.forEach((other) => {
        other.classList.remove("open");
        other.querySelector(".faq-btn").setAttribute("aria-expanded", "false");
        other.querySelector(".faq-answer").style.maxHeight = "0px";
      });

      // Toggle clicked
      if (!isOpen) {
        item.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
        answer.style.maxHeight = answer.scrollHeight + "px";
      }
    });
  });

  /* ---------- Reveal on scroll ---------- */
  const revealEls = document.querySelectorAll(".reveal");

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );

    revealEls.forEach((el) => observer.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("visible"));
  }

  /* ---------- Sticky navbar shadow on scroll ---------- */
  const navbar = document.querySelector(".navbar");

  const onScroll = () => {
    if (window.scrollY > 8) {
      navbar.style.boxShadow = "0 4px 20px rgba(15, 23, 42, 0.06)";
    } else {
      navbar.style.boxShadow = "none";
    }
  };

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();