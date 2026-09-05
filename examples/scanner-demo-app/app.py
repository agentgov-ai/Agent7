"""Demo application for the governance codebase scanner.

This file contains functions with known consequential sinks, FastAPI routes,
model-usage calls, and pure helpers.  Running the scanner against this
directory should produce a ``governance-discovery.json`` that:

- flags ``refund_execute`` as high-risk financial write
- flags ``send_invoice_email`` as high-risk communicate
- flags ``delete_customer`` as medium-risk delete
- records ``generate_reply`` and ``analyze_text`` as model-usage surface
- ignores ``format_date`` (pure helper)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Framework / SDK imports (scanner resolves these via the import-alias map)
# ---------------------------------------------------------------------------
import smtplib
from datetime import datetime
from email.message import EmailMessage

import anthropic  # type: ignore[import-untyped]
import openai  # type: ignore[import-untyped]
import stripe  # type: ignore[import-untyped]
from fastapi import FastAPI

# Fake ORM session stand-in
class _FakeSession:
    def delete(self, obj: object) -> None: ...
    def commit(self) -> None: ...
    def query(self, *a: object) -> object: return self  # type: ignore[return-value]
    def filter_by(self, **kw: object) -> object: return self  # type: ignore[return-value]
    def first(self) -> object: return None

session = _FakeSession()

app = FastAPI()


# ---------------------------------------------------------------------------
# Business capabilities (should be flagged as candidates)
# ---------------------------------------------------------------------------

@app.post("/refund")
def refund_execute(order_id: str, amount: int) -> dict[str, str]:
    """Process a refund via Stripe — high-risk financial write."""
    stripe.refunds.create(charge=order_id, amount=amount)
    return {"status": "refunded"}


@app.post("/invoice")
def send_invoice_email(recipient: str, body: str) -> dict[str, str]:
    """Send an invoice email — high-risk communicate."""
    msg = EmailMessage()
    msg["To"] = recipient
    msg.set_content(body)
    with smtplib.SMTP("localhost") as server:
        server.send_message(msg)
    return {"status": "sent"}


@app.delete("/customer/{customer_id}")
def delete_customer(customer_id: str) -> dict[str, str]:
    """Remove a customer record — medium-risk delete."""
    customer = session.query("Customer").filter_by(id=customer_id).first()
    if customer:
        session.delete(customer)
        session.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Model-usage surface (should be recorded separately, not as capabilities)
# ---------------------------------------------------------------------------

def generate_reply(prompt: str) -> str:
    """Call OpenAI — model usage, not a governed business capability."""
    resp = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def analyze_text(text: str) -> str:
    """Call Anthropic — model usage, not a governed business capability."""
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": text}],
    )
    return msg.content[0].text


# ---------------------------------------------------------------------------
# Pure helper (should be ignored by the scanner)
# ---------------------------------------------------------------------------

def format_date(dt: datetime) -> str:
    """Format a datetime — no sinks, no risk, should be ignored."""
    return dt.strftime("%Y-%m-%d")
