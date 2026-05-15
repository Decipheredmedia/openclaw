"""
payments/payment_manager.py — Central payment registry and ledger.

Exposes:
  get_payment_options(site) → dict describing available payment methods for a site
  record_payment(source, amount, currency, metadata) → persists to SQLite ledger
  get_revenue(period) → queries ledger for revenue summaries
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

PAYMENTS_DIR = Path(__file__).resolve().parent
DB_PATH = PAYMENTS_DIR / "ledger.db"


# ---------------------------------------------------------------------------
# Ledger (SQLite)
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_ledger() -> None:
    """Create the payments table if it doesn't exist."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT    NOT NULL,
                source      TEXT    NOT NULL,
                amount      REAL    NOT NULL,
                currency    TEXT    NOT NULL DEFAULT 'USD',
                site        TEXT    NOT NULL DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'confirmed',
                tx_id       TEXT    UNIQUE,
                metadata    TEXT    NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_recorded_at
            ON payments(recorded_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payments_site
            ON payments(site)
        """)
        conn.commit()
    log.info("Payment ledger initialised at %s", DB_PATH)


def record_payment(
    source: str,
    amount: float,
    currency: str = "USD",
    site: str = "",
    status: str = "confirmed",
    tx_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    Record a payment in the SQLite ledger.

    Parameters
    ----------
    source   : 'stripe', 'paypal', 'btc', 'eth', 'usdt'
    amount   : Amount in the given currency (float)
    currency : ISO 4217 code or crypto ticker
    site     : Domain the payment is attributed to
    status   : 'confirmed', 'pending', 'failed'
    tx_id    : Unique transaction / event ID (prevents double-recording)
    metadata : Arbitrary dict stored as JSON

    Returns
    -------
    int — row ID of the inserted payment, or existing row ID if tx_id duplicate.
    """
    init_ledger()
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata or {})

    try:
        with _get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO payments (recorded_at, source, amount, currency, site,
                                      status, tx_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, source, amount, currency, site, status, tx_id, meta_json),
            )
            conn.commit()
            row_id = cur.lastrowid
            log.info(
                "Payment recorded: id=%d source=%s amount=%s %s site=%s tx=%s",
                row_id, source, amount, currency, site, tx_id,
            )
            return row_id
    except sqlite3.IntegrityError:
        # Duplicate tx_id — idempotent; return existing row id
        with _get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM payments WHERE tx_id = ?", (tx_id,)
            ).fetchone()
            return row["id"] if row else -1


def get_revenue(
    period: str = "today",
    site: Optional[str] = None,
) -> dict[str, Any]:
    """
    Summarise revenue from the ledger.

    period: 'today' | 'week' | 'month' | 'all'

    Returns a dict with:
      total_usd_equivalent, by_source, by_currency, payment_count, payments
    """
    init_ledger()
    now = datetime.now(timezone.utc)
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:  # all
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)

    since_iso = since.isoformat()

    with _get_connection() as conn:
        where = "WHERE recorded_at >= ? AND status = 'confirmed'"
        params: list[Any] = [since_iso]
        if site:
            where += " AND site = ?"
            params.append(site)

        rows = conn.execute(
            f"SELECT * FROM payments {where} ORDER BY recorded_at DESC",
            params,
        ).fetchall()

    by_source: dict[str, float] = {}
    by_currency: dict[str, float] = {}
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0.0) + row["amount"]
        by_currency[row["currency"]] = by_currency.get(row["currency"], 0.0) + row["amount"]

    # Best-effort USD total (only USD and USDT are counted directly)
    usd_total = by_currency.get("USD", 0.0) + by_currency.get("USDT", 0.0)

    return {
        "period": period,
        "since": since_iso,
        "payment_count": len(rows),
        "total_usd_equivalent": round(usd_total, 2),
        "by_source": by_source,
        "by_currency": by_currency,
        "payments": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# Payment options
# ---------------------------------------------------------------------------

def get_payment_options(site: str = "") -> dict[str, Any]:
    """
    Return a dict describing all configured payment methods for a given site.
    Used by the website template to render payment buttons and wallet addresses.
    """
    sys.path.insert(0, str(PAYMENTS_DIR.parent))
    from config import cfg  # noqa: PLC0415

    options: dict[str, Any] = {}

    if cfg.STRIPE_PUBLISHABLE_KEY and cfg.STRIPE_SECRET_KEY:
        options["stripe"] = {
            "enabled": True,
            "publishable_key": cfg.STRIPE_PUBLISHABLE_KEY,
        }

    if cfg.PAYPAL_CLIENT_ID:
        options["paypal"] = {
            "enabled": True,
            "client_id": cfg.PAYPAL_CLIENT_ID,
            "environment": cfg.PAYPAL_ENV,
        }

    wallets = []
    if cfg.BTC_WALLET_ADDRESS:
        wallets.append({"network": "Bitcoin", "token": "BTC", "address": cfg.BTC_WALLET_ADDRESS})
    if cfg.ETH_WALLET_ADDRESS:
        wallets.append({"network": "Ethereum", "token": "ETH", "address": cfg.ETH_WALLET_ADDRESS})
    if cfg.USDT_TRC20_WALLET_ADDRESS:
        wallets.append({"network": "TRON", "token": "USDT (TRC-20)", "address": cfg.USDT_TRC20_WALLET_ADDRESS})

    if wallets:
        options["crypto"] = {"enabled": True, "wallets": wallets}

    return options


# ---------------------------------------------------------------------------
# Telegram notification helper
# ---------------------------------------------------------------------------

async def notify_telegram_payment(
    source: str,
    amount: float,
    currency: str,
    site: str,
    tx_id: Optional[str] = None,
) -> None:
    """Send a payment notification to the configured Telegram chat."""
    sys.path.insert(0, str(PAYMENTS_DIR.parent))
    from config import cfg  # noqa: PLC0415

    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_NOTIFY_CHAT_ID:
        return

    emoji = {"stripe": "💳", "paypal": "🅿️", "btc": "₿", "eth": "Ξ", "usdt": "💵"}.get(source, "💰")
    text = (
        f"{emoji} *New Payment Received*\n"
        f"Source:   `{source.upper()}`\n"
        f"Amount:   `{amount:,.4f} {currency}`\n"
        f"Site:     `{site or 'N/A'}`\n"
        f"Tx ID:    `{tx_id or 'N/A'}`"
    )

    try:
        import urllib.parse  # noqa: PLC0415
        import urllib.request as ureq  # noqa: PLC0415
        url = (
            f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
            f"?chat_id={cfg.TELEGRAM_NOTIFY_CHAT_ID}"
            f"&text={urllib.parse.quote(text)}&parse_mode=Markdown"
        )
        with ureq.urlopen(url, timeout=10) as resp:
            if resp.status != 200:
                log.warning("Telegram notification failed: HTTP %d", resp.status)
    except Exception as exc:
        log.warning("Telegram notification error: %s", exc)
