"""
payments/paypal_handler.py — FastAPI endpoint for PayPal webhook events.

Verifies PayPal webhook signatures using the PayPal REST SDK (or manual HTTPS
verification), handles:
  - PAYMENT.CAPTURE.COMPLETED
  - PAYMENT.SALE.COMPLETED
  - PAYMENT.CAPTURE.DENIED / PAYMENT.CAPTURE.REFUNDED

Records confirmed payments in the SQLite ledger and notifies via Telegram.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["paypal"])

PAYMENTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PAYMENTS_DIR.parent))


# ---------------------------------------------------------------------------
# PayPal signature verification
# ---------------------------------------------------------------------------

def _get_paypal_access_token(client_id: str, secret: str, base_url: str) -> str:
    """Obtain a PayPal OAuth2 access token."""
    credentials = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    req = urllib.request.Request(
        f"{base_url}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data["access_token"]


def _verify_paypal_webhook(
    headers: dict[str, str],
    body: bytes,
    webhook_id: str,
    client_id: str,
    secret: str,
    base_url: str,
) -> bool:
    """
    Verify PayPal webhook signature via the PayPal REST API.
    https://developer.paypal.com/api/webhooks/v1/#verify-webhook-signature
    """
    try:
        access_token = _get_paypal_access_token(client_id, secret, base_url)
        payload = json.dumps({
            "auth_algo": headers.get("paypal-auth-algo", ""),
            "cert_id": headers.get("paypal-cert-url", ""),
            "transmission_id": headers.get("paypal-transmission-id", ""),
            "transmission_sig": headers.get("paypal-transmission-sig", ""),
            "transmission_time": headers.get("paypal-transmission-time", ""),
            "webhook_id": webhook_id,
            "webhook_event": json.loads(body),
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/v1/notifications/verify-webhook-signature",
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        status_val = result.get("verification_status", "")
        log.debug("PayPal signature verification status: %s", status_val)
        return status_val == "SUCCESS"
    except Exception as exc:
        log.warning("PayPal signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/paypal")
async def paypal_webhook(request: Request) -> dict[str, Any]:
    """
    Receive and process PayPal webhook events.

    PayPal sends POST requests here with JSON bodies. We verify the signature,
    parse the event type, record the payment, and send a Telegram notification.
    """
    from config import cfg  # noqa: PLC0415
    from payments.payment_manager import notify_telegram_payment, record_payment  # noqa: PLC0415

    if not (cfg.PAYPAL_CLIENT_ID and cfg.PAYPAL_SECRET and cfg.PAYPAL_WEBHOOK_ID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PayPal not configured on server.",
        )

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Determine base URL
    base_url = (
        "https://api-m.sandbox.paypal.com"
        if cfg.PAYPAL_ENV == "sandbox"
        else "https://api-m.paypal.com"
    )

    # Verify signature
    valid = _verify_paypal_webhook(
        headers=headers,
        body=body,
        webhook_id=cfg.PAYPAL_WEBHOOK_ID,
        client_id=cfg.PAYPAL_CLIENT_ID,
        secret=cfg.PAYPAL_SECRET,
        base_url=base_url,
    )

    if not valid:
        log.warning("PayPal webhook signature verification failed.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PayPal signature verification failed.",
        )

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {exc}",
        )

    event_type = event.get("event_type", "UNKNOWN")
    event_id = event.get("id", "")
    log.info("PayPal event received: %s (id=%s)", event_type, event_id)

    resource = event.get("resource", {})

    if event_type in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.SALE.COMPLETED"):
        amount_info = resource.get("amount", resource.get("gross_amount", {}))
        amount = float(amount_info.get("value", 0))
        currency = amount_info.get("currency_code", "USD").upper()
        site = resource.get("custom_id", "")  # custom_id carries site domain
        payer_email = (
            resource.get("payer", {}).get("email_address", "")
            or resource.get("payee", {}).get("email_address", "")
        )

        row_id = record_payment(
            source="paypal",
            amount=amount,
            currency=currency,
            site=site,
            status="confirmed",
            tx_id=f"pp_{event_id}",
            metadata={
                "event_type": event_type,
                "resource_id": resource.get("id", ""),
                "payer_email": payer_email,
            },
        )
        log.info("PayPal payment recorded (id=%d): %.2f %s", row_id, amount, currency)
        asyncio.create_task(
            notify_telegram_payment("paypal", amount, currency, site, tx_id=event_id)
        )

    elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED"):
        amount_info = resource.get("amount", {})
        amount = float(amount_info.get("value", 0))
        currency = amount_info.get("currency_code", "USD").upper()
        record_payment(
            source="paypal",
            amount=amount,
            currency=currency,
            site="",
            status="failed" if "DENIED" in event_type else "refunded",
            tx_id=f"pp_{event_id}_denied",
            metadata={"event_type": event_type},
        )
        log.warning("PayPal event %s recorded as failed/refunded.", event_type)

    else:
        log.debug("Unhandled PayPal event: %s", event_type)

    return {"received": True, "event": event_type}
