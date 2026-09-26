/* ============================================================
   AgentGov — static demo fixture for the public demo dashboard.

   This file is the ONLY data source for dashboard.html. There is no
   backend, no fetch(), and no network access of any kind.

   Shapes mirror the real Evidence API so the demo is honest about what
   the product actually produces:
     GET /systems/{id}/discovery              -> discovery
     GET /systems/{id}/acap                   -> acap
     GET /systems/{id}/acap/draft             -> acap_draft
     GET /systems/{id}/acap/versions          -> acap_versions
     GET /systems/{id}/coverage               -> coverage
     GET /evidence/events                     -> events   (public projection)
     GET /findings?system_id=                 -> findings
     GET /systems/{id}/risk-profile           -> risk_profile
     GET /systems/{id}/framework-applicability-> framework_applicability
     GET /assessments/{id}                    -> assessment
     GET /systems/{id}/audit-status           -> audit_status

   PRIVACY: everything here is synthetic. No real prompts, responses,
   API keys, tokens, emails, or customer data. Actor and session
   identifiers are illustrative hash-shaped strings, not real hashes of
   real values.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- shared: the real 17-field coverage matrix ----------
     Field list and statuses follow services/evidence_api/coverage.py.
     The unflattering entries are kept on purpose: AgentGov reports
     missing and annotation-required fields rather than fabricating them. */
  function coverageFields(overrides) {
    var base = [
      { field: "schema_version/event_id/timestamp", status: "captured", presence: 1.0 },
      { field: "system_id/deployment_id/environment", status: "captured", presence: 1.0 },
      { field: "session_id", status: "captured", presence: 1.0 },
      { field: "trace_id/span_id/parent link", status: "captured", presence: 1.0 },
      { field: "event_type + component kind/name", status: "captured", presence: 1.0 },
      { field: "model provider/name", status: "captured", presence: 1.0 },
      { field: "prompt template_hash / message shape", status: "captured", presence: 1.0 },
      {
        field: "prompt template_id",
        status: "annotation_required",
        presence: 0.0,
        note: "Template identity must be declared by the team; it cannot be inferred from runtime."
      },
      { field: "tool name + action classification", status: "captured_with_annotation", presence: 1.0,
        note: "Action type comes from scanner suggestion confirmed in review." },
      { field: "tool sanitized arguments + outcome", status: "captured", presence: 1.0,
        note: "Raw argument values are never stored; only hashes and sanitized summaries." },
      {
        field: "retrieval source identifiers",
        status: "missing",
        presence: 0.0,
        note: "No retriever is instrumented in this system."
      },
      { field: "agent identity", status: "captured", presence: 1.0 },
      { field: "approval required/granted", status: "partial", presence: 0.5,
        note: "approval.granted is self-reported and not trusted evidence on its own." },
      {
        field: "data classification",
        status: "annotation_required",
        presence: 0.33,
        note: "Data classes are a human annotation on reviewed capabilities."
      },
      { field: "status + duration", status: "captured", presence: 1.0 },
      { field: "error type on failures", status: "captured", presence: 1.0 },
      { field: "token usage", status: "partial", presence: 0.4,
        note: "Only model events report tokens; tool events have none." }
    ];
    if (overrides) {
      base.forEach(function (row) {
        if (Object.prototype.hasOwnProperty.call(overrides, row.field)) {
          Object.assign(row, overrides[row.field]);
        }
      });
    }
    return base;
  }

  /* ---------- shared: framework applicability (real 5 entries, real order) ---------- */
  function frameworkApplicability(useCase) {
    return [
      {
        framework: "ACAP",
        applicable: true,
        reason: "System has a reviewed authorization contract; runtime behavior is compared against it.",
        relevance: "primary"
      },
      {
        framework: "OWASP Agentic",
        applicable: true,
        reason: "Agent invokes write and communicate tools with external side effects (A01 excessive agency).",
        relevance: "high"
      },
      {
        framework: "NIST AI RMF",
        applicable: true,
        reason: "Govern 1.1 requires documented, approved boundaries for " + useCase + ".",
        relevance: "high"
      },
      {
        framework: "EU AI Act",
        applicable: false,
        reason: "Not a listed high-risk use case; no biometric, employment, credit, or safety decisioning.",
        relevance: "none"
      },
      {
        framework: "ISO/IEC 42001",
        applicable: "informational",
        reason: "Evidence supports an AI management system audit but no certification is claimed.",
        relevance: "supporting"
      }
    ];
  }

  /* ---------- shared: demo control enrichment ----------
     NOTE: the live backend's ACAP rules do NOT emit these three keys
     (run_all_acap_rules skips control_library.enrich_finding). They are
     added here so the Findings detail panel can show the Failed Control
     and Framework Mappings sections. This is stated plainly in the
     README and the extraction report. */
  var AUTH_CONTROL = {
    failed_control: "AGT-AUTH-001",
    failed_control_title: "Agent must not execute an action outside its approved authorization boundary",
    framework_mappings: {
      ACAP: {
        clause: "authorization_boundary",
        requirement: "Runtime tool use must be contained within allowed_capabilities",
        note: "ACAP is AgentGov's own contract, not an external standard."
      },
      NIST_AI_RMF: {
        function: "GOVERN",
        category: "GOVERN 1.1",
        requirement: "Legal and policy requirements are understood, documented and managed"
      },
      EU_AI_Act: {
        article: "Article 14",
        requirement: "Human oversight measures",
        note: "Mapped for reference only; this system is not classified high-risk."
      },
      ISO_42001: {
        clause: "A.9.2",
        requirement: "Controls for AI system operation"
      }
    }
  };

  /* ============================================================
     SYSTEM 1 — gaming-agent-demo  (primary)
     ============================================================ */

  var GAMING_EVENTS = [
    {
      schema_version: "0.1",
      event_id: "d1f4a7e0-1b2c-4d5e-8f90-a1b2c3d4e5f6",
      timestamp: "2026-09-14T18:22:10.114000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "chain_start",
      trace_id: "t-7f3a91c4",
      span_id: "s-0001",
      parent_span_id: null,
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "gaming-agent-demo", identity_type: "logical_agent", user_id_hash: "sha256:4b8e2f0a91c7dd53" },
      component: { kind: "chain", name: "player_support_turn", version: null },
      outcome: { status: "started", duration_ms: null }
    },
    {
      schema_version: "0.1",
      event_id: "b2c5d8f1-2c3d-4e6f-9a01-b2c3d4e5f607",
      timestamp: "2026-09-14T18:22:10.402000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "llm_start",
      trace_id: "t-7f3a91c4",
      span_id: "s-0002",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "gaming-agent-demo", identity_type: "logical_agent" },
      component: { kind: "chat_model", name: "generate_npc_dialogue", version: null },
      model: { provider: "openai", name: "gpt-4.1-mini", requested_name: "gpt-4.1-mini", resolved_name: "gpt-4.1-mini" },
      prompt: {
        template_id: null,
        template_hash: "sha256:11ab93ff42c0e7d8",
        content_capture: "hash",
        message_count: 3,
        roles: ["system", "user", "assistant"]
      },
      outcome: { status: "started", duration_ms: null }
    },
    {
      schema_version: "0.1",
      event_id: "c3d6e9a2-3d4e-4f70-ab12-c3d4e5f60718",
      timestamp: "2026-09-14T18:22:11.788000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "llm_end",
      trace_id: "t-7f3a91c4",
      span_id: "s-0002",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "chat_model", name: "generate_npc_dialogue", version: null },
      model: { provider: "openai", name: "gpt-4.1-mini" },
      prompt: { template_hash: "sha256:11ab93ff42c0e7d8", content_capture: "hash", message_count: 3 },
      outcome: { status: "success", duration_ms: 1386, error_type: null, input_tokens: 812, output_tokens: 147, total_tokens: 959 }
    },
    {
      schema_version: "0.1",
      event_id: "e5f8a1c4-5f60-4192-cd34-e5f607182930",
      timestamp: "2026-09-14T18:22:12.010000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "tool_start",
      trace_id: "t-7f3a91c4",
      span_id: "s-0003",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "gaming-agent-demo", identity_type: "logical_agent" },
      component: { kind: "tool", name: "update_leaderboard_score", version: null },
      tool: {
        name: "update_leaderboard_score",
        action_type: "write",
        arguments_hash: "sha256:6d2b7e11a0c94f35",
        arguments_exposed: false,
        target: "leaderboard_db",
        external_side_effect: false,
        reversible: true
      },
      data: { classifications: [], sources: ["leaderboard_db"], destinations: ["leaderboard_db"] },
      approval: { required: false, granted: null, approver_id_hash: null, policy_id: null },
      outcome: { status: "started", duration_ms: null }
    },
    {
      schema_version: "0.1",
      event_id: "f607b2d5-6071-42a3-de45-f60718293041",
      timestamp: "2026-09-14T18:22:12.094000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "tool_end",
      trace_id: "t-7f3a91c4",
      span_id: "s-0003",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "tool", name: "update_leaderboard_score", version: null },
      tool: { name: "update_leaderboard_score", action_type: "write", arguments_exposed: false },
      outcome: { status: "success", duration_ms: 84, error_type: null }
    },
    {
      /* DENIED capability observed at runtime -> R_ACAP_denied_observed */
      schema_version: "0.1",
      event_id: "a7182c36-7182-42b4-ef56-071829304152",
      timestamp: "2026-09-14T18:22:13.501000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "tool_start",
      trace_id: "t-7f3a91c4",
      span_id: "s-0004",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "gaming-agent-demo", identity_type: "logical_agent" },
      component: { kind: "tool", name: "ban_toxic_player", version: null },
      tool: {
        name: "ban_toxic_player",
        action_type: "write",
        arguments_hash: "sha256:cf40a9e21b7d6058",
        arguments_exposed: false,
        target: "moderation_service",
        external_side_effect: true,
        reversible: false
      },
      data: { classifications: ["account"], sources: [], destinations: ["moderation_service"] },
      approval: { required: true, granted: null, approver_id_hash: null, policy_id: null },
      outcome: { status: "started", duration_ms: null }
    },
    {
      /* Approval CLAIMED but never verified -> R_ACAP_approval_required_missing.
         approval.granted is self-reported by the agent and is explicitly NOT
         trusted evidence (see services/evidence_api/rules.py:190-202). There is
         no approval.verified / trusted / token_verified flag here. */
      schema_version: "0.1",
      event_id: "b8293d47-8293-42c5-f067-182930415263",
      timestamp: "2026-09-14T18:22:14.220000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "tool_start",
      trace_id: "t-7f3a91c4",
      span_id: "s-0005",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "gaming-agent-demo", identity_type: "logical_agent" },
      component: { kind: "tool", name: "purchase_in_game_skin", version: null },
      tool: {
        name: "purchase_in_game_skin",
        action_type: "write",
        arguments_hash: "sha256:2e91c7a04bd58f16",
        arguments_exposed: false,
        target: "payment_gateway",
        external_side_effect: true,
        reversible: false
      },
      data: { classifications: ["financial"], sources: [], destinations: ["payment_gateway"] },
      approval: { required: true, granted: true, approver_id_hash: null, policy_id: null },
      outcome: { status: "started", duration_ms: null }
    },
    {
      schema_version: "0.1",
      event_id: "c9304e58-9304-42d6-0178-293041526374",
      timestamp: "2026-09-14T18:22:15.640000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "tool_error",
      trace_id: "t-7f3a91c4",
      span_id: "s-0006",
      parent_span_id: "s-0001",
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "tool", name: "send_match_invite", version: null },
      tool: { name: "send_match_invite", action_type: "communicate", arguments_exposed: false, target: "notification_service" },
      data: { classifications: [], sources: [], destinations: ["notification_service"] },
      approval: { required: false, granted: null },
      outcome: { status: "error", duration_ms: 1402, error_type: "UpstreamTimeout" }
    },
    {
      schema_version: "0.1",
      event_id: "d0415f69-0415-42e7-1289-304152637485",
      timestamp: "2026-09-14T18:22:15.910000+00:00",
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      session_id: "sha256:9c1a55de7b3f0142",
      event_type: "chain_end",
      trace_id: "t-7f3a91c4",
      span_id: "s-0001",
      parent_span_id: null,
      source: { type: "custom_function_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "chain", name: "player_support_turn", version: null },
      outcome: { status: "success", duration_ms: 5796, error_type: null }
    }
  ];

  var GAMING = {
    system_id: "gaming-agent-demo",
    system: {
      system_id: "gaming-agent-demo",
      deployment_id: "demo-staging",
      environment: "staging",
      purpose: "In-game player support agent: store purchases, moderation, leaderboard and match invites.",
      owner: "Live Ops Platform Team",
      source: "discovery"
    },
    health: { ok: true, events: 9, database: "static demo fixture" },

    audit_status: {
      system_id: "gaming-agent-demo",
      latest_scan_at: "2026-09-14T17:55:02+00:00",
      active_acap_version: 2,
      acap_generated_at: "2026-09-14T18:04:41+00:00",
      latest_runtime_event_at: "2026-09-14T18:22:15.910000+00:00",
      latest_assessment_at: "2026-09-14T18:31:07+00:00",
      needs_reapproval_count: 0,
      status: "up_to_date",
      next_action: "No action required. Scan, ACAP, runtime evidence and assessment are aligned."
    },

    discovery: {
      upload_id: "UP-3f81c0a4e2b9",
      system_id: "gaming-agent-demo",
      scanner_version: "0.1.0",
      schema_version: "0.1",
      project_hash: "sha256:bcc3272b8514d5864697c579c8d8411053333652682b07266c7ec6fb55fa38a9",
      uploaded_at: "2026-09-14T17:55:02+00:00",
      scan_summary: {
        files_scanned: 34,
        functions_seen: 218,
        candidates_found: 4,
        model_surface_found: 1,
        high_risk_count: 2,
        medium_risk_count: 2,
        low_risk_count: 0,
        ignored_helpers_count: 194,
        unenumerated_surface: []
      },
      model_surface: [
        {
          name: "generate_npc_dialogue",
          provider: "openai",
          category: "model_usage",
          file_path: "app.py",
          line: 71,
          module_path: "app",
          call_chain: ["generate_npc_dialogue -> openai.chat.completions.create"]
        }
      ],
      capabilities: [
        {
          capability_id: "CAP-a41c7e90b2d5",
          upload_id: "UP-3f81c0a4e2b9",
          name: "purchase_in_game_skin",
          module_path: "app",
          file_path: "app.py",
          line_start: 44,
          line_end: 47,
          suggested_action_type: "write",
          suggested_data_classes: ["financial"],
          suggested_approval_required: true,
          external_side_effect: true,
          risk: "high",
          confidence: 0.95,
          confidence_source: "sink_reachability",
          evidence: [
            { type: "sink_call", detail: "payment_gateway.purchase_skin", file_path: "app.py", line: 45 },
            { type: "route", detail: "POST /store/purchase-skin", file_path: "app.py", line: 83 }
          ],
          call_chain: ["purchase_in_game_skin -> payment_gateway.purchase_skin"],
          review_status: "approved_for_acap",
          source: "deterministic_scanner"
        },
        {
          capability_id: "CAP-b52d8fa1c3e6",
          upload_id: "UP-3f81c0a4e2b9",
          name: "ban_toxic_player",
          module_path: "app",
          file_path: "app.py",
          line_start: 50,
          line_end: 53,
          suggested_action_type: "write",
          suggested_data_classes: ["account"],
          suggested_approval_required: true,
          external_side_effect: true,
          risk: "high",
          confidence: 0.9,
          confidence_source: "sink_reachability",
          evidence: [
            { type: "sink_call", detail: "moderation_service.ban_player", file_path: "app.py", line: 51 },
            { type: "route", detail: "POST /moderation/ban-player", file_path: "app.py", line: 88 }
          ],
          call_chain: ["ban_toxic_player -> moderation_service.ban_player"],
          review_status: "rejected",
          source: "deterministic_scanner"
        },
        {
          capability_id: "CAP-c63e90b2d4f7",
          upload_id: "UP-3f81c0a4e2b9",
          name: "update_leaderboard_score",
          module_path: "app",
          file_path: "app.py",
          line_start: 56,
          line_end: 58,
          suggested_action_type: "write",
          suggested_data_classes: [],
          suggested_approval_required: false,
          external_side_effect: false,
          risk: "medium",
          confidence: 0.7,
          confidence_source: "route_and_name",
          evidence: [
            { type: "name_heuristic", detail: "function name 'update_leaderboard_score' matches risky pattern", file_path: "app.py", line: 56 },
            { type: "route", detail: "POST /leaderboard/update-score", file_path: "app.py", line: 93 }
          ],
          call_chain: ["update_leaderboard_score -> leaderboard_db.update_score"],
          review_status: "approved_for_acap",
          source: "deterministic_scanner"
        },
        {
          capability_id: "CAP-d74fa1c3e508",
          upload_id: "UP-3f81c0a4e2b9",
          name: "send_match_invite",
          module_path: "app",
          file_path: "app.py",
          line_start: 62,
          line_end: 65,
          suggested_action_type: "communicate",
          suggested_data_classes: [],
          suggested_approval_required: false,
          external_side_effect: true,
          risk: "medium",
          confidence: 0.7,
          confidence_source: "route_and_name",
          evidence: [
            { type: "name_heuristic", detail: "function name 'send_match_invite' matches communicate pattern", file_path: "app.py", line: 62 },
            { type: "route", detail: "POST /match/invite", file_path: "app.py", line: 98 }
          ],
          call_chain: ["send_match_invite -> notification_service.send_push"],
          review_status: "approved_for_acap",
          source: "deterministic_scanner"
        }
      ]
    },

    acap: {
      acap_id: "gaming-agent-demo-reviewed",
      status: "reviewed",
      reviewed_at: "2026-09-14T18:04:41+00:00",
      reviewed_by: "Live Ops Platform Team",
      prohibited_action_count: 1,
      approval_required_tools: ["purchase_in_game_skin"],
      content_policy: { raw_prompts: false, raw_outputs: false, tool_values: "sanitized_summary" },
      contract: { governance_event_schema: "schemas/governance-event.schema.json" }
    },

    acap_versions: [
      { acap_version_id: "ACAP-gaming-agent-demo-v2", version_number: 2, generated_at: "2026-09-14T18:04:41+00:00" },
      { acap_version_id: "ACAP-gaming-agent-demo-v1", version_number: 1, generated_at: "2026-09-13T11:18:26+00:00" }
    ],

    acap_draft: {
      tools: [
        { name: "purchase_in_game_skin", action_type: "write", approval_required: true, observed_uses: 1, authorization: "allowed_with_approval" },
        { name: "ban_toxic_player", action_type: "write", approval_required: true, observed_uses: 1, authorization: "prohibited" },
        { name: "update_leaderboard_score", action_type: "write", approval_required: false, observed_uses: 1, authorization: "allowed" },
        { name: "send_match_invite", action_type: "communicate", approval_required: false, observed_uses: 1, authorization: "allowed" }
      ]
    },

    coverage: { system_id: "gaming-agent-demo", event_count: 9, fields: coverageFields() },

    events: GAMING_EVENTS,

    findings: [
      Object.assign({
        finding_id: "F-4a7b91c0d2e3",
        rule_id: "R_ACAP_denied_observed",
        acap_id: "ACAP-gaming-agent-demo-v2",
        acap_version_id: "ACAP-gaming-agent-demo-v2",
        acap_version_number: 2,
        violates: "ACAP_authorization",
        severity: "high",
        session: "sha256:9c1a55de7b3f0142",
        event_ids: ["a7182c36-7182-42b4-ef56-071829304152"],
        trace_ids: ["t-7f3a91c4"],
        capability_id: "CAP-b52d8fa1c3e6",
        capability_name: "ban_toxic_player",
        description:
          "Tool 'ban_toxic_player' was observed at runtime but is explicitly denied in ACAP v2 (ACAP-gaming-agent-demo-v2)."
      }, AUTH_CONTROL),
      Object.assign({
        finding_id: "F-8c2d45e6f701",
        rule_id: "R_ACAP_approval_required_missing",
        acap_id: "ACAP-gaming-agent-demo-v2",
        acap_version_id: "ACAP-gaming-agent-demo-v2",
        acap_version_number: 2,
        violates: "ACAP_authorization",
        severity: "high",
        session: "sha256:9c1a55de7b3f0142",
        event_ids: ["b8293d47-8293-42c5-f067-182930415263"],
        trace_ids: ["t-7f3a91c4"],
        capability_id: "CAP-a41c7e90b2d5",
        capability_name: "purchase_in_game_skin",
        description:
          "Tool 'purchase_in_game_skin' requires approval per ACAP v2, but no trusted approval evidence was observed. approval.granted alone is not trusted."
      }, AUTH_CONTROL)
    ],

    risk_profile: {
      use_case: "In-game player support agent with store, moderation and social actions",
      environment: "staging",
      authority_level: "delegated",
      autonomy_level: "human_on_loop",
      data_sensitivity: "high",
      external_side_effects: true,
      human_approval_model: "required_for_writes",
      jurisdiction: "global"
    },

    framework_applicability: frameworkApplicability("agent purchase and moderation authority"),

    assessment: {
      assessment_id: "A-5b91c7e024af",
      system_id: "gaming-agent-demo",
      assessed_at: "2026-09-14T18:31:07+00:00",
      acap_status: "reviewed",
      overall_status: "requires_remediation",
      evidence_confidence: "low",
      evidence_summary: {
        event_count: 9,
        coverage: { captured: 10, partial: 2, annotation_required: 2, missing: 1, total_fields: 17 }
      },
      findings_summary: {
        total: 2,
        by_severity: { high: 2 },
        failed_controls: ["AGT-AUTH-001"]
      },
      framework_status: [
        { framework: "ACAP", status: "failed" },
        { framework: "OWASP Agentic", status: "failed" },
        { framework: "NIST AI RMF", status: "needs_review" },
        { framework: "EU AI Act", status: "not_applicable" },
        { framework: "ISO/IEC 42001", status: "informational" }
      ],
      recommended_next_actions: [
        "Remediate high-severity findings before next assessment",
        "Implement a verified approval mechanism for purchase_in_game_skin",
        "Investigate why the denied tool ban_toxic_player is still reachable at runtime",
        "Add instrumentation for missing evidence fields",
        "Complete manual annotations for annotation-required fields"
      ]
    }
  };

  /* ============================================================
     SYSTEM 2 — support-api  (secondary, shows a different audit state)
     ============================================================ */

  var SUPPORT_EVENTS = [
    {
      schema_version: "0.1",
      event_id: "1a2b3c4d-1111-4222-8333-444455556666",
      timestamp: "2026-09-12T09:14:02.330000+00:00",
      system_id: "support-api",
      deployment_id: "local-test",
      environment: "local",
      session_id: "sha256:5c7b0c9b18ae4402",
      event_type: "chain_start",
      trace_id: "t-4662c404",
      span_id: "s-1001",
      parent_span_id: null,
      source: { type: "fastapi_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "support-api", identity_type: "logical_agent" },
      component: { kind: "chain", name: "support_request", version: null },
      outcome: { status: "started", duration_ms: null }
    },
    {
      schema_version: "0.1",
      event_id: "2b3c4d5e-2222-4333-8444-555566667777",
      timestamp: "2026-09-12T09:14:03.118000+00:00",
      system_id: "support-api",
      deployment_id: "local-test",
      environment: "local",
      session_id: "sha256:5c7b0c9b18ae4402",
      event_type: "llm_end",
      trace_id: "t-4662c404",
      span_id: "s-1002",
      parent_span_id: "s-1001",
      source: { type: "fastapi_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "chat_model", name: "draft_reply", version: null },
      model: { provider: "openai", name: "gpt-4.1-mini" },
      prompt: { template_hash: "sha256:70cd1a8b4e2f9013", content_capture: "hash", message_count: 2 },
      outcome: { status: "success", duration_ms: 788, error_type: null, input_tokens: 421, output_tokens: 96, total_tokens: 517 }
    },
    {
      /* approval required, claimed but unverified */
      schema_version: "0.1",
      event_id: "3c4d5e6f-3333-4444-8555-666677778888",
      timestamp: "2026-09-12T09:14:04.908000+00:00",
      system_id: "support-api",
      deployment_id: "local-test",
      environment: "local",
      session_id: "sha256:5c7b0c9b18ae4402",
      event_type: "tool_start",
      trace_id: "t-4662c404",
      span_id: "s-1003",
      parent_span_id: "s-1001",
      source: { type: "fastapi_adapter", library: "ai_governance", library_version: "0.1" },
      actor: { agent_id: "support-api", identity_type: "logical_agent" },
      component: { kind: "tool", name: "refund_execute", version: null },
      tool: {
        name: "refund_execute",
        action_type: "write",
        arguments_hash: "sha256:e715d783a1420c96",
        arguments_exposed: false,
        target: "payment_provider",
        external_side_effect: true,
        reversible: false
      },
      data: { classifications: ["financial"], sources: [], destinations: ["payment_provider"] },
      approval: { required: true, granted: true, approver_id_hash: null, policy_id: null },
      outcome: { status: "started", duration_ms: null }
    },
    {
      schema_version: "0.1",
      event_id: "4d5e6f70-4444-4555-8666-777788889999",
      timestamp: "2026-09-12T09:14:05.221000+00:00",
      system_id: "support-api",
      deployment_id: "local-test",
      environment: "local",
      session_id: "sha256:5c7b0c9b18ae4402",
      event_type: "tool_end",
      trace_id: "t-4662c404",
      span_id: "s-1003",
      parent_span_id: "s-1001",
      source: { type: "fastapi_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "tool", name: "refund_execute", version: null },
      tool: { name: "refund_execute", action_type: "write", arguments_exposed: false },
      outcome: { status: "success", duration_ms: 313, error_type: null }
    },
    {
      schema_version: "0.1",
      event_id: "5e6f7081-5555-4666-8777-88889999aaaa",
      timestamp: "2026-09-12T09:14:05.640000+00:00",
      system_id: "support-api",
      deployment_id: "local-test",
      environment: "local",
      session_id: "sha256:5c7b0c9b18ae4402",
      event_type: "chain_end",
      trace_id: "t-4662c404",
      span_id: "s-1001",
      parent_span_id: null,
      source: { type: "fastapi_adapter", library: "ai_governance", library_version: "0.1" },
      component: { kind: "chain", name: "support_request", version: null },
      outcome: { status: "success", duration_ms: 3310, error_type: null }
    }
  ];

  var SUPPORT = {
    system_id: "support-api",
    system: {
      system_id: "support-api",
      deployment_id: "local-test",
      environment: "local",
      purpose: "Customer support API agent that drafts replies and executes refunds.",
      owner: "Customer Operations",
      source: "registry"
    },
    health: { ok: true, events: 5, database: "static demo fixture" },

    audit_status: {
      system_id: "support-api",
      latest_scan_at: "2026-09-12T08:40:11+00:00",
      active_acap_version: 1,
      acap_generated_at: "2026-09-12T08:52:30+00:00",
      latest_runtime_event_at: "2026-09-12T09:14:05.640000+00:00",
      latest_assessment_at: "2026-09-12T09:20:44+00:00",
      needs_reapproval_count: 1,
      status: "needs_reapproval",
      next_action: "1 capability changed since approval. Re-review and regenerate the ACAP version."
    },

    discovery: {
      upload_id: "UP-90ab12cd34ef",
      system_id: "support-api",
      scanner_version: "0.1.0",
      schema_version: "0.1",
      project_hash: "sha256:7a1de4498cb20f6631d0a5be0c7f2e5488ab19cc0d3e6f7182930415263748596",
      uploaded_at: "2026-09-12T08:40:11+00:00",
      scan_summary: {
        files_scanned: 12,
        functions_seen: 96,
        candidates_found: 3,
        model_surface_found: 1,
        high_risk_count: 1,
        medium_risk_count: 1,
        low_risk_count: 1,
        ignored_helpers_count: 82,
        unenumerated_surface: []
      },
      model_surface: [
        {
          name: "draft_reply",
          provider: "openai",
          category: "model_usage",
          file_path: "app.py",
          line: 38,
          module_path: "app",
          call_chain: ["draft_reply -> openai.chat.completions.create"]
        }
      ],
      capabilities: [
        {
          capability_id: "CAP-0ce6a9aaa99a",
          upload_id: "UP-90ab12cd34ef",
          name: "refund_execute",
          module_path: "app",
          file_path: "app.py",
          line_start: 46,
          line_end: 49,
          suggested_action_type: "write",
          suggested_data_classes: ["financial"],
          suggested_approval_required: true,
          external_side_effect: true,
          risk: "high",
          confidence: 0.95,
          confidence_source: "sink_reachability",
          evidence: [
            { type: "sink_call", detail: "payment_provider.refunds.create", file_path: "app.py", line: 48 },
            { type: "route", detail: "POST /refund", file_path: "app.py", line: 46 }
          ],
          call_chain: ["refund_execute -> payment_provider.refunds.create"],
          review_status: "needs_reapproval",
          source: "deterministic_scanner"
        },
        {
          capability_id: "CAP-cc82f085d3aa",
          upload_id: "UP-90ab12cd34ef",
          name: "send_invoice_email",
          module_path: "app",
          file_path: "app.py",
          line_start: 53,
          line_end: 56,
          suggested_action_type: "communicate",
          suggested_data_classes: ["contact"],
          suggested_approval_required: true,
          external_side_effect: true,
          risk: "medium",
          confidence: 0.7,
          confidence_source: "route_and_name",
          evidence: [
            { type: "name_heuristic", detail: "function name 'send_invoice_email' matches communicate pattern", file_path: "app.py", line: 53 }
          ],
          call_chain: ["send_invoice_email -> mail_provider.send"],
          review_status: "approved_for_acap",
          source: "deterministic_scanner"
        },
        {
          capability_id: "CAP-e1f2a3b4c5d6",
          upload_id: "UP-90ab12cd34ef",
          name: "lookup_order_status",
          module_path: "app",
          file_path: "app.py",
          line_start: 60,
          line_end: 62,
          suggested_action_type: "read",
          suggested_data_classes: [],
          suggested_approval_required: false,
          external_side_effect: false,
          risk: "low",
          confidence: 0.5,
          confidence_source: "name_heuristic",
          evidence: [
            { type: "name_heuristic", detail: "function name 'lookup_order_status' matches read pattern", file_path: "app.py", line: 60 }
          ],
          call_chain: ["lookup_order_status -> orders_db.get"],
          review_status: "pending",
          source: "deterministic_scanner"
        }
      ]
    },

    acap: {
      acap_id: "support-api-reviewed",
      status: "reviewed",
      reviewed_at: "2026-09-12T08:52:30+00:00",
      reviewed_by: "Customer Operations",
      prohibited_action_count: 0,
      approval_required_tools: ["refund_execute", "send_invoice_email"],
      content_policy: { raw_prompts: false, raw_outputs: false, tool_values: "sanitized_summary" },
      contract: { governance_event_schema: "schemas/governance-event.schema.json" }
    },

    acap_versions: [
      { acap_version_id: "ACAP-support-api-v1", version_number: 1, generated_at: "2026-09-12T08:52:30+00:00" }
    ],

    acap_draft: {
      tools: [
        { name: "refund_execute", action_type: "write", approval_required: true, observed_uses: 1, authorization: "allowed_with_approval" },
        { name: "send_invoice_email", action_type: "communicate", approval_required: true, observed_uses: 0, authorization: "allowed_with_approval" },
        { name: "lookup_order_status", action_type: "read", approval_required: false, observed_uses: 0, authorization: "unresolved" }
      ]
    },

    coverage: {
      system_id: "support-api",
      event_count: 5,
      fields: coverageFields({
        "token usage": { status: "partial", presence: 0.2, note: "Only one model event in this window." }
      })
    },

    events: SUPPORT_EVENTS,

    findings: [
      Object.assign({
        finding_id: "F-1d3e5f708291",
        rule_id: "R_ACAP_approval_required_missing",
        acap_id: "ACAP-support-api-v1",
        acap_version_id: "ACAP-support-api-v1",
        acap_version_number: 1,
        violates: "ACAP_authorization",
        severity: "high",
        session: "sha256:5c7b0c9b18ae4402",
        event_ids: ["3c4d5e6f-3333-4444-8555-666677778888"],
        trace_ids: ["t-4662c404"],
        capability_id: "CAP-0ce6a9aaa99a",
        capability_name: "refund_execute",
        description:
          "Tool 'refund_execute' requires approval per ACAP v1, but no trusted approval evidence was observed. approval.granted alone is not trusted."
      }, AUTH_CONTROL)
    ],

    risk_profile: {
      use_case: "Customer support agent with refund authority",
      environment: "local",
      authority_level: "delegated",
      autonomy_level: "human_in_loop",
      data_sensitivity: "high",
      external_side_effects: true,
      human_approval_model: "required_for_writes",
      jurisdiction: "global"
    },

    framework_applicability: frameworkApplicability("agent refund authority"),

    assessment: {
      assessment_id: "A-2f4061837a5c",
      system_id: "support-api",
      assessed_at: "2026-09-12T09:20:44+00:00",
      acap_status: "reviewed",
      overall_status: "requires_remediation",
      evidence_confidence: "low",
      evidence_summary: {
        event_count: 5,
        coverage: { captured: 10, partial: 2, annotation_required: 2, missing: 1, total_fields: 17 }
      },
      findings_summary: {
        total: 1,
        by_severity: { high: 1 },
        failed_controls: ["AGT-AUTH-001"]
      },
      framework_status: [
        { framework: "ACAP", status: "failed" },
        { framework: "OWASP Agentic", status: "needs_review" },
        { framework: "NIST AI RMF", status: "needs_review" },
        { framework: "EU AI Act", status: "not_applicable" },
        { framework: "ISO/IEC 42001", status: "informational" }
      ],
      recommended_next_actions: [
        "Remediate high-severity findings before next assessment",
        "Complete ACAP review for all discovered tools",
        "Re-review refund_execute: it changed since the last approval",
        "Add instrumentation for missing evidence fields"
      ]
    }
  };

  window.AGENTGOV_DEMO = {
    generated_at: "2026-09-15T00:00:00+00:00",
    note: "Static stakeholder demo fixture. Synthetic data only. No backend.",
    systems: [GAMING, SUPPORT]
  };
})();
