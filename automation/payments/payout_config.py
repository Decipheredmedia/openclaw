"""
payments/payout_config.py — Pydantic data models for payment configuration.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class BankAccount(BaseModel):
    """Represents a fiat bank account for payout routing."""

    account_holder: str
    bank_name: str
    account_number: str
    routing_number: str  # ABA / sort code
    account_type: Literal["checking", "savings"] = "checking"
    currency: str = "USD"
    country: str = "US"
    notes: str = ""


class CryptoWallet(BaseModel):
    """Represents a cryptocurrency wallet address."""

    network: Literal["bitcoin", "ethereum", "tron"]
    token: str  # e.g. "BTC", "ETH", "USDT"
    address: str
    confirmations_required: int = 2
    notes: str = ""

    @field_validator("address")
    @classmethod
    def address_not_empty(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("Crypto wallet address must not be empty.")
        return v.strip()


class StripeConfig(BaseModel):
    """Stripe payment gateway configuration."""

    publishable_key: str
    secret_key: str
    webhook_secret: str
    connect_account_id: Optional[str] = None
    enabled: bool = True

    @field_validator("secret_key")
    @classmethod
    def key_format(cls, v: str) -> str:
        if not (v.startswith("sk_live_") or v.startswith("sk_test_")):
            raise ValueError("Stripe secret key must start with 'sk_live_' or 'sk_test_'.")
        return v


class PayPalConfig(BaseModel):
    """PayPal REST API configuration."""

    client_id: str
    secret: str
    webhook_id: str
    environment: Literal["sandbox", "live"] = "live"
    enabled: bool = True

    @property
    def base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://api-m.sandbox.paypal.com"
        return "https://api-m.paypal.com"


class PaymentConfig(BaseModel):
    """Aggregated payment configuration loaded from the environment."""

    stripe: Optional[StripeConfig] = None
    paypal: Optional[PayPalConfig] = None
    wallets: list[CryptoWallet] = []
    bank_accounts: list[BankAccount] = []

    @classmethod
    def from_env(cls) -> "PaymentConfig":
        """Build a PaymentConfig from the global config singleton."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import cfg  # noqa: PLC0415

        stripe_cfg: Optional[StripeConfig] = None
        if cfg.STRIPE_SECRET_KEY and cfg.STRIPE_PUBLISHABLE_KEY and cfg.STRIPE_WEBHOOK_SECRET:
            stripe_cfg = StripeConfig(
                publishable_key=cfg.STRIPE_PUBLISHABLE_KEY,
                secret_key=cfg.STRIPE_SECRET_KEY,
                webhook_secret=cfg.STRIPE_WEBHOOK_SECRET,
                connect_account_id=cfg.STRIPE_CONNECT_ACCOUNT_ID or None,
            )

        paypal_cfg: Optional[PayPalConfig] = None
        if cfg.PAYPAL_CLIENT_ID and cfg.PAYPAL_SECRET and cfg.PAYPAL_WEBHOOK_ID:
            paypal_cfg = PayPalConfig(
                client_id=cfg.PAYPAL_CLIENT_ID,
                secret=cfg.PAYPAL_SECRET,
                webhook_id=cfg.PAYPAL_WEBHOOK_ID,
                environment=cfg.PAYPAL_ENV,
            )

        wallets: list[CryptoWallet] = []
        if cfg.BTC_WALLET_ADDRESS:
            wallets.append(CryptoWallet(
                network="bitcoin", token="BTC", address=cfg.BTC_WALLET_ADDRESS,
                confirmations_required=cfg.BTC_CONFIRMATIONS_REQUIRED,
            ))
        if cfg.ETH_WALLET_ADDRESS:
            wallets.append(CryptoWallet(
                network="ethereum", token="ETH", address=cfg.ETH_WALLET_ADDRESS,
                confirmations_required=cfg.ETH_CONFIRMATIONS_REQUIRED,
            ))
        if cfg.USDT_TRC20_WALLET_ADDRESS:
            wallets.append(CryptoWallet(
                network="tron", token="USDT", address=cfg.USDT_TRC20_WALLET_ADDRESS,
                confirmations_required=cfg.TRON_CONFIRMATIONS_REQUIRED,
            ))

        return cls(stripe=stripe_cfg, paypal=paypal_cfg, wallets=wallets)
