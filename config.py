# config.py
"""
Central place for all secrets and configuration values.

Priority order:
1. Environment variables (Render dashboard or shell)
2. .env file (for local development)

Raises RuntimeError if BOT_TOKEN is missing.
"""

import os
from dotenv import load_dotenv

# Load .env when running locally – harmless on Render
load_dotenv()

# ─────────────────────────────────────────────────────────────
# Telegram credentials
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")          # required
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ─────────────────────────────────────────────────────────────
# Payment configuration
# ─────────────────────────────────────────────────────────────
USDT_WALLET = os.getenv("USDT_WALLET", "")
PAYMENT_AMOUNT = float(os.getenv("PAYMENT_AMOUNT", "20"))

# ─────────────────────────────────────────────────────────────
# Basic validation
# ─────────────────────────────────────────────────────────────
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. "
        "Set it in your Render Environment or in a local .env file."
    )
