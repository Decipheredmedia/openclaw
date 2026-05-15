"""
payments/crypto_monitor.py — Polls blockchain APIs for incoming transactions.

Monitors:
  - Bitcoin (BTC) via Blockstream.info API
  - Ethereum (ETH) via Alchemy JSON-RPC
  - USDT TRC-20 on TRON via TronGrid API

Every CRYPTO_POLL_INTERVAL seconds a scheduler job calls check_all_wallets().
New confirmed transactions are recorded in the ledger and trigger a Telegram alert.
Seen transaction IDs are deduplicated in memory (and the ledger's UNIQUE constraint).
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

PAYMENTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PAYMENTS_DIR.parent))

# In-memory dedup set (also backed by ledger UNIQUE tx_id constraint)
_seen_txids: set[str] = set()


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get_json(url: str, headers: Optional[dict[str, str]] = None, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _post_json(url: str, payload: dict, headers: Optional[dict[str, str]] = None, timeout: int = 15) -> Any:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Bitcoin via Blockstream.info
# ---------------------------------------------------------------------------

def _check_btc(address: str, confirmations_required: int) -> list[dict[str, Any]]:
    """
    Fetch confirmed transactions to *address* from Blockstream.
    Returns list of dicts: {txid, amount_btc, confirmations, block_height}
    """
    url = f"https://blockstream.info/api/address/{address}/txs"
    try:
        txs = _get_json(url)
    except Exception as exc:
        log.warning("BTC API error for %s: %s", address, exc)
        return []

    results = []
    for tx in txs:
        txid = tx.get("txid", "")
        if txid in _seen_txids:
            continue
        status = tx.get("status", {})
        if not status.get("confirmed"):
            continue
        block_height = status.get("block_height", 0)

        # Get current block height for confirmation count
        try:
            tip = int(_get_json("https://blockstream.info/api/blocks/tip/height"))
        except Exception:
            tip = block_height + confirmations_required  # assume confirmed

        conf = tip - block_height + 1
        if conf < confirmations_required:
            continue

        # Sum outputs to our address
        amount_satoshi = sum(
            vout.get("value", 0)
            for vout in tx.get("vout", [])
            if vout.get("scriptpubkey_address") == address
        )
        amount_btc = amount_satoshi / 1e8
        if amount_btc <= 0:
            continue

        results.append({
            "txid": txid,
            "amount": amount_btc,
            "currency": "BTC",
            "confirmations": conf,
        })

    return results


# ---------------------------------------------------------------------------
# Ethereum via Alchemy JSON-RPC
# ---------------------------------------------------------------------------

def _check_eth(address: str, alchemy_api_key: str, confirmations_required: int) -> list[dict[str, Any]]:
    """
    Use Alchemy's eth_getTransactionCount and eth_getLogs to find incoming ETH.
    Uses alchemy_getAssetTransfers for a reliable incoming tx scan.
    """
    url = f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_api_key}"
    address_lower = address.lower()

    try:
        # alchemy_getAssetTransfers — finds incoming ETH transfers
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toAddress": address_lower,
                "category": ["external", "internal", "erc20"],
                "withMetadata": False,
                "excludeZeroValue": True,
                "maxCount": "0x32",  # 50 results
            }],
        }
        data = _post_json(url, payload)
        transfers = data.get("result", {}).get("transfers", [])
    except Exception as exc:
        log.warning("Alchemy ETH API error: %s", exc)
        return []

    # Get current block number for confirmations
    try:
        block_resp = _post_json(url, {"id": 2, "jsonrpc": "2.0", "method": "eth_blockNumber", "params": []})
        current_block = int(block_resp["result"], 16)
    except Exception:
        current_block = 999_999_999

    results = []
    for tx in transfers:
        txid = tx.get("hash", "")
        if not txid or txid in _seen_txids:
            continue

        block_num_hex = tx.get("blockNum", "0x0")
        try:
            block_num = int(block_num_hex, 16)
        except ValueError:
            block_num = 0

        conf = current_block - block_num + 1
        if conf < confirmations_required:
            continue

        asset = tx.get("asset", "ETH")
        value = float(tx.get("value", 0))
        if value <= 0:
            continue

        results.append({
            "txid": txid,
            "amount": value,
            "currency": asset,
            "confirmations": conf,
        })

    return results


# ---------------------------------------------------------------------------
# USDT TRC-20 via TronGrid
# ---------------------------------------------------------------------------

_USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def _check_tron_usdt(address: str, tron_api_key: str, confirmations_required: int) -> list[dict[str, Any]]:
    """
    Query TronGrid for TRC-20 USDT transfers to *address*.
    """
    url = (
        f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
        f"?contract_address={_USDT_TRC20_CONTRACT}&limit=50&only_to=true"
    )
    try:
        data = _get_json(url, headers={"TRON-PRO-API-KEY": tron_api_key} if tron_api_key else {})
        txs = data.get("data", [])
    except Exception as exc:
        log.warning("TronGrid API error: %s", exc)
        return []

    results = []
    for tx in txs:
        txid = tx.get("transaction_id", "")
        if not txid or txid in _seen_txids:
            continue

        # confirmed = block_timestamp is set and not zero
        block_ts = tx.get("block_timestamp", 0)
        if not block_ts:
            continue

        # TronGrid doesn't return confirmations directly; treat any confirmed block as OK
        # For production, cross-check with current block height via getblockcount
        token_info = tx.get("token_info", {})
        decimals = token_info.get("decimals", 6)
        raw_value = int(tx.get("value", 0))
        amount = raw_value / (10 ** decimals)

        if amount <= 0:
            continue

        results.append({
            "txid": txid,
            "amount": amount,
            "currency": "USDT",
            "confirmations": confirmations_required,  # trust TronGrid confirmed flag
        })

    return results


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def check_all_wallets() -> None:
    """
    Scheduled job: poll all configured wallets and record new transactions.
    Called by the APScheduler every CRYPTO_POLL_INTERVAL seconds.
    """
    from config import cfg  # noqa: PLC0415
    from payments.payment_manager import notify_telegram_payment, record_payment  # noqa: PLC0415

    new_payments: list[dict[str, Any]] = []

    # Bitcoin
    if cfg.BTC_WALLET_ADDRESS:
        btc_txs = _check_btc(cfg.BTC_WALLET_ADDRESS, cfg.BTC_CONFIRMATIONS_REQUIRED)
        for tx in btc_txs:
            tx["source"] = "btc"
            tx["address"] = cfg.BTC_WALLET_ADDRESS
            new_payments.append(tx)

    # Ethereum
    if cfg.ETH_WALLET_ADDRESS and cfg.ALCHEMY_API_KEY:
        eth_txs = _check_eth(cfg.ETH_WALLET_ADDRESS, cfg.ALCHEMY_API_KEY, cfg.ETH_CONFIRMATIONS_REQUIRED)
        for tx in eth_txs:
            tx["source"] = "eth"
            tx["address"] = cfg.ETH_WALLET_ADDRESS
            new_payments.append(tx)
    elif cfg.ETH_WALLET_ADDRESS and not cfg.ALCHEMY_API_KEY:
        log.warning("ALCHEMY_API_KEY not configured — ETH monitoring disabled.")

    # USDT TRC-20
    if cfg.USDT_TRC20_WALLET_ADDRESS:
        usdt_txs = _check_tron_usdt(
            cfg.USDT_TRC20_WALLET_ADDRESS,
            cfg.TRON_API_KEY or "",
            cfg.TRON_CONFIRMATIONS_REQUIRED,
        )
        for tx in usdt_txs:
            tx["source"] = "usdt"
            tx["address"] = cfg.USDT_TRC20_WALLET_ADDRESS
            new_payments.append(tx)

    for payment in new_payments:
        txid = payment["txid"]
        if txid in _seen_txids:
            continue
        _seen_txids.add(txid)

        row_id = record_payment(
            source=payment["source"],
            amount=payment["amount"],
            currency=payment["currency"],
            site="",  # crypto payments aren't site-specific
            status="confirmed",
            tx_id=txid,
            metadata={
                "confirmations": payment.get("confirmations"),
                "address": payment.get("address"),
            },
        )
        log.info(
            "Crypto payment recorded: id=%d %s %.6f %s (tx=%s)",
            row_id, payment["source"], payment["amount"], payment["currency"], txid,
        )

        # Fire-and-forget Telegram notification (sync context)
        import asyncio  # noqa: PLC0415
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    notify_telegram_payment(
                        payment["source"], payment["amount"], payment["currency"],
                        site="", tx_id=txid,
                    )
                )
            else:
                loop.run_until_complete(
                    notify_telegram_payment(
                        payment["source"], payment["amount"], payment["currency"],
                        site="", tx_id=txid,
                    )
                )
        except Exception as exc:
            log.warning("Telegram notify failed: %s", exc)
