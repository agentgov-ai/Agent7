const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

const state = {
  health: null,
  systems: [],
  acap: null,
  findings: [],
  events: [],
  selectedId: null,
  draft: null,
  coverage: null,
  riskProfile: null,
  applicability: null,
  latestAssessment: null,
  selectedSystemId: null,
  discovery: null,
  discoveryFilter: "all",
  acapVersions: [],
  auditStatus: null,
  actions: [],
  actionSummary: null,
  actionDetails: {},
  killSwitches: [],
  selectedActionId: null,
  activeTab: "overview",
};

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  const panel = byId("tab-" + tabId);
  if (panel) panel.classList.add("active");
  const navBtn = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  if (navBtn) navBtn.classList.add("active");
}

function byId(id) {
  return document.getElementById(id);
}

function endpoint(path) {
  return `${API_BASE}${path}`;
}

function setText(id, value) {
  byId(id).textContent = safeDisplay(value);
}

function safeDisplay(value) {
  if (value == null || value === "") {
    return "-";
  }
  const text = String(value);
  const blockedPatterns = [
    /restaurant waiter bot/i,
    /I want to order/i,
    /ignore (all|previous) instructions/i,
    /SECRET-PROMPT-TEXT/i,
    /SECRET-RESPONSE-TEXT/i,
  ];
  return blockedPatterns.some((pattern) => pattern.test(text)) ? "[redacted]" : text;
}

function clear(element) {
  while (element.firstChild) {
    element.removeChild(element.firstChild);
  }
}

function cell(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  el.textContent = safeDisplay(text);
  return el;
}

function shortId(value) {
  if (!value) {
    return "-";
  }
  const text = String(value);
  return text.length > 12 ? `${text.slice(0, 8)}...${text.slice(-4)}` : text;
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function selectedFinding() {
  return state.findings.find((finding) => finding.finding_id === state.selectedId) || state.findings[0] || null;
}

function kpiAccent(value, goodValues, badValues) {
  if (badValues && badValues.includes(value)) return "accent-danger";
  if (goodValues && goodValues.includes(value)) return "accent-ok";
  return "accent-warning";
}

function friendlyStatus(raw) {
  const map = {
    requires_remediation: "Requires Remediation",
    needs_review: "Needs Review",
    satisfactory: "Satisfactory",
    "no assessment": "No Assessment",
  };
  return map[raw] || raw;
}

function friendlyLevel(raw) {
  const map = {
    delegated: "Delegated",
    advisory: "Advisory",
    autonomous: "Autonomous",
    human_in_loop: "Human-in-Loop",
    human_on_loop: "Human-on-Loop",
    fully_autonomous: "Fully Autonomous",
  };
  return map[raw] || raw;
}

function renderKpiStrip() {
  const a = state.latestAssessment;
  const profile = state.riskProfile && state.riskProfile.risk_profile;
  const eventCount = state.health && Number.isInteger(state.health.events) ? state.health.events : state.events.length;
  const findingCount = state.findings.length;
  const controls = a && a.findings_summary ? a.findings_summary.failed_controls || [] : [];

  const statusVal = a ? a.overall_status : "no assessment";
  const statusEl = byId("kpiStatus");
  statusEl.textContent = safeDisplay(friendlyStatus(statusVal));
  statusEl.className = "kpi-value " + statusBadgeClass(statusVal).replace("badge ", "kpi-");
  byId("kpiStatusCard").className = "kpi-card " + kpiAccent(statusVal, ["satisfactory"], ["requires_remediation"]);

  const riskEl = byId("kpiRisk");
  riskEl.textContent = profile ? safeDisplay(friendlyLevel(profile.authority_level)) : "-";

  setText("kpiEvents", eventCount);
  setText("kpiFindings", findingCount);
  byId("kpiFindingsCard").className = "kpi-card " + (findingCount > 0 ? "accent-danger" : "accent-ok");
  setText("kpiControls", controls.length);
  byId("kpiControlsCard").className = "kpi-card " + (controls.length > 0 ? "accent-danger" : "accent-ok");

  const confidence = a ? a.evidence_confidence : "-";
  const confEl = byId("kpiConfidence");
  confEl.textContent = confidence !== "-" ? safeDisplay(friendlyLevel(confidence)) : "-";
  byId("kpiConfidenceCard").className = "kpi-card " + kpiAccent(confidence, ["high"], ["low"]);
}

function renderSystem() {
  const system = state.systems[0] || {};
  const acap = (state.acap && state.acap.acap) || {};

  setText("systemId", system.system_id);
  setText("systemDeployment", system.deployment_id);
  setText("systemEnvironment", system.environment);
  setText("systemOwner", system.owner);
  setText("systemPurpose", system.purpose);

  setText("acapId", acap.acap_id || system.acap_id);
  setText("acapReview", acap.reviewed_at);
  setText(
    "acapApprovalTools",
    Array.isArray(acap.approval_required_tools) && acap.approval_required_tools.length
      ? acap.approval_required_tools.join(", ")
      : "-"
  );
  setText("acapProhibitedCount", Number.isInteger(acap.prohibited_action_count) ? acap.prohibited_action_count : "-");

  const status = byId("acapStatus");
  status.className = "badge";
  status.textContent = safeDisplay(acap.status || system.acap_status || "-");
}

function renderFindingsList() {
  const list = byId("findingsList");
  clear(list);

  if (state.findings.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No findings available.";
    list.appendChild(empty);
    return;
  }

  for (const finding of state.findings) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `finding-button${finding.finding_id === state.selectedId ? " active" : ""}`;
    button.addEventListener("click", () => {
      state.selectedId = finding.finding_id;
      render();
    });

    const title = document.createElement("div");
    title.className = "finding-title";

    const id = document.createElement("span");
    id.textContent = finding.finding_id || "Finding";

    const severity = document.createElement("span");
    severity.className = `badge ${finding.severity || ""}`;
    severity.textContent = finding.severity || "-";

    const meta = document.createElement("div");
    meta.className = "finding-meta";
    const isAcap = (finding.rule_id || "").startsWith("R_ACAP_");
    const metaText = isAcap
      ? `${finding.rule_id} | ${finding.capability_name || "-"}`
      : `${finding.rule_id || "-"} | ${finding.session || "-"}`;
    meta.textContent = safeDisplay(metaText);

    if (isAcap) {
      const acapBadge = document.createElement("span");
      acapBadge.className = "badge acap-violation";
      acapBadge.textContent = "ACAP";
      title.append(id, severity, acapBadge);
    } else {
      title.append(id, severity);
    }
    button.append(title, meta);
    list.appendChild(button);
  }
}

function renderControlAndFrameworks(finding) {
  setText("detailControlId", finding.failed_control || "-");
  setText("detailControlTitle", finding.failed_control_title || "-");

  const container = byId("frameworkMappings");
  clear(container);

  const mappings = finding.framework_mappings;
  if (!mappings || typeof mappings !== "object" || Object.keys(mappings).length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No framework mappings available.";
    container.appendChild(empty);
    return;
  }

  const labels = {
    ACAP: "ACAP",
    NIST_AI_RMF: "NIST AI RMF",
    EU_AI_Act: "EU AI Act",
    ISO_42001: "ISO/IEC 42001",
  };

  for (const [key, mapping] of Object.entries(mappings)) {
    const card = document.createElement("div");
    card.className = "framework-card";

    const title = document.createElement("h4");
    title.textContent = labels[key] || key;
    card.appendChild(title);

    for (const [field, value] of Object.entries(mapping)) {
      if (field === "note") {
        continue;
      }
      const row = document.createElement("div");
      row.className = "fw-row";
      row.textContent = safeDisplay(`${field}: ${value}`);
      card.appendChild(row);
    }

    if (mapping.note) {
      const disclaimer = document.createElement("div");
      disclaimer.className = "disclaimer";
      disclaimer.textContent = safeDisplay(mapping.note);
      card.appendChild(disclaimer);
    }

    container.appendChild(card);
  }
}

function renderEventIds(finding) {
  const container = byId("eventIds");
  clear(container);

  const ids = Array.isArray(finding.event_ids) ? finding.event_ids : [];
  if (ids.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No linked event IDs.";
    container.appendChild(empty);
    return;
  }

  for (const eventId of ids) {
    const chip = document.createElement("span");
    chip.className = "id-chip";
    chip.textContent = safeDisplay(eventId);
    container.appendChild(chip);
  }
}

function findingEvents(finding) {
  const linkedIds = new Set(Array.isArray(finding.event_ids) ? finding.event_ids : []);
  const traceIds = new Set(Array.isArray(finding.trace_ids) ? finding.trace_ids : []);
  const session = finding.session || "";

  const inScope = state.events.filter((event) => {
    if (linkedIds.has(event.event_id)) {
      return true;
    }
    if (event._session_ref && event._session_ref === session) {
      return true;
    }
    return traceIds.has(event.trace_id);
  });

  return inScope.sort((a, b) => {
    const aLine = Number.isInteger(a._jsonl_line) ? a._jsonl_line : Number.MAX_SAFE_INTEGER;
    const bLine = Number.isInteger(b._jsonl_line) ? b._jsonl_line : Number.MAX_SAFE_INTEGER;
    if (aLine !== bLine) {
      return aLine - bLine;
    }
    return String(a.timestamp || "").localeCompare(String(b.timestamp || ""));
  });
}

function eventTitle(event) {
  const toolName = event.tool && event.tool.name;
  const componentName = event.component && event.component.name;
  return [event.event_type, toolName || componentName].filter(Boolean).join(" / ");
}

function eventSubtext(event) {
  const parts = [];
  if (event.outcome && event.outcome.status) {
    parts.push(`status ${event.outcome.status}`);
  }
  if (event.tool && event.tool.action_type) {
    parts.push(`action ${event.tool.action_type}`);
  }
  if (event.tool && event.tool.target) {
    parts.push(`target ${event.tool.target}`);
  }
  if (event.trace_id) {
    parts.push(`trace ${shortId(event.trace_id)}`);
  }
  return parts.join(" | ");
}

function renderTimeline(finding) {
  const timeline = byId("timeline");
  clear(timeline);

  const linkedIds = new Set(Array.isArray(finding.event_ids) ? finding.event_ids : []);
  const events = findingEvents(finding);

  if (events.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No events loaded for this finding.";
    timeline.appendChild(empty);
    return;
  }

  for (const event of events) {
    const item = document.createElement("li");
    item.className = `timeline-item${linkedIds.has(event.event_id) ? " linked" : ""}`;

    const time = document.createElement("div");
    time.className = "timeline-time";
    time.textContent = safeDisplay(formatTime(event.timestamp));

    const main = document.createElement("div");
    main.className = "timeline-main";

    const kind = document.createElement("div");
    kind.className = "timeline-kind";
    kind.textContent = safeDisplay(eventTitle(event) || "event");

    const sub = document.createElement("div");
    sub.className = "timeline-sub";
    sub.textContent = safeDisplay(eventSubtext(event) || "-");

    const id = document.createElement("div");
    id.className = "timeline-id";
    id.textContent = safeDisplay(event.event_id || "-");

    main.append(kind, sub);
    item.append(time, main, id);
    timeline.appendChild(item);
  }
}

const RULE_RECOMMENDATIONS = {
  R1_confirm_without_proposal: "Ensure a place_order proposal exists in the session before confirm_order is invoked. Verify the agent workflow enforces this sequence structurally.",
  R2_confirmation_without_customer_turn: "Require the confirmation to arrive in a separate invoke turn from the proposal, ensuring a trusted human input boundary.",
  R3_duplicate_confirmation: "Add duplicate-detection logic to prevent the same order from being confirmed more than once in a session.",
  R_ACAP_unapproved_observed: "Review this tool and add it to the capability inventory. If it is a legitimate capability, approve it. If not, investigate why it was invoked at runtime.",
  R_ACAP_denied_observed: "This tool is explicitly denied. Investigate why it was invoked at runtime and ensure the agent cannot execute it.",
  R_ACAP_approval_required_missing: "This capability requires trusted approval evidence. Implement a verified approval mechanism (not just approval.granted) before allowing execution.",
  R_ACAP_data_class_mismatch: "Runtime data classes exceed the ACAP-approved boundary. Review and update the capability's allowed data classes or restrict the tool's data access.",
};

function whyItMatters(finding) {
  const control = finding.failed_control_title || "";
  const mappings = finding.framework_mappings || {};
  const frameworks = Object.keys(mappings).length;
  if (!control) return "This finding indicates a governance policy violation.";
  return `${control}. This violation maps to ${frameworks} governance framework${frameworks !== 1 ? "s" : ""} and indicates a gap in the agent's authorization controls.`;
}

function renderDetails() {
  const finding = selectedFinding();
  if (!finding) {
    setText("detailTitle", "Selected Finding");
    setText("detailRule", "-");
    setText("detailSession", "-");
    setText("detailAcap", "-");
    setText("detailOutcome", "-");
    setText("detailDescription", "-");
    setText("detailWhyMatters", "-");
    setText("detailRecommendation", "-");
    setText("detailControlId", "-");
    setText("detailControlTitle", "-");
    clear(byId("frameworkMappings"));
    byId("severityBadge").className = "badge";
    setText("severityBadge", "-");
    byId("detailPanelHead").className = "panel-head";
    clear(byId("eventIds"));
    clear(byId("timeline"));
    return;
  }

  setText("detailTitle", finding.finding_id || "Selected Finding");
  setText("detailRule", `${finding.rule_id || "-"}${finding.violates ? ` (${finding.violates})` : ""}`);
  setText("detailSession", finding.session);
  setText("detailAcap", finding.acap_version_id
    ? `${finding.acap_version_id} (v${finding.acap_version_number})`
    : finding.acap_id);
  setText("detailOutcome", finding.capability_name
    ? `${finding.capability_name} (runtime observed)`
    : finding.outcome_status || "n/a");
  setText("detailDescription", finding.description);
  setText("detailWhyMatters", whyItMatters(finding));
  setText("detailRecommendation", RULE_RECOMMENDATIONS[finding.rule_id] || "Review the finding and update agent controls accordingly.");

  const severityBadge = byId("severityBadge");
  severityBadge.className = `badge ${finding.severity || ""}`;
  severityBadge.textContent = finding.severity || "-";

  const panelHead = byId("detailPanelHead");
  panelHead.className = finding.severity === "high" ? "panel-head sev-high" : "panel-head";

  renderControlAndFrameworks(finding);
  renderEventIds(finding);
  renderTimeline(finding);
}

function renderError(message) {
  const banner = byId("errorBanner");
  if (!message) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function draftValue(obj) {
  if (obj && typeof obj === "object" && "value" in obj) {
    return obj.value;
  }
  return obj;
}

function authBadgeClass(auth) {
  const val = draftValue(auth);
  if (val === "allowed") return "badge allowed";
  if (val === "allowed_with_approval") return "badge conditional";
  if (val === "allowed_conditional") return "badge conditional";
  if (val === "prohibited") return "badge high";
  return "badge";
}

function coverageBadgeClass(status) {
  if (status === "captured" || status === "captured_for_new_events") return "badge allowed";
  if (status === "captured_with_annotation") return "badge allowed";
  if (status === "partial" || status === "annotation_required") return "badge medium";
  if (status === "missing") return "badge high";
  return "badge";
}

function renderAcapReview() {
  const body = byId("toolReviewBody");
  clear(body);
  const statusBadge = byId("draftStatus");

  if (!state.draft || !state.draft.tools) {
    statusBadge.className = "badge";
    statusBadge.textContent = "-";
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "empty";
    cell.textContent = "No draft ACAP available.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  statusBadge.className = "badge";
  statusBadge.textContent = safeDisplay(state.draft.status || "draft");

  for (const tool of state.draft.tools) {
    const row = document.createElement("tr");

    const nameCell = document.createElement("td");
    nameCell.textContent = safeDisplay(tool.name);
    nameCell.className = "mono";

    const actionCell = document.createElement("td");
    actionCell.textContent = safeDisplay(draftValue(tool.proposed_action_type) || "-");

    const approvalCell = document.createElement("td");
    const approvalVal = tool.approval && tool.approval.required;
    const reqVal = draftValue(approvalVal);
    approvalCell.textContent = reqVal === true ? "required" : reqVal === false ? "no" : safeDisplay(String(reqVal ?? "-"));

    const usageCell = document.createElement("td");
    const usage = tool.observed_usage || {};
    usageCell.textContent = typeof usage.starts === "number" ? usage.starts : "-";

    const authCell = document.createElement("td");
    const authBadge = document.createElement("span");
    const authVal = draftValue(tool.authorization) || "unresolved";
    authBadge.className = authBadgeClass(tool.authorization);
    authBadge.textContent = safeDisplay(String(authVal));
    authCell.appendChild(authBadge);

    row.append(nameCell, actionCell, approvalCell, usageCell, authCell);
    body.appendChild(row);
  }
}

function renderCoverage() {
  const body = byId("coverageBody");
  clear(body);
  const countBadge = byId("coverageEventCount");

  if (!state.coverage || !state.coverage.fields) {
    countBadge.className = "badge";
    countBadge.textContent = "-";
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty";
    cell.textContent = "No coverage data available.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  countBadge.className = "badge";
  countBadge.textContent = `${state.coverage.event_count} events`;

  for (const entry of state.coverage.fields) {
    const row = document.createElement("tr");

    const fieldCell = document.createElement("td");
    fieldCell.textContent = safeDisplay(entry.field);

    const statusCell = document.createElement("td");
    const statusBadge = document.createElement("span");
    statusBadge.className = coverageBadgeClass(entry.status);
    statusBadge.textContent = safeDisplay(entry.status);
    statusCell.appendChild(statusBadge);

    const presenceCell = document.createElement("td");
    presenceCell.textContent = entry.presence != null ? `${(entry.presence * 100).toFixed(1)}%` : "-";

    const noteCell = document.createElement("td");
    noteCell.className = "muted";
    noteCell.textContent = safeDisplay(entry.note || "-");

    row.append(fieldCell, statusCell, presenceCell, noteCell);
    body.appendChild(row);
  }
}

function applicableBadgeClass(value) {
  if (value === true) return "badge allowed";
  if (value === false) return "badge not-applicable";
  if (value === "informational") return "badge informational";
  return "badge";
}

function applicableLabel(value) {
  if (value === true) return "yes";
  if (value === false) return "no";
  return String(value);
}

function renderRiskProfile() {
  const profile = state.riskProfile && state.riskProfile.risk_profile;
  if (!profile) {
    setText("riskUseCase", "-");
    setText("riskEnvironment", "-");
    setText("riskAuthority", "-");
    setText("riskAutonomy", "-");
    setText("riskDataSensitivity", "-");
    setText("riskSideEffects", "-");
    setText("riskApprovalModel", "-");
    setText("riskJurisdiction", "-");
    return;
  }
  setText("riskUseCase", profile.use_case);
  setText("riskEnvironment", profile.environment);
  setText("riskAuthority", profile.authority_level);
  setText("riskAutonomy", profile.autonomy_level);
  setText("riskDataSensitivity", profile.data_sensitivity);
  setText("riskSideEffects", profile.external_side_effects ? "yes" : "no");
  setText("riskApprovalModel", profile.human_approval_model);
  setText("riskJurisdiction", profile.jurisdiction || "none");
}

function renderApplicability() {
  const body = byId("applicabilityBody");
  clear(body);
  const frameworks = state.applicability && state.applicability.frameworks;
  if (!frameworks || frameworks.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 3;
    cell.className = "empty";
    cell.textContent = "No applicability data available.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }
  for (const entry of frameworks) {
    const row = document.createElement("tr");

    const nameCell = document.createElement("td");
    nameCell.textContent = safeDisplay(entry.framework);
    nameCell.style.fontWeight = "600";

    const badgeCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = applicableBadgeClass(entry.applicable);
    badge.textContent = applicableLabel(entry.applicable);
    badgeCell.appendChild(badge);

    const reasonCell = document.createElement("td");
    reasonCell.className = "muted";
    reasonCell.textContent = safeDisplay(entry.reason);

    row.append(nameCell, badgeCell, reasonCell);
    body.appendChild(row);
  }
}

function statusBadgeClass(status) {
  if (status === "satisfactory" || status === "passed") return "badge allowed";
  if (status === "needs_review") return "badge medium";
  if (status === "requires_remediation" || status === "failed") return "badge high";
  if (status === "not_applicable") return "badge not-applicable";
  if (status === "informational") return "badge informational";
  return "badge";
}

function renderLatestAssessment() {
  const a = state.latestAssessment;
  const badge = byId("overallStatusBadge");
  if (!a) {
    badge.className = "badge";
    badge.textContent = "no assessment";
    setText("assessmentId", "-");
    setText("assessmentTime", "-");
    setText("assessmentConfidence", "-");
    setText("assessmentControls", "-");
    clear(byId("frameworkStatusBody"));
    clear(byId("recommendedActions"));
    return;
  }
  badge.className = statusBadgeClass(a.overall_status);
  badge.textContent = safeDisplay(a.overall_status);
  setText("assessmentId", a.assessment_id);
  setText("assessmentTime", formatTime(a.assessed_at));
  const confEl = byId("assessmentConfidence");
  confEl.textContent = safeDisplay(a.evidence_confidence);
  const controls = (a.findings_summary && a.findings_summary.failed_controls) || [];
  setText("assessmentControls", controls.length ? controls.join(", ") : "none");

  const fwBody = byId("frameworkStatusBody");
  clear(fwBody);
  for (const fw of (a.framework_status || [])) {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.textContent = safeDisplay(fw.framework);
    nameCell.style.fontWeight = "600";
    const statusCell = document.createElement("td");
    const sBadge = document.createElement("span");
    sBadge.className = statusBadgeClass(fw.status);
    sBadge.textContent = safeDisplay(fw.status);
    statusCell.appendChild(sBadge);
    row.append(nameCell, statusCell);
    fwBody.appendChild(row);
  }

  const actionList = byId("recommendedActions");
  clear(actionList);
  const actions = a.recommended_next_actions || [];
  if (actions.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No recommended actions.";
    actionList.appendChild(li);
  } else {
    for (const action of actions) {
      const li = document.createElement("li");
      li.textContent = safeDisplay(action);
      actionList.appendChild(li);
    }
  }
}

async function runAssessment() {
  const sid = state.selectedSystemId;
  if (!sid) return;
  try {
    await fetch(endpoint(`/systems/${encodeURIComponent(sid)}/assessments/run`), {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    await loadEvidenceView();
  } catch (err) {
    renderError(`Assessment run failed: ${err.message}`);
  }
}

async function demoReset() {
  try {
    await fetch(endpoint("/demo/reset"), {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    await loadEvidenceView();
  } catch (err) {
    renderError(`Demo reset failed: ${err.message}`);
  }
}

function render() {
  renderKpiStrip();
  renderSystem();
  renderAcapReview();
  renderWorkflowStatus();
  renderAuditStatus();
  renderDiscovery();
  renderCoverage();
  renderRiskProfile();
  renderApplicability();
  renderLatestAssessment();
  renderGovernedActions();
  renderKillSwitches();
  renderApprovals();
  renderShellChrome();
  renderFindingsList();
  renderDetails();
  // Update sidebar status
  const statusEl = byId("sidebarStatus");
  if (statusEl) {
    const h = state.health;
    statusEl.textContent = h && h.ok ? "Connected" : "Offline";
  }
}

async function readJson(path) {
  const response = await fetch(endpoint(path), { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function populateSystemSelector(systems) {
  const selector = byId("systemSelector");
  clear(selector);
  for (const system of systems) {
    const option = document.createElement("option");
    option.value = system.system_id;
    option.textContent = system.system_id;
    if (system.system_id === state.selectedSystemId) {
      option.selected = true;
    }
    selector.appendChild(option);
  }
}

async function loadEvidenceView() {
  renderError("");
  try {
    const systemsPayload = await readJson("/systems");
    const systems = Array.isArray(systemsPayload.systems) ? systemsPayload.systems : [];
    state.systems = systems;

    if (!state.selectedSystemId && systems.length > 0) {
      state.selectedSystemId = systems[0].system_id;
    }
    populateSystemSelector(systems);

    const sid = state.selectedSystemId;
    const enc = sid ? encodeURIComponent(sid) : null;

    const [health, findingsPayload, eventsPayload] = await Promise.all([
      readJson("/health"),
      sid ? readJson(`/findings?system_id=${enc}`) : readJson("/findings"),
      readJson("/evidence/events?limit=5000"),
    ]);

    const acapPayload = sid ? await readJson(`/systems/${enc}/acap`) : null;

    let draftPayload = null;
    let coveragePayload = null;
    let riskPayload = null;
    let applicabilityPayload = null;
    if (sid) {
      try {
        [draftPayload, coveragePayload, riskPayload, applicabilityPayload] = await Promise.all([
          readJson(`/systems/${enc}/acap/draft`),
          readJson(`/systems/${enc}/coverage`),
          readJson(`/systems/${enc}/risk-profile`),
          readJson(`/systems/${enc}/framework-applicability`),
        ]);
      } catch (_) { /* optional endpoints; continue with null */ }
    }

    let discoveryPayload = null;
    let acapVersionsPayload = [];
    if (sid) {
      try { discoveryPayload = await readJson(`/systems/${enc}/discovery`); }
      catch (_) { /* no discovery yet */ }
      try {
        const vp = await readJson(`/systems/${enc}/acap/versions`);
        acapVersionsPayload = Array.isArray(vp.versions) ? vp.versions : [];
      } catch (_) { /* no versions yet */ }
    }

    let auditStatusPayload = null;
    if (sid) {
      try { auditStatusPayload = await readJson(`/systems/${enc}/audit-status`); }
      catch (_) { /* optional */ }
    }

    let latestAssessment = null;
    if (sid) {
      try {
        const assessList = await readJson(`/systems/${enc}/assessments`);
        const items = Array.isArray(assessList.assessments) ? assessList.assessments : [];
        if (items.length > 0) {
          latestAssessment = await readJson(`/assessments/${encodeURIComponent(items[0].assessment_id)}`);
        }
      } catch (_) { /* optional */ }
    }

    state.health = health;
    state.discovery = discoveryPayload;
    state.acapVersions = acapVersionsPayload;
    state.auditStatus = auditStatusPayload;
    state.acap = acapPayload;
    state.draft = draftPayload;
    state.coverage = coveragePayload;
    state.riskProfile = riskPayload;
    state.applicability = applicabilityPayload;
    state.latestAssessment = latestAssessment;
    state.findings = Array.isArray(findingsPayload.findings) ? findingsPayload.findings : [];
    state.events = Array.isArray(eventsPayload.events) ? eventsPayload.events : [];
    state.selectedId = (state.findings[0] || {}).finding_id || null;
    state.actionDetails = {};
    state.selectedActionId = null;
    if (sid) await loadGovernedActions(sid);
    render();
  } catch (error) {
    state.health = { ok: false };
    render();
    renderError(`Unable to load evidence data from ${API_BASE || "this API"}: ${error.message}`);
  }
}

function exportReport() {
  const sid = state.selectedSystemId;
  if (!sid) return;
  window.open(endpoint(`/systems/${encodeURIComponent(sid)}/assessment-report.md`), "_blank");
}

// ---------------------------------------------------------------------------
// Discovery section
// ---------------------------------------------------------------------------

function riskBadgeClass(risk) {
  if (risk === "high") return "badge danger";
  if (risk === "medium") return "badge warning";
  return "badge allowed";
}

function capStatusBadgeClass(status) {
  if (status === "approved_for_acap") return "badge allowed";
  if (status === "rejected") return "badge high";
  if (status === "false_positive") return "badge not-applicable";
  if (status === "edited") return "badge informational";
  return "badge medium";
}

function renderDiscovery() {
  const d = state.discovery;
  const summaryPanel = byId("scanSummaryPanel");
  const filtersEl = byId("riskFilters");
  const cardsEl = byId("capabilityCards");
  const surfacePanel = byId("modelSurfacePanel");
  const uploadPanel = byId("discoveryUploadPanel");

  if (!d) {
    summaryPanel.style.display = "none";
    filtersEl.style.display = "none";
    clear(cardsEl);
    surfacePanel.style.display = "none";
    uploadPanel.style.display = "";
    byId("acapPreviewPanel").style.display = "none";
    renderAcapVersions();
    return;
  }

  uploadPanel.style.display = "none";
  summaryPanel.style.display = "";
  filtersEl.style.display = "";

  const s = d.scan_summary || {};
  setText("scanUploadId", shortId(d.upload_id));
  setText("scanFilesScanned", s.files_scanned);
  setText("scanFunctionsSeen", s.functions_seen);
  setText("scanCandidatesFound", s.candidates_found);
  setText("scanModelSurface", s.model_surface_found);
  setText("scanHighRisk", s.high_risk_count);
  setText("scanMediumRisk", s.medium_risk_count);
  setText("scanLowRisk", s.low_risk_count);
  setText("scanUploadedAt", formatTime(d.uploaded_at));

  clear(cardsEl);
  const caps = d.capabilities || [];
  const filter = state.discoveryFilter;
  const filtered = caps.filter(c => {
    if (filter === "all") return true;
    if (filter === "pending") return c.review_status === "pending";
    if (filter === "reviewed") return c.review_status !== "pending";
    return c.risk === filter;
  });

  for (const cap of filtered) {
    cardsEl.appendChild(renderCapabilityCard(cap));
  }
  if (filtered.length === 0) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "No capabilities match the current filter.";
    cardsEl.appendChild(p);
  }

  const ms = d.model_surface || [];
  if (ms.length > 0) {
    surfacePanel.style.display = "";
    const tbody = byId("modelSurfaceBody");
    clear(tbody);
    for (const entry of ms) {
      const row = document.createElement("tr");
      const providerCell = document.createElement("td");
      providerCell.appendChild(cell("span", "badge", entry.provider));
      row.append(
        cell("td", "mono", entry.name),
        providerCell,
        cell("td", "mono", entry.file_path),
        cell("td", "", entry.line),
        cell("td", "muted", (entry.call_chain || []).join(" "))
      );
      tbody.appendChild(row);
    }
  } else {
    surfacePanel.style.display = "none";
  }

  renderAcapPreview();
  renderAcapVersions();
}

function renderCapabilityCard(cap) {
  const card = document.createElement("div");
  card.className = `capability-card risk-${cap.risk || "low"}`;

  const header = document.createElement("div");
  header.className = "cap-header";
  header.append(
    cell("span", "cap-name", cap.name),
    cell("span", riskBadgeClass(cap.risk), cap.risk),
    cell("span", "badge", `${safeDisplay(cap.confidence_source)} (${safeDisplay(cap.confidence)})`),
    cell("span", capStatusBadgeClass(cap.review_status), cap.review_status)
  );
  card.appendChild(header);

  const meta = document.createElement("div");
  meta.className = "cap-meta";
  meta.append(
    cell("span", "mono", `${safeDisplay(cap.file_path)}:${safeDisplay(cap.line_start)}-${safeDisplay(cap.line_end)}`),
    cell("span", "", `module: ${safeDisplay(cap.module_path)}`),
    cell("span", "", `action: ${safeDisplay(cap.suggested_action_type)}`),
    cell("span", "", `data: ${safeDisplay((cap.suggested_data_classes || []).join(", ") || "-")}`)
  );
  card.appendChild(meta);

  const evidence = cap.evidence || [];
  if (evidence.length > 0) {
    const evDiv = document.createElement("div");
    evDiv.className = "cap-evidence";
    const ul = document.createElement("ul");
    for (const ev of evidence) {
      const li = document.createElement("li");
      li.textContent = `${ev.type}: ${safeDisplay(ev.detail)} (line ${ev.line})`;
      ul.appendChild(li);
    }
    evDiv.appendChild(ul);
    card.appendChild(evDiv);
  }

  const chains = cap.call_chain || [];
  if (chains.length > 0) {
    const chainDiv = document.createElement("div");
    chainDiv.className = "cap-call-chain mono";
    chainDiv.textContent = chains.join(" | ");
    card.appendChild(chainDiv);
  }

  const actions = document.createElement("div");
  actions.className = "cap-actions";

  const approveBtn = document.createElement("button");
  approveBtn.className = "btn-approve";
  approveBtn.textContent = "Approve";
  approveBtn.addEventListener("click", () => reviewCapability(cap.capability_id, "approve"));

  const editBtn = document.createElement("button");
  editBtn.className = "btn-edit";
  editBtn.textContent = "Edit";
  editBtn.addEventListener("click", () => openEditModal(cap));

  const rejectBtn = document.createElement("button");
  rejectBtn.className = "btn-reject";
  rejectBtn.textContent = "Reject";
  rejectBtn.addEventListener("click", () => reviewCapability(cap.capability_id, "reject"));

  const fpBtn = document.createElement("button");
  fpBtn.className = "btn-false-positive";
  fpBtn.textContent = "Not a Capability";
  fpBtn.addEventListener("click", () => reviewCapability(cap.capability_id, "not-a-capability"));

  actions.append(approveBtn, editBtn, rejectBtn, fpBtn);
  card.appendChild(actions);
  return card;
}

async function reviewCapability(capabilityId, action) {
  const sid = state.selectedSystemId;
  if (!sid) return;
  try {
    const resp = await fetch(
      endpoint(`/systems/${encodeURIComponent(sid)}/capabilities/${encodeURIComponent(capabilityId)}/${action}`),
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!resp.ok) {
      const err = await resp.json();
      renderError(`Review failed: ${err.detail || resp.status}`);
      return;
    }
    const enc = encodeURIComponent(sid);
    try { state.discovery = await readJson(`/systems/${enc}/discovery`); }
    catch (_) { state.discovery = null; }
    renderDiscovery();
  } catch (err) {
    renderError(`Review failed: ${err.message}`);
  }
}

function openEditModal(cap) {
  byId("editCapId").value = cap.capability_id;
  byId("editActionType").value = "";
  byId("editRisk").value = "";
  byId("editDataClasses").value = (cap.suggested_data_classes || []).join(", ");
  byId("editApprovalRequired").checked = !!cap.suggested_approval_required;
  byId("editSideEffect").checked = !!cap.external_side_effect;
  byId("editCapabilityModal").classList.remove("hidden");
}

function closeEditModal() {
  byId("editCapabilityModal").classList.add("hidden");
}

async function submitEdit(e) {
  e.preventDefault();
  const sid = state.selectedSystemId;
  const capId = byId("editCapId").value;
  if (!sid || !capId) return;
  const body = {};
  const at = byId("editActionType").value;
  if (at) body.action_type = at;
  const rk = byId("editRisk").value;
  if (rk) body.risk = rk;
  const dc = byId("editDataClasses").value.trim();
  if (dc) body.data_classes = dc.split(",").map(s => s.trim()).filter(Boolean);
  body.approval_required = byId("editApprovalRequired").checked;
  body.external_side_effect = byId("editSideEffect").checked;
  try {
    const resp = await fetch(
      endpoint(`/systems/${encodeURIComponent(sid)}/capabilities/${encodeURIComponent(capId)}/edit`),
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    );
    if (!resp.ok) {
      const err = await resp.json();
      renderError(`Edit failed: ${err.detail || resp.status}`);
      return;
    }
    closeEditModal();
    const enc = encodeURIComponent(sid);
    try { state.discovery = await readJson(`/systems/${enc}/discovery`); }
    catch (_) { state.discovery = null; }
    renderDiscovery();
  } catch (err) {
    renderError(`Edit failed: ${err.message}`);
  }
}

async function uploadDiscovery() {
  const fileInput = byId("discoveryFile");
  const systemId = byId("discoverySystemId").value.trim() || state.selectedSystemId;
  if (!systemId) { renderError("Enter a System ID for the upload."); return; }
  if (!fileInput.files || fileInput.files.length === 0) {
    renderError("Select a governance-discovery.json file."); return;
  }
  try {
    const text = await fileInput.files[0].text();
    const discovery = JSON.parse(text);
    const resp = await fetch(endpoint("/discovery/upload"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_id: systemId, discovery }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      renderError(`Upload failed: ${err.detail || resp.status}`);
      return;
    }
    renderError("");
    // Refresh systems (upload auto-registers new system)
    try {
      const sp = await readJson("/systems");
      state.systems = Array.isArray(sp.systems) ? sp.systems : [];
      populateSystemSelector(state.systems);
    } catch (_) {}
    // Select the uploaded system and switch to Discovery tab
    state.selectedSystemId = systemId;
    populateSystemSelector(state.systems);
    const enc = encodeURIComponent(systemId);
    try { state.discovery = await readJson(`/systems/${enc}/discovery`); }
    catch (_) { state.discovery = null; }
    switchTab("discovery");
    renderDiscovery();
    renderWorkflowStatus();
  } catch (err) {
    renderError(`Upload failed: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// ACAP preview & version generation
// ---------------------------------------------------------------------------

function renderAcapPreview() {
  const panel = byId("acapPreviewPanel");
  const d = state.discovery;
  if (!d || !d.capabilities || d.capabilities.length === 0) {
    panel.style.display = "none";
    return;
  }
  panel.style.display = "";

  const caps = d.capabilities;
  let approved = 0, denied = 0, pending = 0, fp = 0, pendingHighRisk = 0;
  const allowedNames = [];
  const deniedNames = [];

  for (const c of caps) {
    const s = c.review_status;
    if (s === "approved_for_acap" || s === "edited") { approved++; allowedNames.push(c.name); }
    else if (s === "rejected") { denied++; deniedNames.push(c.name); }
    else if (s === "false_positive") { fp++; }
    else { pending++; if (c.risk === "high") pendingHighRisk++; }
  }

  setText("previewApproved", approved);
  setText("previewDenied", denied);
  setText("previewPending", pending);
  setText("previewFP", fp);

  const warn = byId("acapPreviewWarning");
  if (pendingHighRisk > 0) {
    warn.style.display = "";
    warn.textContent = `Warning: ${pendingHighRisk} high-risk capability${pendingHighRisk > 1 ? "ies" : "y"} remain unreviewed.`;
  } else if (pending > 0) {
    warn.style.display = "";
    warn.textContent = `${pending} capability${pending > 1 ? "ies" : "y"} still pending review.`;
  } else {
    warn.style.display = "none";
  }

  const allowedEl = byId("acapPreviewAllowed");
  clear(allowedEl);
  if (allowedNames.length > 0) {
    const h = document.createElement("h4");
    h.textContent = "Allowed capabilities";
    h.className = "preview-subhead";
    allowedEl.appendChild(h);
    const ul = document.createElement("ul");
    ul.className = "preview-list";
    for (const n of allowedNames) { const li = document.createElement("li"); li.textContent = n; li.className = "mono"; ul.appendChild(li); }
    allowedEl.appendChild(ul);
  }

  const deniedEl = byId("acapPreviewDeniedList");
  clear(deniedEl);
  if (deniedNames.length > 0) {
    const h = document.createElement("h4");
    h.textContent = "Denied capabilities";
    h.className = "preview-subhead";
    deniedEl.appendChild(h);
    const ul = document.createElement("ul");
    ul.className = "preview-list";
    for (const n of deniedNames) { const li = document.createElement("li"); li.textContent = n; li.className = "mono"; ul.appendChild(li); }
    deniedEl.appendChild(ul);
  }
}

function renderAcapVersions() {
  const panel = byId("acapVersionsPanel");
  const versions = state.acapVersions || [];
  if (versions.length === 0) { panel.style.display = "none"; return; }
  panel.style.display = "";
  const list = byId("acapVersionsList");
  clear(list);
  const sid = state.selectedSystemId;
  for (const v of versions) {
    const card = document.createElement("div");
    card.className = "acap-version-card";
    card.append(
      cell("span", "badge allowed", `v${safeDisplay(v.version_number)}`),
      cell("span", "mono", v.acap_version_id),
      cell("span", "muted", formatTime(v.generated_at))
    );
    if (sid) {
      const dlBtn = document.createElement("a");
      dlBtn.className = "btn-download";
      dlBtn.textContent = "governance.yaml";
      dlBtn.href = endpoint(`/systems/${encodeURIComponent(sid)}/governance-manifest.yaml?version_id=${encodeURIComponent(v.acap_version_id)}`);
      dlBtn.download = "governance.yaml";
      card.appendChild(dlBtn);
    }
    list.appendChild(card);
  }

  byId("manifestUsagePanel").style.display = versions.length > 0 ? "" : "none";
}

async function generateAcapVersion() {
  const sid = state.selectedSystemId;
  if (!sid) return;
  try {
    const resp = await fetch(
      endpoint(`/systems/${encodeURIComponent(sid)}/acap/generate-from-discovery`),
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!resp.ok) {
      const err = await resp.json();
      renderError(`ACAP generation failed: ${err.detail || resp.status}`);
      return;
    }
    renderError("");
    const enc = encodeURIComponent(sid);
    try {
      const vp = await readJson(`/systems/${enc}/acap/versions`);
      state.acapVersions = Array.isArray(vp.versions) ? vp.versions : [];
    } catch (_) { state.acapVersions = []; }
    renderAcapPreview();
    renderAcapVersions();
    renderWorkflowStatus();
  } catch (err) {
    renderError(`ACAP generation failed: ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Audit status
// ---------------------------------------------------------------------------

function renderAuditStatus() {
  const panel = byId("auditStatusPanel");
  const badge = byId("auditStatusBadge");
  const action = byId("auditNextAction");
  const as = state.auditStatus;
  if (!as) {
    badge.className = "badge";
    badge.textContent = "-";
    action.textContent = "Select a system to view audit status.";
    return;
  }
  const statusMap = {
    up_to_date: { cls: "badge allowed", label: "Up to date" },
    discovery_missing: { cls: "badge", label: "Discovery missing" },
    acap_missing: { cls: "badge warning", label: "ACAP missing" },
    runtime_missing: { cls: "badge", label: "Runtime missing" },
    needs_reapproval: { cls: "badge danger", label: "Needs reapproval" },
    scan_changed_since_acap: { cls: "badge warning", label: "Scan changed" },
    runtime_changed_since_assessment: { cls: "badge warning", label: "Runtime changed" },
  };
  const m = statusMap[as.status] || { cls: "badge", label: as.status };
  badge.className = m.cls;
  badge.textContent = m.label;
  action.textContent = as.next_action || "-";
}

// ---------------------------------------------------------------------------
// Governance workflow status
// ---------------------------------------------------------------------------

function renderWorkflowStatus() {
  const d = state.discovery;
  const versions = state.acapVersions || [];
  const findings = state.findings || [];

  const caps = (d && d.capabilities) || [];
  const reviewed = caps.filter(c => c.review_status !== "pending").length;
  const acapFindings = findings.filter(f => (f.rule_id || "").startsWith("R_ACAP_"));

  _setStep("wfScan", !!d);
  _setStep("wfReview", reviewed > 0);
  _setStep("wfAcap", versions.length > 0);
  _setStep("wfRules", acapFindings.length > 0 || (versions.length > 0 && findings.length > 0));
  _setStep("wfFindings", acapFindings.length > 0);

  // Run ACAP Rules button state
  const btn = byId("btnRunAcapRules");
  const hint = byId("runAcapHint");
  if (versions.length > 0) {
    btn.disabled = false;
    hint.style.display = "none";
  } else {
    btn.disabled = true;
    hint.style.display = d ? "" : "none";
  }
}

function _setStep(id, done) {
  const el = byId(id);
  if (!el) return;
  if (done) { el.classList.add("done"); } else { el.classList.remove("done"); }
}

async function runAcapRules() {
  const sid = state.selectedSystemId;
  if (!sid) return;
  const btn = byId("btnRunAcapRules");
  const result = byId("runAcapResult");
  btn.disabled = true;
  btn.textContent = "Running\u2026";
  result.style.display = "none";
  try {
    const resp = await fetch(
      endpoint(`/systems/${encodeURIComponent(sid)}/rules/run-acap`),
      { method: "POST", headers: { "Content-Type": "application/json" } }
    );
    if (!resp.ok) {
      const err = await resp.json();
      result.textContent = `Failed: ${err.detail || resp.status}`;
      result.className = "wf-result wf-error";
      result.style.display = "";
      return;
    }
    const body = await resp.json();
    result.textContent = `${body.findings_created} finding${body.findings_created !== 1 ? "s" : ""} from ${body.events_evaluated} events (ACAP v${body.acap_version_number})`;
    result.className = "wf-result wf-success";
    result.style.display = "";

    // Refresh findings
    const enc = encodeURIComponent(sid);
    try {
      const fp = await readJson(`/findings?system_id=${enc}`);
      state.findings = Array.isArray(fp.findings) ? fp.findings : [];
      state.selectedId = (state.findings[0] || {}).finding_id || null;
    } catch (_) {}
    renderFindingsList();
    renderDetails();
    renderWorkflowStatus();
  } catch (err) {
    result.textContent = `Error: ${err.message}`;
    result.className = "wf-result wf-error";
    result.style.display = "";
  } finally {
    btn.disabled = false;
    btn.textContent = "Run ACAP Rules";
  }
}

function initEventListeners() {
  byId("runAssessmentBtn").addEventListener("click", runAssessment);
  byId("demoResetBtn").addEventListener("click", demoReset);
  byId("exportReportBtn").addEventListener("click", exportReport);
  byId("systemSelector").addEventListener("change", (e) => {
    state.selectedSystemId = e.target.value;
    loadEvidenceView();
  });

  byId("btnUploadDiscovery").addEventListener("click", uploadDiscovery);
  byId("btnGenerateAcap").addEventListener("click", generateAcapVersion);
  byId("btnRunAcapRules").addEventListener("click", runAcapRules);
  byId("editModalClose").addEventListener("click", closeEditModal);
  byId("editModalCancel").addEventListener("click", closeEditModal);
  byId("editCapabilityForm").addEventListener("submit", submitEdit);
  for (const btn of byId("riskFilters").querySelectorAll(".filter-btn")) {
    btn.addEventListener("click", () => {
      for (const b of byId("riskFilters").querySelectorAll(".filter-btn")) {
        b.classList.remove("active");
      }
      btn.classList.add("active");
      state.discoveryFilter = btn.dataset.risk;
      renderDiscovery();
    });
  }

  const createKsBtn = byId("createKillSwitchBtn");
  if (createKsBtn) createKsBtn.addEventListener("click", createKillSwitch);

  const themeBtn = byId("themeToggle");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  const refreshBtn = byId("refreshBtn");
  if (refreshBtn) refreshBtn.addEventListener("click", refreshView);

  const menuBtn = byId("menuBtn");
  if (menuBtn) menuBtn.addEventListener("click", () => setSidebar(true));
  const backdrop = byId("sidebarBackdrop");
  if (backdrop) backdrop.addEventListener("click", () => setSidebar(false));

  // Tab navigation
  for (const btn of document.querySelectorAll(".nav-item[data-tab]")) {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
      setSidebar(false);
    });
  }
}

// ---------------------------------------------------------------------------
// Shell: theme, refresh, mobile navigation
// ---------------------------------------------------------------------------

const THEME_KEY = "agent7-theme";

function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch (_) {
    /* private mode or blocked storage: the theme still applies for this page */
  }
}

function setSidebar(open) {
  const sidebar = byId("sidebar");
  const backdrop = byId("sidebarBackdrop");
  if (!sidebar || !backdrop) return;
  sidebar.classList.toggle("open", open);
  backdrop.classList.toggle("hidden", !open);
}

async function refreshView() {
  const btn = byId("refreshBtn");
  if (btn) btn.classList.add("spinning");
  try {
    await loadEvidenceView();
  } finally {
    if (btn) btn.classList.remove("spinning");
  }
}

initEventListeners();
loadEvidenceView();

// ---------------------------------------------------------------------------
// Governed Actions
// ---------------------------------------------------------------------------

const PILLARS = [
  { key: "DISCOVER", label: "Discover" },
  { key: "UNDERSTAND", label: "Understand" },
  { key: "AUTHORIZE", label: "Authorize" },
  { key: "ENFORCE", label: "Enforce" },
  { key: "PROVE", label: "Prove" },
  { key: "COMPLY", label: "Comply" },
  { key: "LEARN", label: "Learn" },
];

function pillarStates() {
  const summary = state.actionSummary || {};
  const actions = state.actions || [];
  const hasDecision = actions.some((a) => a.verdict);
  const blocked = (summary.blocked || 0) + (summary.shadow_would_block || 0);
  const enforcing = actions.some((a) => a.enforcement_mode && a.enforcement_mode !== "observe");
  return {
    DISCOVER: state.discovery ? "done" : "pending",
    UNDERSTAND: actions.length > 0 ? "done" : "pending",
    AUTHORIZE: hasDecision ? "done" : "pending",
    ENFORCE: blocked > 0 ? "done" : enforcing ? "partial" : "pending",
    PROVE: actions.some((a) => a.execution_status) ? "done" : "pending",
    COMPLY: (state.findings || []).length > 0 ? "partial" : "pending",
    LEARN: actions.length > 0 ? "partial" : "pending",
  };
}

function renderPillars() {
  const host = byId("pillarRibbon");
  if (!host) return;
  clear(host);
  const states = pillarStates();
  for (const pillar of PILLARS) {
    const node = document.createElement("div");
    node.className = `pillar ${states[pillar.key]}`;
    const dot = document.createElement("span");
    dot.className = "pillar-dot";
    const label = document.createElement("span");
    label.className = "pillar-label";
    label.textContent = pillar.label;
    const sub = document.createElement("span");
    sub.className = "pillar-state";
    sub.textContent = states[pillar.key] === "done" ? "active" : states[pillar.key] === "partial" ? "collecting" : "not yet";
    node.append(dot, label, sub);
    host.appendChild(node);
  }
}

function actionKpi(label, value, accent) {
  const card = document.createElement("div");
  card.className = `kpi-card ${accent}`;
  const v = document.createElement("div");
  v.className = "kpi-value";
  v.textContent = String(value == null ? 0 : value);
  const l = document.createElement("div");
  l.className = "kpi-label";
  l.textContent = label;
  card.append(v, l);
  return card;
}

function verdictBadgeClass(verdict) {
  if (verdict === "ALLOW") return "badge allowed";
  if (verdict === "DENY") return "badge danger";
  if (verdict === "REQUIRE_APPROVAL") return "badge warning";
  return "badge";
}

function executionBadgeClass(status) {
  if (status === "allowed_executed") return "badge allowed";
  if (status === "denied_blocked") return "badge danger";
  if (status === "approval_required_blocked") return "badge warning";
  if (status === "shadow_allowed") return "badge medium";
  if (status === "error") return "badge danger";
  return "badge";
}

function renderActionKpis() {
  const host = byId("actionKpis");
  if (!host) return;
  clear(host);
  const s = state.actionSummary || {};
  host.appendChild(actionKpi("Governed Actions", s.total, "accent-info"));
  host.appendChild(actionKpi("Allowed", s.allowed, "accent-ok"));
  host.appendChild(actionKpi("Denied", s.denied, "accent-danger"));
  host.appendChild(actionKpi("Approval Required", s.approval_required, "accent-warning"));
  host.appendChild(actionKpi("Blocked", s.blocked, "accent-danger"));
  host.appendChild(actionKpi("Shadow Would-Block", s.shadow_would_block, "accent-warning"));
}

function renderGovernedActions() {
  renderPillars();
  renderActionKpis();

  const body = byId("actionsBody");
  if (!body) return;
  clear(body);
  const countBadge = byId("actionCount");
  const actions = state.actions || [];
  if (countBadge) countBadge.textContent = `${actions.length} actions`;

  if (!actions.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "empty";
    cell.textContent = "No governed actions yet. Run an instrumented app with enforcement_mode set to shadow or enforce.";
    row.appendChild(cell);
    body.appendChild(row);
    renderActionDetail();
    return;
  }

  for (const action of actions) {
    const row = document.createElement("tr");
    if (action.action_id === state.selectedActionId) row.className = "selected";
    row.style.cursor = "pointer";
    row.addEventListener("click", () => {
      state.selectedActionId = action.action_id;
      renderGovernedActions();
    });

    const name = document.createElement("td");
    name.textContent = safeDisplay(action.capability_name);

    const verdict = document.createElement("td");
    const vb = document.createElement("span");
    vb.className = verdictBadgeClass(action.verdict);
    vb.textContent = safeDisplay(action.verdict);
    verdict.appendChild(vb);

    const outcome = document.createElement("td");
    const ob = document.createElement("span");
    ob.className = executionBadgeClass(action.execution_status);
    ob.textContent = safeDisplay(action.execution_status);
    outcome.appendChild(ob);

    const mode = document.createElement("td");
    mode.textContent = safeDisplay(action.enforcement_mode);

    const reason = document.createElement("td");
    reason.className = "muted";
    reason.textContent = safeDisplay(action.reason_code);

    const decidedBy = document.createElement("td");
    decidedBy.className = "muted";
    decidedBy.textContent = safeDisplay(action.decided_by);

    const when = document.createElement("td");
    when.className = "muted";
    when.textContent = formatTime(action.created_at);

    row.append(name, verdict, outcome, mode, reason, decidedBy, when);
    body.appendChild(row);
  }

  renderActionDetail();
}

function selectedAction() {
  const actions = state.actions || [];
  return actions.find((a) => a.action_id === state.selectedActionId) || actions[0] || null;
}

function renderActionDetail() {
  const action = selectedAction();
  const badge = byId("actionDetailVerdict");
  if (!badge) return;

  if (!action) {
    badge.className = "badge";
    badge.textContent = "-";
    for (const id of [
      "actionDetailId", "actionDetailDecisionId", "actionDetailCapability", "actionDetailModule",
      "actionDetailMode", "actionDetailStatus", "actionDetailReasonCode", "actionDetailKillSwitch",
      "actionDetailPattern", "actionDetailArgsHash", "actionDetailArgNames", "actionDetailReason",
    ]) {
      const el = byId(id);
      if (el) el.textContent = "-";
    }
    return;
  }

  badge.className = verdictBadgeClass(action.verdict);
  badge.textContent = safeDisplay(action.verdict);
  setText("actionDetailId", action.action_id);
  setText("actionDetailDecisionId", action.decision_id);
  setText("actionDetailCapability", action.capability_name);
  setText("actionDetailModule", action.module_path);
  setText("actionDetailMode", action.enforcement_mode);
  setText("actionDetailStatus", action.execution_status);
  setText("actionDetailReasonCode", action.reason_code);
  setText("actionDetailKillSwitch", action.kill_switch_id);
  setText("actionDetailPattern", action.matched_pattern_id);
  setText("actionDetailArgsHash", action.arguments_hash);
  setText("actionDetailReason", action.reason);

  const names = byId("actionDetailArgNames");
  const detail = state.actionDetails[action.action_id];
  if (names) {
    const argNames = detail && detail.request ? detail.request.argument_names : null;
    names.textContent = Array.isArray(argNames) && argNames.length ? argNames.join(", ") : "-";
  }
  if (!detail) loadActionDetail(action.action_id);
}

async function loadActionDetail(actionId) {
  const sid = state.selectedSystemId;
  if (!sid || state.actionDetails[actionId]) return;
  try {
    state.actionDetails[actionId] = await readJson(
      `/systems/${encodeURIComponent(sid)}/actions/${encodeURIComponent(actionId)}`
    );
    renderActionDetail();
  } catch (_) { /* detail is optional */ }
}

function renderKillSwitches() {
  const body = byId("killSwitchBody");
  if (!body) return;
  clear(body);
  const switches = state.killSwitches || [];
  const countBadge = byId("killSwitchCount");
  if (countBadge) {
    const active = switches.filter((s) => s.enabled).length;
    countBadge.className = active > 0 ? "badge danger" : "badge";
    countBadge.textContent = `${active} active / ${switches.length} total`;
  }

  if (!switches.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty";
    cell.textContent = "No kill switches defined for this system.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const sw of switches) {
    const row = document.createElement("tr");

    const id = document.createElement("td");
    id.className = "mono";
    id.textContent = safeDisplay(sw.kill_switch_id);

    const targets = document.createElement("td");
    targets.textContent = (sw.target_capabilities || []).join(", ") || "-";

    const verdict = document.createElement("td");
    verdict.textContent = safeDisplay(sw.verdict);

    const reason = document.createElement("td");
    reason.className = "muted";
    reason.textContent = safeDisplay(sw.reason || "-");

    const stateCell = document.createElement("td");
    const sb = document.createElement("span");
    sb.className = sw.enabled ? "badge danger" : "badge";
    sb.textContent = sw.enabled ? "ENABLED" : "disabled";
    stateCell.appendChild(sb);

    const actionCell = document.createElement("td");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = sw.enabled ? "btn-secondary" : "btn-primary";
    btn.textContent = sw.enabled ? "Disable" : "Enable";
    btn.addEventListener("click", () => toggleKillSwitch(sw.kill_switch_id, !sw.enabled));
    actionCell.appendChild(btn);

    row.append(id, targets, verdict, reason, stateCell, actionCell);
    body.appendChild(row);
  }
}

async function loadGovernedActions(systemId) {
  const enc = encodeURIComponent(systemId);
  try {
    const payload = await readJson(`/systems/${enc}/actions?limit=200`);
    state.actions = Array.isArray(payload.actions) ? payload.actions : [];
    state.actionSummary = payload.summary || null;
  } catch (_) {
    state.actions = [];
    state.actionSummary = null;
  }
  try {
    const payload = await readJson(`/systems/${enc}/kill-switches`);
    state.killSwitches = Array.isArray(payload.kill_switches) ? payload.kill_switches : [];
  } catch (_) {
    state.killSwitches = [];
  }
}

async function toggleKillSwitch(killSwitchId, enabled) {
  const sid = state.selectedSystemId;
  if (!sid) return;
  const response = await fetch(
    endpoint(`/systems/${encodeURIComponent(sid)}/kill-switches/${encodeURIComponent(killSwitchId)}`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    renderError(`Could not update kill switch: ${err.detail || response.status}`);
    return;
  }
  await loadGovernedActions(sid);
  renderGovernedActions();
  renderKillSwitches();
}

async function createKillSwitch() {
  const sid = state.selectedSystemId;
  if (!sid) return;
  const id = byId("killSwitchId").value.trim();
  const targets = byId("killSwitchTargets").value.split(",").map((s) => s.trim()).filter(Boolean);
  const reason = byId("killSwitchReason").value.trim();
  if (!id || !targets.length) {
    renderError("A kill switch needs an id and at least one target capability.");
    return;
  }
  const response = await fetch(endpoint(`/systems/${encodeURIComponent(sid)}/kill-switches`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kill_switch_id: id,
      target_capabilities: targets,
      enabled: true,
      reason: reason || null,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    renderError(`Could not create kill switch: ${err.detail || response.status}`);
    return;
  }
  byId("killSwitchId").value = "";
  byId("killSwitchTargets").value = "";
  byId("killSwitchReason").value = "";
  await loadGovernedActions(sid);
  renderGovernedActions();
  renderKillSwitches();
}


// ---------------------------------------------------------------------------
// Approvals — a filtered view of the governed actions already in state
// ---------------------------------------------------------------------------

function heldActions() {
  return (state.actions || []).filter(
    (a) => a.verdict === "REQUIRE_APPROVAL" || a.execution_status === "approval_required_blocked"
  );
}

function renderApprovals() {
  const body = byId("approvalsBody");
  if (!body) return;
  clear(body);

  const held = heldActions();
  const countBadge = byId("approvalsCount");
  if (countBadge) {
    countBadge.className = held.length ? "badge warning" : "badge";
    countBadge.textContent = `${held.length} held`;
  }

  const kpis = byId("approvalKpis");
  if (kpis) {
    clear(kpis);
    const summary = state.actionSummary || {};
    kpis.appendChild(actionKpi("Awaiting Approval", held.length, "accent-warning"));
    kpis.appendChild(actionKpi("Approval Required", summary.approval_required, "accent-warning"));
    kpis.appendChild(actionKpi("Executed", summary.executed, "accent-ok"));
    kpis.appendChild(actionKpi("Governed Actions", summary.total, "accent-info"));
  }

  if (!held.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty";
    cell.textContent = "Nothing is waiting on approval.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const action of held) {
    const row = document.createElement("tr");

    const name = document.createElement("td");
    name.textContent = safeDisplay(action.capability_name);

    const verdict = document.createElement("td");
    const vb = document.createElement("span");
    vb.className = verdictBadgeClass(action.verdict);
    vb.textContent = safeDisplay(action.verdict);
    verdict.appendChild(vb);

    const outcome = document.createElement("td");
    const ob = document.createElement("span");
    ob.className = executionBadgeClass(action.execution_status);
    ob.textContent = safeDisplay(action.execution_status);
    outcome.appendChild(ob);

    const mode = document.createElement("td");
    mode.textContent = safeDisplay(action.enforcement_mode);

    const reason = document.createElement("td");
    reason.className = "muted";
    reason.textContent = safeDisplay(action.reason_code);

    const when = document.createElement("td");
    when.className = "muted";
    when.textContent = formatTime(action.created_at);

    row.append(name, verdict, outcome, mode, reason, when);
    body.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Topbar / sidebar chrome driven by loaded state
// ---------------------------------------------------------------------------

function renderShellChrome() {
  const envBadge = byId("envBadge");
  if (envBadge) {
    const events = state.events || [];
    const env = (events.find((e) => e && e.environment) || {}).environment;
    envBadge.textContent = safeDisplay(env || "local");
  }

  const approvals = byId("navApprovalsCount");
  if (approvals) {
    const held = heldActions().length;
    approvals.textContent = String(held);
    approvals.style.display = held ? "" : "none";
  }

  const findings = byId("navFindingsCount");
  if (findings) {
    const count = (state.findings || []).length;
    findings.textContent = String(count);
    findings.style.display = count ? "" : "none";
  }
}
