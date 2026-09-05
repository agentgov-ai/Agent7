from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Sink catalog
# ---------------------------------------------------------------------------
# Each entry maps a dotted call-chain pattern to governance metadata.
#
# "pattern":  tuple of name segments.  A trailing "*" matches any suffix.
# "sql_write_check":  when True the matcher inspects the first string arg
#                     for INSERT / UPDATE / DELETE / DROP keywords.
# ---------------------------------------------------------------------------

SINK_CATALOG: list[dict[str, Any]] = [
    # ── payment / refund ──────────────────────────────────────────────
    {"pattern": ("stripe", "refunds", "create"),      "action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},
    {"pattern": ("stripe", "charges", "create"),       "action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},
    {"pattern": ("stripe", "PaymentIntent", "create"), "action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},
    {"pattern": ("stripe", "PaymentIntent", "confirm"),"action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},
    {"pattern": ("stripe", "Subscription", "create"),  "action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},
    {"pattern": ("paypal", "*"),                       "action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},
    {"pattern": ("braintree", "*"),                    "action_type": "write",       "data_classes": ["financial"], "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "payment"},

    # ── email / communication ─────────────────────────────────────────
    {"pattern": ("smtplib", "SMTP", "send_message"),   "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("smtplib", "SMTP", "sendmail"),       "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("smtplib", "SMTP_SSL", "send_message"),"action_type": "communicate","data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("smtplib", "SMTP_SSL", "sendmail"),   "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("sendgrid", "*"),                     "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("ses", "send_email"),                 "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("ses", "send_raw_email"),             "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "email"},
    {"pattern": ("twilio", "*"),                       "action_type": "communicate", "data_classes": ["contact"],   "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "communication"},
    {"pattern": ("slack_sdk", "*"),                    "action_type": "communicate", "data_classes": ["contact"],   "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "communication"},

    # ── database write / delete ───────────────────────────────────────
    {"pattern": ("cursor", "execute"),                 "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database", "sql_write_check": True},
    {"pattern": ("session", "add"),                    "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("session", "commit"),                 "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("session", "delete"),                 "action_type": "delete",      "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("session", "flush"),                  "action_type": "write",       "data_classes": ["database"],  "risk": "low",    "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "insert_one"),          "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "insert_many"),         "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "update_one"),          "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "update_many"),         "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "delete_one"),          "action_type": "delete",      "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "delete_many"),         "action_type": "delete",      "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},
    {"pattern": ("collection", "replace_one"),         "action_type": "write",       "data_classes": ["database"],  "risk": "medium", "approval_required": False, "external_side_effect": False, "category": "database"},

    # ── HTTP outbound ─────────────────────────────────────────────────
    {"pattern": ("requests", "post"),                  "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("requests", "put"),                   "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("requests", "patch"),                 "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("requests", "delete"),                "action_type": "delete",      "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("httpx", "post"),                     "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("httpx", "put"),                      "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("httpx", "patch"),                    "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("httpx", "delete"),                   "action_type": "delete",      "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},
    {"pattern": ("urllib", "request", "urlopen"),      "action_type": "write",       "data_classes": [],            "risk": "medium", "approval_required": False, "external_side_effect": True,  "category": "http_outbound"},

    # ── filesystem ────────────────────────────────────────────────────
    {"pattern": ("os", "remove"),                      "action_type": "delete",      "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("os", "unlink"),                      "action_type": "delete",      "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("os", "rename"),                      "action_type": "write",       "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("shutil", "rmtree"),                  "action_type": "delete",      "data_classes": ["filesystem"],"risk": "high",   "approval_required": True,  "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("shutil", "move"),                    "action_type": "write",       "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("shutil", "copy"),                    "action_type": "write",       "data_classes": ["filesystem"],"risk": "low",    "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("shutil", "copy2"),                   "action_type": "write",       "data_classes": ["filesystem"],"risk": "low",    "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("Path", "write_text"),                "action_type": "write",       "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("Path", "write_bytes"),               "action_type": "write",       "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},
    {"pattern": ("Path", "unlink"),                    "action_type": "delete",      "data_classes": ["filesystem"],"risk": "medium", "approval_required": False, "external_side_effect": False, "category": "filesystem"},

    # ── subprocess ────────────────────────────────────────────────────
    {"pattern": ("subprocess", "run"),                 "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},
    {"pattern": ("subprocess", "call"),                "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},
    {"pattern": ("subprocess", "Popen"),               "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},
    {"pattern": ("subprocess", "check_call"),          "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},
    {"pattern": ("subprocess", "check_output"),        "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},
    {"pattern": ("os", "system"),                      "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},
    {"pattern": ("os", "popen"),                       "action_type": "execute",     "data_classes": [],            "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "subprocess"},

    # ── cloud SDK ─────────────────────────────────────────────────────
    {"pattern": ("s3", "put_object"),                  "action_type": "write",       "data_classes": ["cloud"],     "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "cloud"},
    {"pattern": ("s3", "delete_object"),               "action_type": "delete",      "data_classes": ["cloud"],     "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "cloud"},
    {"pattern": ("s3", "upload_file"),                 "action_type": "write",       "data_classes": ["cloud"],     "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "cloud"},
    {"pattern": ("sqs", "send_message"),               "action_type": "communicate", "data_classes": ["cloud"],     "risk": "high",   "approval_required": False, "external_side_effect": True,  "category": "cloud"},
    {"pattern": ("sns", "publish"),                    "action_type": "communicate", "data_classes": ["cloud"],     "risk": "high",   "approval_required": False, "external_side_effect": True,  "category": "cloud"},
    {"pattern": ("lambda_client", "invoke"),           "action_type": "execute",     "data_classes": ["cloud"],     "risk": "high",   "approval_required": True,  "external_side_effect": True,  "category": "cloud"},
]

# ── model-usage surface (not business capabilities) ───────────────────
# These are recorded separately as model_surface entries, not as
# governed business capabilities.  A bare openai.chat.completions.create
# is model infrastructure; it only becomes a capability when wrapped in
# a business-meaningful tool/action.

MODEL_USAGE_PATTERNS: list[dict[str, Any]] = [
    {"pattern": ("openai", "*"),                       "provider": "openai",     "category": "model_usage"},
    {"pattern": ("anthropic", "*"),                    "provider": "anthropic",  "category": "model_usage"},
    {"pattern": ("ChatOpenAI", "*"),                   "provider": "openai",     "category": "model_usage"},
    {"pattern": ("ChatAnthropic", "*"),                "provider": "anthropic",  "category": "model_usage"},
    {"pattern": ("litellm", "*"),                      "provider": "litellm",    "category": "model_usage"},
    {"pattern": ("cohere", "*"),                       "provider": "cohere",     "category": "model_usage"},
]


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

_SQL_WRITE_KEYWORDS = frozenset({"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"})


def _pattern_matches(pattern: tuple[str, ...], call_chain: tuple[str, ...]) -> bool:
    """Return True if *pattern* matches *call_chain*.

    A trailing ``"*"`` in *pattern* means "one-or-more additional segments".
    """
    if not pattern or not call_chain:
        return False
    if pattern[-1] == "*":
        prefix = pattern[:-1]
        return len(call_chain) > len(prefix) and call_chain[: len(prefix)] == prefix
    return call_chain == pattern


def match_sink(call_chain: tuple[str, ...]) -> dict[str, Any] | None:
    """Return the first matching sink entry for *call_chain*, or ``None``."""
    for entry in SINK_CATALOG:
        if _pattern_matches(entry["pattern"], call_chain):
            return entry
    return None


def match_model_usage(call_chain: tuple[str, ...]) -> dict[str, Any] | None:
    """Return the first matching model-usage entry, or ``None``."""
    for entry in MODEL_USAGE_PATTERNS:
        if _pattern_matches(entry["pattern"], call_chain):
            return entry
    return None


def is_sql_write(first_arg_value: str | None) -> bool:
    """Check whether a SQL string starts with a write keyword."""
    if not first_arg_value:
        return False
    token = first_arg_value.strip().split()[0].upper() if first_arg_value.strip() else ""
    return token in _SQL_WRITE_KEYWORDS


def all_sinks() -> list[dict[str, Any]]:
    """Return the full sink catalog (for reporting / testing)."""
    return list(SINK_CATALOG)
