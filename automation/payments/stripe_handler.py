"""
payments/stripe_handler.py — FastAPI endpoint for Stripe webhook events.

Verifies the Stripe-Signature header, handles:
  - checkout.session.completed
  - payment_intent.succeeded
  - payment_intent.payment_failed

Records every confirmed payment in the SQLite ledger and notifies via Telegram.

Mount this router in main.py's FastAPI app.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, status

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["stripe"])

PAYMENTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PAYMENTS_DIR.parent))


def _stripe():
    """Lazy import stripe to avoid hard dependency at module load."""
    try:
        import stripe as _stripe_lib  # type: ignore[import]
        return _stripe_lib
    except ImportError:
        raise ImportError("stripe package not installed. Run: pip install stripe")


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
) -> dict:
    """
    Receive and process Stripe webhook events.

    Stripe sends events here when payments occur. We verify the signature,
    extract payment data, record it in the ledger, and notify Telegram.
    """
    from config import cfg  # noqa: PLC0415
    from payments.payment_manager import notify_telegram_payment, record_payment  # noqa: PLC0415

    if not cfg.STRIPE_WEBHOOK_SECRET:
        log.warning("STRIPE_WEBHOOK_SECRET not configured — webhook will not be verified.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret not configured on server.",
        )

    stripe = _stripe()
    stripe.api_key = cfg.STRIPE_SECRET_KEY

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, cfg.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        log.warning("Stripe webhook signature verification failed.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature.",
        )
    except Exception as exc:
        log.error("Stripe webhook parse error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    event_type = event["type"]
    log.info("Stripe event received: %s (id=%s)", event_type, event["id"])

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        amount_total = (session.get("amount_total") or 0) / 100  # cents → dollars
        currency = (session.get("currency") or "usd").upper()
        customer_email = session.get("customer_email") or ""
        site = session.get("metadata", {}).get("site", "")

        row_id = record_payment(
            source="stripe",
            amount=amount_total,
            currency=currency,
            site=site,
            status="confirmed",
            tx_id=f"cs_{session['id']}",
            metadata={
                "event_id": event["id"],
                "session_id": session["id"],
                "customer_email": customer_email,
                "payment_status": session.get("payment_status"),
            },
        )
        log.info("Checkout session payment recorded (id=%d): %.2f %s", row_id, amount_total, currency)
        asyncio.create_task(
            notify_telegram_payment("stripe", amount_total, currency, site, tx_id=session["id"])
        )

    elif event_type == "payment_intent.succeeded":
        pi = event["data"]["object"]
        amount = (pi.get("amount_received") or 0) / 100
        currency = (pi.get("currency") or "usd").upper()
        site = pi.get("metadata", {}).get("site", "")

        row_id = record_payment(
            source="stripe",
            amount=amount,
            currency=currency,
            site=site,
            status="confirmed",
            tx_id=f"pi_{pi['id']}",
            metadata={"event_id": event["id"], "payment_intent_id": pi["id"]},
        )
        log.info("PaymentIntent recorded (id=%d): %.2f %s", row_id, amount, currency)
        asyncio.create_task(
            notify_telegram_payment("stripe", amount, currency, site, tx_id=pi["id"])
        )

    elif event_type == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        log.warning(
            "Stripe payment failed: %s — %s",
            pi["id"],
            pi.get("last_payment_error", {}).get("message", "unknown reason"),
        )
        record_payment(
            source="stripe",
            amount=(pi.get("amount") or 0) / 100,
            currency=(pi.get("currency") or "usd").upper(),
            site=pi.get("metadata", {}).get("site", ""),
            status="failed",
            tx_id=f"pifail_{pi['id']}",
            metadata={"event_id": event["id"]},
        )

    else:
        log.debug("Unhandled Stripe event type: %s", event_type)

    return {"received": True, "event": event_type}
