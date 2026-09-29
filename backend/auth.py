"""
Azure AD token provider for the Azure OpenAI / enterprise AI gateway.

Same auth pattern used across other internal AI projects: ClientSecretCredential
first, static API key as local-dev fallback. Kept isolated in its own module so
llm_client.py doesn't need to know which auth mode is active.

Env vars (set in backend/.env — never commit real values):
  CLIENT_ID / CLIENT_SECRET / TENANT_ID  -> Azure AD app registration (preferred)
  AZURE_OPENAI_API_KEY                   -> static key fallback (local dev only)
"""
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SCOPE = "https://cognitiveservices.azure.com/.default"

_cached_token: Optional[str] = None
_token_expiry: float = 0.0


def get_azure_ad_token() -> Optional[str]:
    """Return a cached-or-fresh Azure AD token, or None if AD creds aren't configured."""
    global _cached_token, _token_expiry

    if _cached_token and time.time() < (_token_expiry - 300):
        return _cached_token

    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    tenant_id = os.environ.get("TENANT_ID")

    if not all([client_id, client_secret, tenant_id]):
        return None

    try:
        from azure.identity import ClientSecretCredential

        credential = ClientSecretCredential(
            tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
        )
        token = credential.get_token(_SCOPE)
        _cached_token = token.token
        _token_expiry = token.expires_on
        logger.info("Azure AD token obtained via ClientSecretCredential")
        return _cached_token
    except Exception as e:
        logger.error(f"Failed to obtain Azure AD token: {e}")
        return None


def invalidate_azure_ad_token() -> None:
    """Force the next get_azure_ad_token() call to fetch a fresh token."""
    global _cached_token, _token_expiry
    _cached_token = None
    _token_expiry = 0.0
