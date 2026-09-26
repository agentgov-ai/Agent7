"""Demo application for the governance codebase scanner."""

from __future__ import annotations

from datetime import datetime
from fastapi import FastAPI

app = FastAPI()


# Fake external SDKs so this demo runs without installing stripe/openai/anthropic.

class stripe:
    class refunds:
        @staticmethod
        def create(charge: str, amount: int) -> dict:
            return {"id": "rfnd_demo", "charge": charge, "amount": amount}


class email_client:
    @staticmethod
    def send(to: str, body: str) -> dict:
        return {"status": "sent", "to": to}


class openai:
    class chat:
        class completions:
            @staticmethod
            def create(model: str, messages: list[dict]) -> object:
                class Msg:
                    content = "demo response"

                class Choice:
                    message = Msg()

                class Resp:
                    choices = [Choice()]

                return Resp()


class anthropic:
    class Anthropic:
        class messages:
            @staticmethod
            def create(model: str, max_tokens: int, messages: list[dict]) -> object:
                class Content:
                    text = "demo analysis"

                class Msg:
                    content = [Content()]

                return Msg()


class _FakeSession:
    def delete(self, obj: object) -> None:
        pass

    def commit(self) -> None:
        pass

    def query(self, *args: object) -> object:
        return self

    def filter_by(self, **kwargs: object) -> object:
        return self

    def first(self) -> object:
        return {"id": "demo-customer"}


session = _FakeSession()


def refund_execute(order_id: str, amount: int) -> dict[str, str]:
    stripe.refunds.create(charge=order_id, amount=amount)
    return {"status": "refunded"}


def send_invoice_email(recipient: str, body: str) -> dict[str, str]:
    email_client.send(to=recipient, body=body)
    return {"status": "sent"}


def delete_customer(customer_id: str) -> dict[str, str]:
    customer = session.query("Customer").filter_by(id=customer_id).first()
    if customer:
        session.delete(customer)
        session.commit()
    return {"status": "deleted"}


@app.post("/refund")
def refund_endpoint() -> dict[str, str]:
    return refund_execute(order_id="ORD-001", amount=2599)


@app.post("/invoice")
def invoice_endpoint() -> dict[str, str]:
    return send_invoice_email(
        recipient="user@example.com",
        body="Your invoice is ready",
    )


@app.delete("/customer/{customer_id}")
def delete_customer_endpoint(customer_id: str) -> dict[str, str]:
    return delete_customer(customer_id)


def generate_reply(prompt: str) -> str:
    resp = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def analyze_text(text: str) -> str:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": text}],
    )
    return msg.content[0].text


def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")