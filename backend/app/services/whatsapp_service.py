"""Meta Business API WhatsApp service."""
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v18.0"


def send_template(phone: str, template: str, params: list[str]) -> dict:
    """Send a Meta-approved template message."""
    url = f"{GRAPH_URL}/{settings.WHATSAPP_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": "en_IN"},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            }],
        },
    }
    r = requests.post(url, json=payload,
                      headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                      timeout=10)
    r.raise_for_status()
    return r.json()


def send_text(phone: str, body: str) -> dict:
    """Send a free-form text message (within 24h reply window)."""
    url = f"{GRAPH_URL}/{settings.WHATSAPP_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": body},
    }
    r = requests.post(url, json=payload,
                      headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                      timeout=10)
    r.raise_for_status()
    return r.json()


def download_media(media_id: str) -> bytes:
    """Download WhatsApp media bytes via the Graph API."""
    # Step 1: get the media URL
    url_resp = requests.get(
        f"{GRAPH_URL}/{media_id}",
        headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
        timeout=10,
    )
    url_resp.raise_for_status()
    media_url = url_resp.json().get("url")

    # Step 2: download the actual bytes
    media_resp = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
        timeout=30,
    )
    media_resp.raise_for_status()
    return media_resp.content


def generate_consent_token(client_id: str, ttl_seconds: int = 86400) -> tuple[str, int]:
    """Generate a time-limited HMAC-SHA256 consent token."""
    expires = int(time.time()) + ttl_seconds
    msg = f"{client_id}:{expires}"
    sig = hmac.new(settings.SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    import base64
    return base64.urlsafe_b64encode(f"{msg}:{sig}".encode()).decode(), expires


def verify_consent_token(token: str) -> str:
    """Verify consent token and return client_id. Raises ValueError on invalid/expired."""
    import base64
    from fastapi import HTTPException
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        client_id, expires_str, sig = decoded.rsplit(":", 2)
        expires = int(expires_str)
    except Exception:
        raise HTTPException(400, "Invalid consent token")

    if time.time() > expires:
        raise HTTPException(400, "Consent token expired")

    msg = f"{client_id}:{expires_str}"
    expected = hmac.new(settings.SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Invalid consent token signature")

    return client_id
