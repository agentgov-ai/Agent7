/* ============================================================
   AgentGov Product Landing Page — Polished
   Scroll-driven timeline, reveal animations, nav behavior,
   capability card interactions, stat count-up.
   All UI data is static — no backend API calls.
   ============================================================ */

(function () {
  "use strict";

  /* ----- Scroll Reveal via IntersectionObserver ----- */
  var revealObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("revealed");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1 }
  );

  document.querySelectorAll("[data-reveal]").forEach(function (el) {
    revealObserver.observe(el);
  });

  /* ----- Navigation: scroll shrink + active section highlighting ----- */
  var nav = document.getElementById("mainNav");
  var navLinks = document.querySelectorAll(".nav-links a:not(.nav-cta)");
  var sections = document.querySelectorAll(".section[id], .timeline-section[id], .hero-section[id], .cta-section[id]");

  function updateNav() {
    if (window.scrollY > 40) {
      nav.classList.add("scrolled");
    } else {
      nav.classList.remove("scrolled");
    }

    var current = "";
    sections.forEach(function (section) {
      var top = section.offsetTop - 140;
      if (window.scrollY >= top) {
        current = section.getAttribute("id");
      }
    });

    navLinks.forEach(function (link) {
      link.classList.remove("active");
      if (link.getAttribute("href") === "#" + current) {
        link.classList.add("active");
      }
    });
  }

  window.addEventListener("scroll", updateNav, { passive: true });
  updateNav();

  /* ----- Mobile hamburger toggle ----- */
  var hamburger = document.getElementById("navHamburger");
  var navLinksContainer = document.getElementById("navLinks");

  if (hamburger && navLinksContainer) {
    hamburger.addEventListener("click", function () {
      navLinksContainer.classList.toggle("open");
      hamburger.setAttribute(
        "aria-expanded",
        navLinksContainer.classList.contains("open")
      );
    });

    navLinksContainer.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        navLinksContainer.classList.remove("open");
      });
    });
  }

  /* ----- Smooth scroll for anchor links ----- */
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener("click", function (e) {
      var targetId = anchor.getAttribute("href");
      if (targetId === "#") return;
      var target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        if (history.pushState) {
          history.pushState(null, null, targetId);
        }
      }
    });
  });

  /* ----- Confidence fill bars: animate width on reveal ----- */
  document.querySelectorAll(".confidence-fill").forEach(function (bar) {
    var width = bar.style.width;
    bar.style.width = "0";

    var barObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            setTimeout(function () {
              bar.style.width = width;
            }, 300);
            barObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );
    barObserver.observe(bar);
  });

  /* ============================================================
     Scroll Timeline — the main interaction
     ============================================================ */
  var timelineTrack = document.getElementById("timelineTrack");
  var timelineProgress = document.getElementById("timelineProgress");
  var timelineSteps = document.querySelectorAll(".timeline-step");
  var stickyTitle = document.getElementById("stickyTitle");
  var stickyDesc = document.getElementById("stickyDesc");
  var stickyExample = document.getElementById("stickyExample");

  var stepData = [
    {
      title: "Scan backend code",
      desc: "Detect routes, model calls, tools, risky functions, and side-effectful actions across your entire codebase.",
      example: "Example: refund, invoice, email, delete, update, approve."
    },
    {
      title: "Suggest governed capabilities",
      desc: "Group thousands of functions into a small review queue. Show confidence, evidence, and suggested action type for each capability.",
      example: "Example: 43 capabilities from 1,248 files; 14,777 helpers ignored."
    },
    {
      title: "Review and approve ACAP",
      desc: "Teams approve, edit, or reject suggestions. Reviewed capabilities become authorization boundaries that the runtime enforces.",
      example: "Only human-confirmed decisions become policy."
    },
    {
      title: "Monitor runtime behavior",
      desc: "Middleware, model wrappers, callbacks, logs, and tool hooks capture what actually happened during live requests.",
      example: "Privacy-safe: no raw prompts or responses stored by default."
    },
    {
      title: "Detect findings and gaps",
      desc: "Compare observed behavior against approved ACAP. Highlight missing approvals, unknown actions, and uncovered routes.",
      example: "Example: refund_execute called without approval token."
    },
    {
      title: "Generate assessment evidence",
      desc: "Map findings to controls and frameworks with supporting traces. Produce remediation guidance tied to exact event IDs.",
      example: "Frameworks: NIST AI RMF, ISO 42001, OWASP Agentic Top 10."
    }
  ];

  function updateTimeline() {
    if (!timelineTrack || !timelineProgress || timelineSteps.length === 0) return;

    var trackRect = timelineTrack.getBoundingClientRect();
    var viewportMiddle = window.innerHeight * 0.5;

    var trackTop = trackRect.top;
    var trackHeight = trackRect.height;
    var scrolledInto = viewportMiddle - trackTop;
    var progress = Math.max(0, Math.min(1, scrolledInto / trackHeight));

    timelineProgress.style.height = (progress * trackHeight) + "px";

    var activeIndex = 0;
    timelineSteps.forEach(function (step, i) {
      var stepRect = step.getBoundingClientRect();
      var circleCenter = stepRect.top + 16;
      if (viewportMiddle >= circleCenter) {
        activeIndex = i;
      }
    });

    timelineSteps.forEach(function (step, i) {
      if (i <= activeIndex) {
        step.classList.add("active");
      } else {
        step.classList.remove("active");
      }
    });

    if (stickyTitle && stickyDesc && stickyExample && stepData[activeIndex]) {
      var d = stepData[activeIndex];
      stickyTitle.textContent = d.title;
      stickyDesc.textContent = d.desc;
      stickyExample.textContent = d.example;
    }
  }

  window.addEventListener("scroll", updateTimeline, { passive: true });
  window.addEventListener("resize", updateTimeline, { passive: true });
  setTimeout(updateTimeline, 100);

  /* ============================================================
     Capability card expand/collapse
     ============================================================ */
  document.querySelectorAll(".capability-header").forEach(function (header) {
    header.addEventListener("click", function () {
      header.closest(".capability-card").classList.toggle("expanded");
    });
  });

  /* ============================================================
     Capability card Approve / Edit / Reject
     Frontend-only state management
     ============================================================ */
  var capGrid = document.querySelector(".capability-cards-grid");

  function removeStatusBadge(card) {
    var existing = card.querySelector(".card-status-badge");
    if (existing) existing.remove();
  }

  function removeStatusText(card) {
    var existing = card.querySelector(".card-status-text");
    if (existing) existing.remove();
  }

  function addStatusText(card, text, color) {
    removeStatusText(card);
    var actions = card.querySelector(".capability-actions");
    if (!actions) return;
    var el = document.createElement("div");
    el.className = "card-status-text";
    el.style.color = color;
    el.textContent = text;
    actions.parentNode.insertBefore(el, actions.nextSibling);
  }

  function closeEditPanel(card) {
    var panel = card.querySelector(".card-edit-panel");
    if (panel) panel.remove();
    card.classList.remove("editing");
  }

  function openEditPanel(card) {
    if (card.classList.contains("editing")) {
      closeEditPanel(card);
      return;
    }

    // Read current values from the card
    var metaValues = card.querySelectorAll(".meta-value");
    var currentAction = metaValues[0] ? metaValues[0].textContent : "Write";
    var currentApproval = metaValues[1] ? metaValues[1].textContent : "Required";
    var currentData = metaValues[2] ? metaValues[2].textContent : "";

    var panel = document.createElement("div");
    panel.className = "card-edit-panel";
    panel.innerHTML =
      '<label>Action Type</label>' +
      '<select class="edit-action">' +
        '<option value="Read"' + (currentAction === "Read" ? ' selected' : '') + '>Read</option>' +
        '<option value="Write"' + (currentAction === "Write" ? ' selected' : '') + '>Write</option>' +
        '<option value="Delete"' + (currentAction === "Delete" ? ' selected' : '') + '>Delete</option>' +
        '<option value="Communicate"' + (currentAction === "Communicate" ? ' selected' : '') + '>Communicate</option>' +
      '</select>' +
      '<label>Approval Required</label>' +
      '<select class="edit-approval">' +
        '<option value="Required"' + (currentApproval === "Required" ? ' selected' : '') + '>Required</option>' +
        '<option value="Conditional"' + (currentApproval === "Conditional" ? ' selected' : '') + '>Conditional</option>' +
        '<option value="Not Required"' + (currentApproval === "Not Required" ? ' selected' : '') + '>Not Required</option>' +
      '</select>' +
      '<label>Data Classification</label>' +
      '<input type="text" class="edit-data" value="' + currentData.replace(/"/g, '&quot;') + '" />' +
      '<div class="edit-panel-actions">' +
        '<button class="btn btn-sm btn-approve edit-save">Save</button>' +
        '<button class="btn btn-sm btn-secondary edit-cancel">Cancel</button>' +
      '</div>';

    // Insert panel after capability-actions
    var actions = card.querySelector(".capability-actions");
    if (actions) {
      actions.parentNode.insertBefore(panel, actions.nextSibling);
    } else {
      card.querySelector(".capability-body").appendChild(panel);
    }

    card.classList.add("editing");

    // Save handler
    panel.querySelector(".edit-save").addEventListener("click", function (e) {
      e.stopPropagation();
      var newAction = panel.querySelector(".edit-action").value;
      var newApproval = panel.querySelector(".edit-approval").value;
      var newData = panel.querySelector(".edit-data").value;

      if (metaValues[0]) metaValues[0].textContent = newAction;
      if (metaValues[1]) metaValues[1].textContent = newApproval;
      if (metaValues[2]) metaValues[2].textContent = newData;

      closeEditPanel(card);
      addStatusText(card, "Changes saved", "var(--green-deep)");
    });

    // Cancel handler
    panel.querySelector(".edit-cancel").addEventListener("click", function (e) {
      e.stopPropagation();
      closeEditPanel(card);
    });
  }

  if (capGrid) {
    capGrid.addEventListener("click", function (e) {
      var btn = e.target.closest(".btn-approve, .btn-edit, .btn-reject");
      if (!btn) return;
      // Don't trigger if it's an edit panel button
      if (btn.classList.contains("edit-save") || btn.classList.contains("edit-cancel")) return;

      e.stopPropagation();
      var card = btn.closest(".capability-card");
      if (!card) return;

      // Approve
      if (btn.classList.contains("btn-approve")) {
        closeEditPanel(card);
        card.classList.remove("card-rejected");
        card.classList.add("card-approved");
        removeStatusBadge(card);
        var badge = document.createElement("span");
        badge.className = "badge badge-low card-status-badge";
        badge.textContent = "Approved";
        badge.style.marginLeft = "8px";
        card.querySelector(".capability-header").appendChild(badge);
        addStatusText(card, "Added to ACAP draft", "var(--green-deep)");
      }

      // Reject
      if (btn.classList.contains("btn-reject")) {
        closeEditPanel(card);
        card.classList.remove("card-approved");
        card.classList.add("card-rejected");
        removeStatusBadge(card);
        var rejBadge = document.createElement("span");
        rejBadge.className = "badge badge-high card-status-badge";
        rejBadge.textContent = "Rejected";
        rejBadge.style.marginLeft = "8px";
        card.querySelector(".capability-header").appendChild(rejBadge);
        addStatusText(card, "Excluded from ACAP", "var(--rose)");
      }

      // Edit
      if (btn.classList.contains("btn-edit")) {
        openEditPanel(card);
      }
    });
  }

  /* ============================================================
     Stat count-up animation
     ============================================================ */
  var statsSection = document.querySelector(".scanner-stats");
  if (statsSection) {
    var statObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animateCounters();
            statObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.3 }
    );
    statObserver.observe(statsSection);
  }

  function animateCounters() {
    var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    document.querySelectorAll(".scanner-stats .stat-value").forEach(function (el) {
      var raw = el.textContent.replace(/,/g, "");
      var target = parseInt(raw, 10);
      if (isNaN(target) || target === 0) return;
      if (prefersReduced) return;

      var duration = 1500;
      var start = performance.now();
      el.textContent = "0";

      function tick(now) {
        var elapsed = now - start;
        var progress = Math.min(elapsed / duration, 1);
        // Ease-out cubic
        var eased = 1 - Math.pow(1 - progress, 3);
        var current = Math.round(eased * target);
        el.textContent = current.toLocaleString();
        if (progress < 1) {
          requestAnimationFrame(tick);
        }
      }

      requestAnimationFrame(tick);
    });
  }

})();
