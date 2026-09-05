"""Demo application functions — no decorators, no SDK imports.

These functions are instrumented dynamically via governance.yaml.
"""
from __future__ import annotations


def process_refund(order_id: str, amount: int) -> dict:
    """Process a refund — approved capability, will be wrapped."""
    return {"refunded": True, "order_id": order_id, "amount": amount}


def send_notification(recipient: str, message: str) -> str:
    """Send a notification — approved capability, will be wrapped."""
    return f"Sent to {recipient}"


def internal_helper() -> str:
    """Internal helper — pending status, will NOT be wrapped."""
    return "helper result"
