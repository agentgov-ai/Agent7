/* ============================================================
   AgentGov — static demo dashboard controller.

   Purpose-built for the public site. There is no backend:
     * no fetch(), no XHR, no WebSocket, no localhost
     * the only data source is window.AGENTGOV_DEMO (demo-data.js)
     * every action mutates in-memory state and re-renders

   Render pipeline and helper semantics intentionally mirror the real
   operational console so the demo behaves like the product.
   ============================================================ */

(function () {
  "use strict";

  var DEMO = window.AGENTGOV_DEMO;

  /* ============================ helpers ============================ */

  function byId(id) { return document.getElementById(id); }

  function clone(value) {
    return typeof window.structuredClone === "function"
      ? window.structuredClone(value)
      : JSON.parse(JSON.stringify(value));
  }

  function setText(id, value) {
    var node = byId(id);
    if (node) {
      node.textContent = (value === null || value === undefined || value === "")
        ? "—"
        : String(value);
    }
  }

  function clear(node) {
    while (node && node.firstChild) { node.removeChild(node.firstChild); }
  }

  function make(tag, className, textContent) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (textContent !== undefined && textContent !== null) {
      node.textContent = String(textContent);
    }
    return node;
  }

  function show(node, visible) {
    if (!node) { return; }
    node.classList.toggle("hidden", !visible);
  }

  /* Deterministic 12-hex digest used for demo finding ids.
     The real backend uses sha256; WebCrypto is async, so this is a
     synchronous FNV-1a stand-in. Same inputs always give the same id. */
  function digest12(input) {
    var h1 = 0x811c9dc5;
    var h2 = 0x01000193;
    for (var i = 0; i < input.length; i += 1) {
      var c = input.charCodeAt(i);
      h1 = (h1 ^ c) >>> 0;
      h1 = Math.imul(h1, 0x01000193) >>> 0;
      h2 = (h2 + Math.imul(c + i + 1, 0x85ebca6b)) >>> 0;
      h2 = (h2 ^ (h2 >>> 13)) >>> 0;
    }
    function hex(n, width) {
      var s = (n >>> 0).toString(16);
      while (s.length < width) { s = "0" + s; }
      return s.slice(-width);
    }
    return hex(h1, 8) + hex(h2, 4);
  }

  function findingId(ruleId, eventIds) {
    return "F-" + digest12(ruleId + "|" + eventIds.join(","));
  }

  function shortId(value) {
    if (!value) { return "—"; }
    var s = String(value);
    return s.length <= 20 ? s : s.slice(0, 8) + "…" + s.slice(-4);
  }

  function formatTime(value) {
    if (!value) { return "—"; }
    var d = new Date(value);
    if (isNaN(d.getTime())) { return String(value); }
    return d.toLocaleString();
  }

  function formatClock(value) {
    if (!value) { return "—"; }
    var d = new Date(value);
    if (isNaN(d.getTime())) { return String(value); }
    return d.toLocaleTimeString();
  }

  function titleize(value) {
    if (!value) { return "—"; }
    return String(value)
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (m) { return m.toUpperCase(); });
  }

  function pct(value) {
    if (value === null || value === undefined) { return "—"; }
    return Math.round(Number(value) * 100) + "%";
  }

  /* ---- badge class mappers (same vocabulary as the real console) ---- */

  function riskBadgeClass(risk) {
    if (risk === "high") { return "badge high"; }
    if (risk === "medium") { return "badge medium"; }
    if (risk === "low") { return "badge low"; }
    return "badge not-applicable";
  }

  function severityBadgeClass(severity) {
    if (severity === "high") { return "badge high"; }
    if (severity === "medium") { return "badge medium"; }
    return "badge not-applicable";
  }

  function coverageBadgeClass(status) {
    if (status === "captured" || status === "captured_with_annotation" || status === "captured_for_new_events") {
      return "badge low";
    }
    if (status === "partial") { return "badge medium"; }
    if (status === "annotation_required") { return "badge conditional"; }
    return "badge high";
  }

  function authBadgeClass(auth) {
    if (auth === "allowed") { return "badge allowed"; }
    if (auth === "allowed_with_approval" || auth === "allowed_conditional") { return "badge conditional"; }
    if (auth === "prohibited") { return "badge high"; }
    return "badge not-applicable";
  }

  function capStatusBadgeClass(status) {
    if (status === "approved_for_acap" || status === "edited") { return "badge allowed"; }
    if (status === "rejected") { return "badge high"; }
    if (status === "false_positive") { return "badge not-applicable"; }
    if (status === "needs_reapproval") { return "badge conditional"; }
    return "badge medium";
  }

  function frameworkStatusBadgeClass(status) {
    if (status === "passed") { return "badge allowed"; }
    if (status === "failed") { return "badge high"; }
    if (status === "needs_review") { return "badge medium"; }
    if (status === "informational") { return "badge informational"; }
    return "badge not-applicable";
  }

  function applicableBadgeClass(applicable) {
    if (applicable === true) { return "badge allowed"; }
    if (applicable === "informational") { return "badge informational"; }
    return "badge not-applicable";
  }

  function friendlyCapStatus(status) {
    var map = {
      pending: "Pending review",
      approved_for_acap: "Approved",
      rejected: "Denied",
      false_positive: "Not a capability",
      edited: "Approved (edited)",
      needs_reapproval: "Needs re-approval"
    };
    return map[status] || titleize(status);
  }

  var RULE_RECOMMENDATIONS = {
    R_ACAP_unapproved_observed:
      "Review this tool and add it to the capability inventory, then approve or deny it explicitly.",
    R_ACAP_denied_observed:
      "Investigate why a denied tool was invoked at runtime. Either remove the code path or revise the ACAP decision through review.",
    R_ACAP_approval_required_missing:
      "Implement a verified approval mechanism. A self-reported approval.granted flag is not trusted evidence — emit approval.verified from the approving system.",
    R_ACAP_data_class_mismatch:
      "Review and update the capability's allowed data classes, or stop passing the unexpected data class."
  };

  function whyItMatters(finding) {
    if (!finding) { return "—"; }
    var parts = [];
    if (finding.failed_control_title) {
      parts.push("This breaks the control “" + finding.failed_control_title + "”.");
    }
    if (finding.violates === "ACAP_authorization") {
      parts.push("The system acted outside the boundary a human approved, so its behavior is no longer covered by the authorization contract.");
    } else if (finding.violates === "ACAP_data_boundary") {
      parts.push("The system handled a data class outside the approved boundary.");
    }
    var mappings = finding.framework_mappings ? Object.keys(finding.framework_mappings).length : 0;
    if (mappings) {
      parts.push("It maps to " + mappings + " governance framework" + (mappings === 1 ? "" : "s") + " below.");
    }
    return parts.length ? parts.join(" ") : "—";
  }

  /* ============================ state ============================ */

  var state = {
    systemIndex: 0,
    data: null,
    activeTab: "overview",
    riskFilter: "all",
    selectedFindingId: null,
    rulesRunCount: 0,
    yamlVisible: false
  };

  function loadSystem(index) {
    state.systemIndex = index;
    state.data = clone(DEMO.systems[index]);
    state.riskFilter = "all";
    state.selectedFindingId = state.data.findings.length ? state.data.findings[0].finding_id : null;
    state.rulesRunCount = 0;
    state.yamlVisible = false;

    show(byId("yamlPanel"), false);
    var previewBtn = byId("btnPreviewYaml");
    if (previewBtn) { previewBtn.textContent = "Preview governance.yaml"; }
    var result = byId("runAcapResult");
    if (result) { result.textContent = ""; result.className = "wf-result"; }
    var filters = byId("riskFilters");
    if (filters) {
      Array.prototype.forEach.call(filters.querySelectorAll(".filter-btn"), function (btn) {
        btn.classList.toggle("active", btn.dataset.risk === "all");
      });
    }
  }

  function activeAcapVersion() {
    var versions = state.data.acap_versions;
    return (versions && versions.length) ? versions[0] : null;
  }

  /* ============================ rules engine ============================
     Faithful reimplementation of the two ACAP rules the product ships.
     See services/evidence_api/rules.py for the authoritative versions. */

  function approvalRequired(cap) {
    if (!cap) { return false; }
    if (typeof cap.approval_required === "boolean") { return cap.approval_required; }
    return Boolean(cap.suggested_approval_required);
  }

  /* approval.granted is self-reported and NOT trusted evidence. Only an
     explicit verification flag from the approving system counts. */
  function hasTrustedApproval(event) {
    var a = event && event.approval;
    if (!a) { return false; }
    return a.verified === true || a.trusted === true || a.token_verified === true;
  }

  function toolNameFromEvent(event) {
    if (event.tool && event.tool.name) { return event.tool.name; }
    if (event.component && event.component.kind === "tool") { return event.component.name; }
    return null;
  }

  function buildAcapLookup() {
    var allowed = {};
    var denied = {};
    state.data.discovery.capabilities.forEach(function (cap) {
      if (cap.review_status === "approved_for_acap" || cap.review_status === "edited") {
        allowed[cap.name] = cap;
      } else if (cap.review_status === "rejected") {
        denied[cap.name] = cap;
      }
    });
    return { allowed: allowed, denied: denied };
  }

  /* Control enrichment the live ACAP rules do not yet emit
     (run_all_acap_rules skips control_library.enrich_finding). Taken from
     the fixture so the Findings detail panel stays complete. */
  function demoEnrichment() {
    var found = null;
    DEMO.systems.forEach(function (sys) {
      if (found) { return; }
      var f = sys.findings && sys.findings[0];
      if (f && f.framework_mappings) {
        found = {
          failed_control: f.failed_control,
          failed_control_title: f.failed_control_title,
          framework_mappings: f.framework_mappings
        };
      }
    });
    return found || {};
  }

  function runAcapRulesLocally() {
    var version = activeAcapVersion();
    if (!version) { return { findings: [], evaluated: 0, version: null }; }

    var lookup = buildAcapLookup();
    var enrichment = demoEnrichment();
    var vid = version.acap_version_id;
    var vnum = version.version_number;
    var findings = [];
    var evaluated = 0;

    state.data.events.forEach(function (event) {
      if (event.event_type !== "tool_start") { return; }
      evaluated += 1;
      var name = toolNameFromEvent(event);
      if (!name) { return; }

      var eids = [event.event_id];
      var base = {
        acap_id: vid,
        acap_version_id: vid,
        acap_version_number: vnum,
        violates: "ACAP_authorization",
        severity: "high",
        session: event.session_id || null,
        event_ids: eids,
        trace_ids: [event.trace_id || ""]
      };

      if (lookup.denied[name]) {
        findings.push(Object.assign({}, base, enrichment, {
          finding_id: findingId("R_ACAP_denied_observed", eids),
          rule_id: "R_ACAP_denied_observed",
          capability_id: lookup.denied[name].capability_id,
          capability_name: name,
          description: "Tool '" + name + "' was observed at runtime but is explicitly denied in ACAP v" +
            vnum + " (" + vid + ")."
        }));
        return;
      }

      var cap = lookup.allowed[name];
      if (cap && approvalRequired(cap) && !hasTrustedApproval(event)) {
        findings.push(Object.assign({}, base, enrichment, {
          finding_id: findingId("R_ACAP_approval_required_missing", eids),
          rule_id: "R_ACAP_approval_required_missing",
          capability_id: cap.capability_id,
          capability_name: name,
          description: "Tool '" + name + "' requires approval per ACAP v" + vnum +
            ", but no trusted approval evidence was observed. approval.granted alone is not trusted."
        }));
      }
    });

    return { findings: findings, evaluated: evaluated, version: version };
  }

  /* ============================ governance.yaml ============================
     Mirrors _build_manifest_from_acap in services/evidence_api/app.py:907.
     Only approved capabilities are emitted; denied ones never appear. */

  function buildGovernanceYaml() {
    var version = activeAcapVersion();
    var lines = [];
    lines.push("system_id: " + state.data.system_id);
    lines.push("generated_from:");
    lines.push("  acap_version_id: " + (version ? version.acap_version_id : "null"));
    lines.push("  acap_version_number: " + (version ? version.version_number : "null"));
    lines.push("  generated_at: '" + new Date().toISOString() + "'");
    lines.push("  source: evidence_api");
    lines.push("capabilities:");

    var emitted = 0;
    state.data.discovery.capabilities.forEach(function (cap) {
      if (cap.review_status !== "approved_for_acap" && cap.review_status !== "edited") { return; }
      if (!cap.module_path) { return; }  // uninstrumentable, skipped upstream too
      emitted += 1;
      lines.push("- capability_id: " + cap.capability_id);
      lines.push("  name: " + cap.name);
      lines.push("  module_path: " + cap.module_path + "." + cap.name);
      lines.push("  action_type: " + (cap.suggested_action_type || "unknown"));
      lines.push("  status: approved");
      if (approvalRequired(cap)) {
        lines.push("  approval_required: true");
      }
      var classes = cap.suggested_data_classes || [];
      if (classes.length) {
        lines.push("  data_classes:");
        classes.forEach(function (dc) { lines.push("  - " + dc); });
      }
      if (cap.external_side_effect) {
        lines.push("  external_side_effect: true");
      }
    });

    if (!emitted) {
      lines.push("# No approved capabilities yet. Approve at least one capability");
      lines.push("# in Capability Discovery, then regenerate the ACAP version.");
    }
    return lines.join("\n") + "\n";
  }

  /* ============================ renderers ============================ */

  function renderSystemSelector() {
    var select = byId("systemSelector");
    if (!select || select.options.length) { return; }
    DEMO.systems.forEach(function (sys, i) {
      var opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = sys.system_id;
      select.appendChild(opt);
    });
    select.value = String(state.systemIndex);
  }

  function renderKpis() {
    var d = state.data;
    var findings = d.findings;
    var controls = {};
    findings.forEach(function (f) { if (f.failed_control) { controls[f.failed_control] = true; } });
    var controlCount = Object.keys(controls).length;

    var status = findings.some(function (f) { return f.severity === "high"; })
      ? "Requires Remediation"
      : (findings.length ? "Needs Review" : "Satisfactory");

    setText("kpiStatus", status);
    setText("kpiRisk", titleize(d.risk_profile.data_sensitivity) + " sensitivity");
    setText("kpiEvents", d.events.length);
    setText("kpiFindings", findings.length);
    setText("kpiControls", controlCount);
    setText("kpiConfidence", titleize(d.assessment.evidence_confidence));

    var statusCard = byId("kpiStatusCard");
    if (statusCard) {
      statusCard.className = "kpi-card " + (findings.length ? "accent-danger" : "accent-ok");
    }
    var findingsCard = byId("kpiFindingsCard");
    if (findingsCard) {
      findingsCard.className = "kpi-card " + (findings.length ? "accent-danger" : "accent-ok");
    }
    var controlsCard = byId("kpiControlsCard");
    if (controlsCard) {
      controlsCard.className = "kpi-card " + (controlCount ? "accent-danger" : "accent-ok");
    }
    var confidenceCard = byId("kpiConfidenceCard");
    if (confidenceCard) {
      confidenceCard.className = "kpi-card " +
        (d.assessment.evidence_confidence === "high" ? "accent-ok" : "accent-warning");
    }
  }

  function renderSystem() {
    var s = state.data.system;
    setText("systemId", s.system_id);
    setText("systemDeployment", s.deployment_id);
    setText("systemEnvironment", s.environment);
    setText("systemOwner", s.owner);
    setText("systemPurpose", s.purpose);

    var acap = state.data.acap;
    setText("acapId", acap.acap_id);
    setText("acapReview", titleize(acap.status) + " by " + acap.reviewed_by + " · " + formatTime(acap.reviewed_at));
    setText("acapApprovalTools", acap.approval_required_tools.length ? acap.approval_required_tools.join(", ") : "none");
    setText("acapProhibitedCount", acap.prohibited_action_count);

    var badge = byId("acapStatus");
    if (badge) {
      badge.textContent = titleize(acap.status);
      badge.className = "badge allowed";
    }
  }

  function renderAuditStatus() {
    var a = state.data.audit_status;
    var badge = byId("auditStatusBadge");
    if (badge) {
      badge.textContent = titleize(a.status);
      badge.className = a.status === "up_to_date" ? "badge allowed" : "badge medium";
    }
    setText("auditNextAction", a.next_action);
  }

  function renderWorkflow() {
    var d = state.data;
    var reviewed = d.discovery.capabilities.some(function (c) {
      return c.review_status && c.review_status !== "pending";
    });
    var steps = [
      ["wfScan", Boolean(d.discovery && d.discovery.capabilities.length)],
      ["wfReview", reviewed],
      ["wfAcap", Boolean(d.acap_versions && d.acap_versions.length)],
      ["wfRules", state.rulesRunCount > 0 || d.findings.length > 0],
      ["wfFindings", d.findings.length > 0]
    ];
    steps.forEach(function (pair) {
      var node = byId(pair[0]);
      if (node) { node.classList.toggle("done", Boolean(pair[1])); }
    });
  }

  /* ---------------------------- discovery ---------------------------- */

  function capabilityMatchesFilter(cap) {
    var f = state.riskFilter;
    if (f === "all") { return true; }
    if (f === "pending") { return cap.review_status === "pending"; }
    if (f === "reviewed") { return Boolean(cap.review_status) && cap.review_status !== "pending"; }
    return cap.risk === f;
  }

  function renderCapabilityCard(cap) {
    var card = make("div", "capability-card risk-" + (cap.risk || "low"));

    var header = make("div", "cap-header");
    header.appendChild(make("span", "cap-name", cap.name));
    header.appendChild(make("span", riskBadgeClass(cap.risk), cap.risk || "unknown"));
    header.appendChild(make("span", "badge not-applicable",
      cap.confidence_source + " (" + cap.confidence + ")"));
    header.appendChild(make("span", capStatusBadgeClass(cap.review_status),
      friendlyCapStatus(cap.review_status)));
    card.appendChild(header);

    var meta = make("div", "cap-meta");
    meta.appendChild(make("span", "mono", cap.file_path + ":" + cap.line_start + "-" + cap.line_end));
    meta.appendChild(make("span", null, "module: " + cap.module_path));
    meta.appendChild(make("span", null, "action: " + (cap.suggested_action_type || "unknown")));
    meta.appendChild(make("span", null, "data: " +
      ((cap.suggested_data_classes && cap.suggested_data_classes.length)
        ? cap.suggested_data_classes.join(", ")
        : "none")));
    meta.appendChild(make("span", null, "approval: " + (approvalRequired(cap) ? "required" : "not required")));
    meta.appendChild(make("span", null, "side effect: " + (cap.external_side_effect ? "external" : "internal")));
    card.appendChild(meta);

    if (cap.evidence && cap.evidence.length) {
      var evWrap = make("div", "cap-evidence");
      var ul = make("ul");
      cap.evidence.forEach(function (ev) {
        ul.appendChild(make("li", null, ev.type + ": " + ev.detail + " (line " + ev.line + ")"));
      });
      evWrap.appendChild(ul);
      card.appendChild(evWrap);
    }

    if (cap.call_chain && cap.call_chain.length) {
      card.appendChild(make("div", "cap-call-chain mono", cap.call_chain.join(" | ")));
    }

    var actions = make("div", "cap-actions");
    [
      ["btn-approve", "Approve", "approve"],
      ["btn-edit", "Edit", "edit"],
      ["btn-reject", "Reject", "reject"],
      ["btn-false-positive", "Not a Capability", "not-a-capability"]
    ].forEach(function (spec) {
      var btn = make("button", spec[0], spec[1]);
      btn.type = "button";
      btn.dataset.capId = cap.capability_id;
      btn.dataset.action = spec[2];
      actions.appendChild(btn);
    });
    card.appendChild(actions);

    var statusRow;
    if (cap.review_status === "approved_for_acap" || cap.review_status === "edited") {
      statusRow = make("div", "cap-status-row", "Included in the next ACAP version.");
    } else if (cap.review_status === "rejected") {
      statusRow = make("div", "cap-status-row is-negative",
        "Denied. Runtime use of this tool will raise a finding.");
    } else if (cap.review_status === "false_positive") {
      statusRow = make("div", "cap-status-row is-neutral",
        "Excluded from the capability inventory.");
    } else if (cap.review_status === "needs_reapproval") {
      statusRow = make("div", "cap-status-row is-negative",
        "Changed since approval. Re-review before regenerating the ACAP.");
    } else {
      statusRow = make("div", "cap-status-row is-neutral",
        "Awaiting human decision. Scanner suggestions are not authorization.");
    }
    card.appendChild(statusRow);

    return card;
  }

  function renderDiscovery() {
    var d = state.data.discovery;
    var sum = d.scan_summary;

    setText("scanUploadId", d.upload_id);
    setText("scanFilesScanned", sum.files_scanned);
    setText("scanFunctionsSeen", sum.functions_seen);
    setText("scanCandidatesFound", sum.candidates_found);
    setText("scanModelSurface", sum.model_surface_found);
    setText("scanHighRisk", sum.high_risk_count);
    setText("scanMediumRisk", sum.medium_risk_count);
    setText("scanLowRisk", sum.low_risk_count);
    setText("scanIgnored", sum.ignored_helpers_count);
    setText("scanCollapseNote", sum.functions_seen + " functions into " + sum.candidates_found);

    var container = byId("capabilityCards");
    clear(container);
    var visible = d.capabilities.filter(capabilityMatchesFilter);
    if (!visible.length) {
      container.appendChild(make("div", "card empty", "No capabilities match this filter."));
    } else {
      visible.forEach(function (cap) { container.appendChild(renderCapabilityCard(cap)); });
    }

    var body = byId("modelSurfaceBody");
    clear(body);
    (d.model_surface || []).forEach(function (m) {
      var tr = make("tr");
      tr.appendChild(make("td", "mono", m.name));
      tr.appendChild(make("td", null, m.provider));
      tr.appendChild(make("td", "mono", m.file_path));
      tr.appendChild(make("td", null, m.line));
      tr.appendChild(make("td", "mono", (m.call_chain || []).join(" | ")));
      body.appendChild(tr);
    });
  }

  /* ---------------------------- ACAP ---------------------------- */

  function renderAcap() {
    var caps = state.data.discovery.capabilities;
    var approved = caps.filter(function (c) {
      return c.review_status === "approved_for_acap" || c.review_status === "edited";
    });
    var denied = caps.filter(function (c) { return c.review_status === "rejected"; });
    var pending = caps.filter(function (c) {
      return c.review_status === "pending" || c.review_status === "needs_reapproval";
    });
    var fp = caps.filter(function (c) { return c.review_status === "false_positive"; });

    setText("previewApproved", approved.length);
    setText("previewDenied", denied.length);
    setText("previewPending", pending.length);
    setText("previewFP", fp.length);

    var warning = byId("acapPreviewWarning");
    if (warning) {
      if (pending.length) {
        warning.textContent = pending.length + " capabilit" + (pending.length === 1 ? "y" : "ies") +
          " still awaiting review. They are excluded from the ACAP until a human decides.";
        show(warning, true);
      } else {
        show(warning, false);
      }
    }

    function fillList(containerId, heading, items) {
      var container = byId(containerId);
      clear(container);
      if (!items.length) { return; }
      container.appendChild(make("h4", "preview-subhead", heading));
      var ul = make("ul", "preview-list");
      items.forEach(function (c) {
        ul.appendChild(make("li", "mono", c.name + (approvalRequired(c) ? "  (approval required)" : "")));
      });
      container.appendChild(ul);
    }
    fillList("acapPreviewAllowed", "Allowed capabilities", approved);
    fillList("acapPreviewDeniedList", "Denied capabilities", denied);

    /* version history */
    var list = byId("acapVersionsList");
    clear(list);
    var versions = state.data.acap_versions || [];
    if (!versions.length) {
      list.appendChild(make("div", "empty",
        "No ACAP version yet. Generate one to create an authorization boundary."));
    } else {
      versions.forEach(function (v, i) {
        var row = make("div", "acap-version-card");
        row.appendChild(make("span", "badge allowed", "v" + v.version_number));
        row.appendChild(make("span", "mono", v.acap_version_id));
        row.appendChild(make("span", "muted",
          formatTime(v.generated_at) + (i === 0 ? " · active" : "")));
        var dl = make("button", "btn-download", "governance.yaml");
        dl.type = "button";
        row.appendChild(dl);
        list.appendChild(row);
      });
    }

    var runBtn = byId("btnRunAcapRules");
    if (runBtn) { runBtn.disabled = !versions.length; }
    show(byId("runAcapHint"), !versions.length);

    /* tool authorization table, derived from current review state */
    var body = byId("toolReviewBody");
    clear(body);
    var observedCount = {};
    state.data.events.forEach(function (e) {
      if (e.event_type !== "tool_start") { return; }
      var n = toolNameFromEvent(e);
      if (n) { observedCount[n] = (observedCount[n] || 0) + 1; }
    });

    caps.forEach(function (cap) {
      var auth;
      if (cap.review_status === "approved_for_acap" || cap.review_status === "edited") {
        auth = approvalRequired(cap) ? "allowed_with_approval" : "allowed";
      } else if (cap.review_status === "rejected") {
        auth = "prohibited";
      } else if (cap.review_status === "false_positive") {
        auth = "not_a_capability";
      } else {
        auth = "unresolved";
      }
      var tr = make("tr");
      tr.appendChild(make("td", "mono", cap.name));
      tr.appendChild(make("td", null, cap.suggested_action_type || "unknown"));
      tr.appendChild(make("td", null, approvalRequired(cap) ? "required" : "—"));
      tr.appendChild(make("td", null, observedCount[cap.name] || 0));
      var authTd = make("td");
      authTd.appendChild(make("span", authBadgeClass(auth), titleize(auth)));
      tr.appendChild(authTd);
      body.appendChild(tr);
    });

    var draftBadge = byId("draftStatus");
    if (draftBadge) {
      draftBadge.textContent = pending.length ? pending.length + " unresolved" : "fully reviewed";
      draftBadge.className = pending.length ? "badge medium" : "badge allowed";
    }

    if (state.yamlVisible) {
      var out = byId("yamlOutput");
      if (out) { out.textContent = buildGovernanceYaml(); }
    }
  }

  /* ---------------------------- evidence ---------------------------- */

  function flaggedEventIds() {
    var ids = {};
    state.data.findings.forEach(function (f) {
      (f.event_ids || []).forEach(function (id) { ids[id] = true; });
    });
    return ids;
  }

  function renderEvidence() {
    var d = state.data;
    var flagged = flaggedEventIds();

    var streamCount = byId("eventStreamCount");
    if (streamCount) { streamCount.textContent = d.events.length + " events"; }

    var body = byId("eventStreamBody");
    clear(body);
    d.events.forEach(function (e) {
      var tr = make("tr");
      if (flagged[e.event_id]) { tr.className = "event-row-flagged"; }
      tr.appendChild(make("td", "mono", formatClock(e.timestamp)));
      tr.appendChild(make("td", "mono", e.event_type));
      tr.appendChild(make("td", null, e.component ? e.component.name : "—"));

      var action = "—";
      if (e.tool && e.tool.action_type) {
        action = e.tool.action_type;
      } else if (e.model && e.model.provider) {
        action = e.model.provider + " / " + e.model.name;
      }
      tr.appendChild(make("td", null, action));

      var approvalText = "—";
      if (e.approval && e.approval.required) {
        approvalText = hasTrustedApproval(e)
          ? "verified"
          : (e.approval.granted ? "claimed, unverified" : "required, absent");
      } else if (e.approval && e.approval.required === false) {
        approvalText = "not required";
      }
      var approvalTd = make("td");
      if (approvalText === "claimed, unverified" || approvalText === "required, absent") {
        approvalTd.appendChild(make("span", "badge high", approvalText));
      } else {
        approvalTd.textContent = approvalText;
      }
      tr.appendChild(approvalTd);

      var outcomeTd = make("td");
      var status = e.outcome ? e.outcome.status : "unknown";
      var cls = status === "error"
        ? "badge high"
        : (status === "success" ? "badge allowed" : "badge not-applicable");
      outcomeTd.appendChild(make("span", cls,
        status + (e.outcome && e.outcome.error_type ? ": " + e.outcome.error_type : "")));
      tr.appendChild(outcomeTd);

      tr.appendChild(make("td", "mono", shortId(e.event_id)));
      body.appendChild(tr);
    });

    var covCount = byId("coverageEventCount");
    if (covCount) { covCount.textContent = d.coverage.event_count + " events"; }

    var covBody = byId("coverageBody");
    clear(covBody);
    d.coverage.fields.forEach(function (row) {
      var tr = make("tr");
      tr.appendChild(make("td", null, row.field));
      var statusTd = make("td");
      statusTd.appendChild(make("span", coverageBadgeClass(row.status), titleize(row.status)));
      tr.appendChild(statusTd);
      tr.appendChild(make("td", null, pct(row.presence)));
      tr.appendChild(make("td", "muted", row.note || "—"));
      covBody.appendChild(tr);
    });
  }

  /* ---------------------------- findings ---------------------------- */

  function selectedFinding() {
    var findings = state.data.findings;
    if (!findings.length) { return null; }
    for (var i = 0; i < findings.length; i += 1) {
      if (findings[i].finding_id === state.selectedFindingId) { return findings[i]; }
    }
    return findings[0];
  }

  function renderFindingsList() {
    var container = byId("findingsList");
    clear(container);
    var findings = state.data.findings;
    if (!findings.length) {
      container.appendChild(make("div", "empty",
        "No findings. Run ACAP rules to evaluate runtime evidence."));
      return;
    }
    var current = selectedFinding();
    findings.forEach(function (f) {
      var isActive = current && f.finding_id === current.finding_id;
      var btn = make("button", "finding-button" + (isActive ? " active" : ""));
      btn.type = "button";
      btn.dataset.findingId = f.finding_id;

      var title = make("div", "finding-title");
      title.appendChild(make("span", "mono", f.finding_id));
      title.appendChild(make("span", severityBadgeClass(f.severity), f.severity));
      if (f.acap_version_id) {
        title.appendChild(make("span", "badge acap-violation", "ACAP"));
      }
      btn.appendChild(title);
      btn.appendChild(make("div", "finding-meta",
        f.rule_id + " · " + (f.capability_name || f.session || "")));
      container.appendChild(btn);
    });
  }

  function renderFindingDetail() {
    var f = selectedFinding();
    var head = byId("detailPanelHead");
    var badge = byId("severityBadge");

    if (!f) {
      setText("detailTitle", "No finding selected");
      if (badge) { badge.textContent = "—"; badge.className = "badge"; }
      if (head) { head.className = "card-head"; }
      ["detailRule", "detailSession", "detailAcap", "detailOutcome",
        "detailDescription", "detailWhyMatters", "detailRecommendation",
        "detailControlId", "detailControlTitle"].forEach(function (id) { setText(id, null); });
      clear(byId("frameworkMappings"));
      clear(byId("eventIds"));
      clear(byId("timeline"));
      show(byId("controlSection"), false);
      show(byId("frameworkSection"), false);
      return;
    }

    state.selectedFindingId = f.finding_id;

    setText("detailTitle", f.capability_name ? f.capability_name : f.finding_id);
    if (badge) {
      badge.textContent = f.severity;
      badge.className = severityBadgeClass(f.severity);
    }
    if (head) {
      head.className = "card-head" + (f.severity === "high" ? " sev-high" : "");
    }

    setText("detailRule", f.rule_id);
    setText("detailSession", shortId(f.session));
    setText("detailAcap", f.acap_version_id
      ? f.acap_version_id + " (v" + f.acap_version_number + ")"
      : (f.acap_id || null));
    setText("detailOutcome", f.capability_name
      ? f.capability_name + " (runtime observed)"
      : (f.outcome_status || null));

    setText("detailDescription", f.description);
    setText("detailWhyMatters", whyItMatters(f));
    setText("detailRecommendation",
      RULE_RECOMMENDATIONS[f.rule_id] || "Review this finding with the system owner.");

    var hasControl = Boolean(f.failed_control);
    show(byId("controlSection"), hasControl);
    if (hasControl) {
      setText("detailControlId", f.failed_control);
      setText("detailControlTitle", f.failed_control_title);
    }

    var fwWrap = byId("frameworkMappings");
    clear(fwWrap);
    var mappings = f.framework_mappings || {};
    var keys = Object.keys(mappings);
    show(byId("frameworkSection"), keys.length > 0);
    var labels = {
      ACAP: "ACAP",
      NIST_AI_RMF: "NIST AI RMF",
      EU_AI_Act: "EU AI Act",
      ISO_42001: "ISO/IEC 42001"
    };
    keys.forEach(function (key) {
      var card = make("div", "framework-card");
      card.appendChild(make("h4", null, labels[key] || key.replace(/_/g, " ")));
      var detail = mappings[key] || {};
      Object.keys(detail).forEach(function (field) {
        if (field === "note") { return; }
        var row = make("div", "fw-row");
        row.appendChild(make("span", "muted", titleize(field) + ": "));
        row.appendChild(make("span", null, String(detail[field])));
        card.appendChild(row);
      });
      if (detail.note) {
        card.appendChild(make("p", "disclaimer", detail.note));
      }
      fwWrap.appendChild(card);
    });

    var idWrap = byId("eventIds");
    clear(idWrap);
    (f.event_ids || []).forEach(function (id) {
      idWrap.appendChild(make("span", "id-chip mono", id));
    });

    /* Timeline: the trace this finding came from, with cited events marked. */
    var tl = byId("timeline");
    clear(tl);
    var traceId = (f.trace_ids && f.trace_ids[0]) || null;
    var linked = {};
    (f.event_ids || []).forEach(function (id) { linked[id] = true; });
    var traceEvents = state.data.events.filter(function (e) {
      return !traceId || e.trace_id === traceId;
    });
    if (!traceEvents.length) {
      tl.appendChild(make("li", "empty", "No trace events available."));
    }
    traceEvents.forEach(function (e) {
      var li = make("li", "timeline-item" + (linked[e.event_id] ? " linked" : ""));
      li.appendChild(make("span", "timeline-time", formatClock(e.timestamp)));
      var main = make("div", "timeline-main");
      main.appendChild(make("span", "timeline-kind", e.event_type));
      main.appendChild(make("span", "timeline-sub",
        (e.component ? e.component.name : "") +
        (e.outcome && e.outcome.status ? " · " + e.outcome.status : "")));
      li.appendChild(main);
      li.appendChild(make("span", "timeline-id mono", shortId(e.event_id)));
      tl.appendChild(li);
    });
  }

  /* ---------------------------- assessment ---------------------------- */

  function renderAssessment() {
    var a = state.data.assessment;
    var badge = byId("overallStatusBadge");
    if (badge) {
      badge.textContent = titleize(a.overall_status);
      badge.className = a.overall_status === "satisfactory"
        ? "badge allowed"
        : (a.overall_status === "needs_review" ? "badge medium" : "badge high");
    }
    setText("assessmentId", a.assessment_id);
    setText("assessmentTime", formatTime(a.assessed_at));
    setText("assessmentConfidence", titleize(a.evidence_confidence));
    setText("assessmentControls", a.findings_summary.failed_controls.length
      ? a.findings_summary.failed_controls.join(", ")
      : "none");

    var body = byId("frameworkStatusBody");
    clear(body);
    a.framework_status.forEach(function (row) {
      var tr = make("tr");
      tr.appendChild(make("td", null, row.framework));
      var td = make("td");
      td.appendChild(make("span", frameworkStatusBadgeClass(row.status), titleize(row.status)));
      tr.appendChild(td);
      body.appendChild(tr);
    });

    var actions = byId("recommendedActions");
    clear(actions);
    a.recommended_next_actions.forEach(function (text) {
      actions.appendChild(make("li", null, text));
    });
    /* Assessment snapshots are frozen in the real product too; say so when stale. */
    if (state.data.findings.length !== a.findings_summary.total) {
      actions.appendChild(make("li", null,
        "This assessment snapshot is stale: " + state.data.findings.length +
        " finding(s) now exist versus " + a.findings_summary.total +
        " at assessment time. Run a new assessment in the operational console."));
    }

    var r = state.data.risk_profile;
    setText("riskUseCase", r.use_case);
    setText("riskEnvironment", r.environment);
    setText("riskAuthority", titleize(r.authority_level));
    setText("riskAutonomy", titleize(r.autonomy_level));
    setText("riskDataSensitivity", titleize(r.data_sensitivity));
    setText("riskSideEffects", r.external_side_effects ? "Yes — external systems are affected" : "No");
    setText("riskApprovalModel", titleize(r.human_approval_model));
    setText("riskJurisdiction", r.jurisdiction);

    var appBody = byId("applicabilityBody");
    clear(appBody);
    state.data.framework_applicability.forEach(function (row) {
      var tr = make("tr");
      tr.appendChild(make("td", null, row.framework));
      var td = make("td");
      var label = row.applicable === true
        ? "Yes"
        : (row.applicable === false ? "No" : titleize(row.applicable));
      td.appendChild(make("span", applicableBadgeClass(row.applicable), label));
      tr.appendChild(td);
      tr.appendChild(make("td", "muted", row.reason));
      appBody.appendChild(tr);
    });
  }

  /* ---------------------------- master render ---------------------------- */

  function render() {
    renderKpis();
    renderSystem();
    renderAuditStatus();
    renderWorkflow();
    renderDiscovery();
    renderAcap();
    renderEvidence();
    renderFindingsList();
    renderFindingDetail();
    renderAssessment();
  }

  /* ============================ actions ============================ */

  function switchTab(tab) {
    state.activeTab = tab;
    Array.prototype.forEach.call(document.querySelectorAll(".tab-panel"), function (panel) {
      panel.classList.toggle("active", panel.id === "tab-" + tab);
    });
    Array.prototype.forEach.call(document.querySelectorAll(".nav-item"), function (btn) {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    closeSidebar();
  }

  function findCapability(capId) {
    var caps = state.data.discovery.capabilities;
    for (var i = 0; i < caps.length; i += 1) {
      if (caps[i].capability_id === capId) { return caps[i]; }
    }
    return null;
  }

  function markAcapStale(message) {
    state.data.audit_status.status = "scan_changed_since_acap";
    state.data.audit_status.next_action = message;
  }

  function reviewCapability(capId, action) {
    var cap = findCapability(capId);
    if (!cap) { return; }
    if (action === "approve") { cap.review_status = "approved_for_acap"; }
    else if (action === "reject") { cap.review_status = "rejected"; }
    else if (action === "not-a-capability") { cap.review_status = "false_positive"; }
    markAcapStale("Review decisions changed since the active ACAP version. Regenerate the ACAP version, then re-run the rules.");
    render();
  }

  function openEditModal(capId) {
    var cap = findCapability(capId);
    if (!cap) { return; }
    byId("editCapId").value = cap.capability_id;
    byId("editActionType").value = "";
    byId("editRisk").value = "";
    byId("editDataClasses").value = (cap.suggested_data_classes || []).join(", ");
    byId("editApprovalRequired").checked = approvalRequired(cap);
    byId("editSideEffect").checked = Boolean(cap.external_side_effect);
    byId("editCapabilityModal").classList.remove("hidden");
  }

  function closeEditModal() {
    byId("editCapabilityModal").classList.add("hidden");
  }

  function submitEdit(event) {
    event.preventDefault();
    var cap = findCapability(byId("editCapId").value);
    if (!cap) { closeEditModal(); return; }

    var actionType = byId("editActionType").value;
    var risk = byId("editRisk").value;
    var classes = byId("editDataClasses").value
      .split(",")
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });

    if (actionType) { cap.suggested_action_type = actionType; }
    if (risk) { cap.risk = risk; }
    cap.suggested_data_classes = classes;
    cap.approval_required = byId("editApprovalRequired").checked;
    cap.suggested_approval_required = cap.approval_required;
    cap.external_side_effect = byId("editSideEffect").checked;
    cap.review_status = "edited";

    closeEditModal();
    markAcapStale("A capability was edited after the active ACAP version. Regenerate the ACAP version, then re-run the rules.");
    render();
  }

  function generateAcapVersion() {
    var versions = state.data.acap_versions;
    var next = (versions.length ? versions[0].version_number : 0) + 1;
    var now = new Date().toISOString();

    versions.unshift({
      acap_version_id: "ACAP-" + state.data.system_id + "-v" + next,
      version_number: next,
      generated_at: now
    });

    var approved = state.data.discovery.capabilities.filter(function (c) {
      return c.review_status === "approved_for_acap" || c.review_status === "edited";
    });
    state.data.acap.approval_required_tools = approved
      .filter(approvalRequired)
      .map(function (c) { return c.name; });
    state.data.acap.prohibited_action_count = state.data.discovery.capabilities.filter(function (c) {
      return c.review_status === "rejected";
    }).length;
    state.data.acap.reviewed_at = now;

    state.data.audit_status.active_acap_version = next;
    state.data.audit_status.acap_generated_at = now;
    state.data.audit_status.status = "runtime_changed_since_assessment";
    state.data.audit_status.next_action =
      "ACAP v" + next + " is now active. Run ACAP rules to evaluate runtime evidence against it.";

    var result = byId("runAcapResult");
    if (result) {
      result.className = "wf-result wf-success";
      result.textContent = "Generated ACAP v" + next + " with " + approved.length +
        " allowed and " + state.data.acap.prohibited_action_count + " denied capabilities.";
    }
    render();
  }

  function runAcapRules() {
    var btn = byId("btnRunAcapRules");
    var result = byId("runAcapResult");
    if (!btn || btn.disabled) { return; }

    var original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Running…";

    /* Brief delay so the running state is visible. No network involved. */
    window.setTimeout(function () {
      var outcome = runAcapRulesLocally();
      state.data.findings = outcome.findings;
      state.rulesRunCount += 1;
      state.selectedFindingId = outcome.findings.length ? outcome.findings[0].finding_id : null;

      if (outcome.findings.length) {
        state.data.audit_status.status = "runtime_changed_since_assessment";
        state.data.audit_status.next_action = outcome.findings.length +
          " finding(s) detected against ACAP v" + outcome.version.version_number +
          ". Review the findings and run a new assessment.";
      } else {
        state.data.audit_status.status = "up_to_date";
        state.data.audit_status.next_action = "No findings against ACAP v" +
          outcome.version.version_number +
          ". Runtime behavior is inside the approved boundary.";
      }

      btn.textContent = original;
      btn.disabled = false;

      if (result) {
        result.className = "wf-result " + (outcome.findings.length ? "wf-error" : "wf-success");
        result.textContent = outcome.findings.length + " finding" +
          (outcome.findings.length === 1 ? "" : "s") + " from " + outcome.evaluated +
          " tool events (ACAP v" + outcome.version.version_number + ")";
      }
      render();
    }, 450);
  }

  function togglePreviewYaml() {
    state.yamlVisible = !state.yamlVisible;
    var panel = byId("yamlPanel");
    show(panel, state.yamlVisible);
    byId("btnPreviewYaml").textContent = state.yamlVisible
      ? "Hide governance.yaml"
      : "Preview governance.yaml";
    if (state.yamlVisible) {
      byId("yamlOutput").textContent = buildGovernanceYaml();
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function downloadYaml() {
    var blob = new Blob([buildGovernanceYaml()], { type: "text/yaml;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "governance.yaml";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  /* ---------------------------- sidebar (mobile) ---------------------------- */

  function openSidebar() {
    byId("dashboardSidebar").classList.add("open");
    byId("sidebarToggle").setAttribute("aria-expanded", "true");
    var scrim = byId("sidebarScrim");
    scrim.hidden = false;
    scrim.classList.add("is-visible");
  }

  function closeSidebar() {
    byId("dashboardSidebar").classList.remove("open");
    byId("sidebarToggle").setAttribute("aria-expanded", "false");
    var scrim = byId("sidebarScrim");
    scrim.classList.remove("is-visible");
    scrim.hidden = true;
  }

  /* ============================ wiring ============================ */

  function initEventListeners() {
    Array.prototype.forEach.call(document.querySelectorAll(".nav-item[data-tab]"), function (btn) {
      btn.addEventListener("click", function () { switchTab(btn.dataset.tab); });
    });

    byId("systemSelector").addEventListener("change", function (e) {
      loadSystem(parseInt(e.target.value, 10) || 0);
      render();
      switchTab(state.activeTab);
    });

    byId("riskFilters").addEventListener("click", function (e) {
      var btn = e.target.closest(".filter-btn");
      if (!btn) { return; }
      state.riskFilter = btn.dataset.risk;
      Array.prototype.forEach.call(byId("riskFilters").querySelectorAll(".filter-btn"), function (b) {
        b.classList.toggle("active", b === btn);
      });
      renderDiscovery();
    });

    byId("capabilityCards").addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-action]");
      if (!btn) { return; }
      if (btn.dataset.action === "edit") { openEditModal(btn.dataset.capId); }
      else { reviewCapability(btn.dataset.capId, btn.dataset.action); }
    });

    byId("findingsList").addEventListener("click", function (e) {
      var btn = e.target.closest(".finding-button");
      if (!btn) { return; }
      state.selectedFindingId = btn.dataset.findingId;
      renderFindingsList();
      renderFindingDetail();
    });

    byId("acapVersionsList").addEventListener("click", function (e) {
      if (e.target.closest(".btn-download")) { downloadYaml(); }
    });

    byId("btnGenerateAcap").addEventListener("click", generateAcapVersion);
    byId("btnRunAcapRules").addEventListener("click", runAcapRules);
    byId("btnPreviewYaml").addEventListener("click", togglePreviewYaml);
    byId("btnDownloadYaml").addEventListener("click", downloadYaml);

    byId("editCapabilityForm").addEventListener("submit", submitEdit);
    byId("editModalClose").addEventListener("click", closeEditModal);
    byId("editModalCancel").addEventListener("click", closeEditModal);
    byId("editCapabilityModal").addEventListener("click", function (e) {
      if (e.target === byId("editCapabilityModal")) { closeEditModal(); }
    });

    byId("sidebarToggle").addEventListener("click", function () {
      if (byId("dashboardSidebar").classList.contains("open")) { closeSidebar(); }
      else { openSidebar(); }
    });
    byId("sidebarScrim").addEventListener("click", closeSidebar);

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") { return; }
      if (!byId("editCapabilityModal").classList.contains("hidden")) { closeEditModal(); }
      else { closeSidebar(); }
    });
  }

  function init() {
    if (!DEMO || !DEMO.systems || !DEMO.systems.length) {
      var main = document.querySelector(".main-content");
      if (main) {
        main.insertBefore(
          make("div", "error-banner",
            "Demo data failed to load. assets/demo-data.js is missing or malformed."),
          main.firstChild
        );
      }
      return;
    }
    loadSystem(0);
    renderSystemSelector();
    initEventListeners();
    render();
  }

  init();
})();
