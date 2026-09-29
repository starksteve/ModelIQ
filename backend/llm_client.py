"""
LLM client factory — chat completions + embeddings.

Two provider modes, selected automatically:

1. OpenAI-compatible (free tiers: Google Gemini, Groq, OpenRouter, Mistral, ...)
   Set OPENAI_BASE_URL + OPENAI_API_KEY in backend/.env and this uses the
   standard `openai` SDK pointed at that base URL. This is the default for a
   personal project — no Azure/enterprise gateway required.

2. Azure OpenAI (enterprise) — used only when OPENAI_BASE_URL is not set.
   Auth priority: Azure AD token provider (auth.get_azure_ad_token) first,
   static AZURE_OPENAI_API_KEY fallback second.

If neither is configured, get_client() returns None and callers must report
"LLM not configured" rather than fabricate a response.
"""
import os
import logging
from functools import lru_cache

# Use the OS certificate store (Windows) so requests through a corporate
# SSL-inspection proxy trust the enterprise root CA. Must run before httpx/openai
# open any TLS connection. No-op if truststore is unavailable.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

from dotenv import load_dotenv

from auth import get_azure_ad_token

load_dotenv()

logger = logging.getLogger(__name__)

# --- OpenAI-compatible provider (free tiers) -------------------------------
# When OPENAI_BASE_URL is set we talk to any OpenAI-compatible endpoint.
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gemini-2.0-flash")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-004")

USE_OPENAI_COMPATIBLE = bool(OPENAI_BASE_URL and OPENAI_API_KEY)

# --- Azure OpenAI (enterprise fallback) ------------------------------------
AZURE_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

# Model names the rest of the app passes as `model=`. They resolve to whichever
# provider is active so callers never need to know which backend is in use.
CHAT_DEPLOYMENT = OPENAI_MODEL if USE_OPENAI_COMPATIBLE else AZURE_CHAT_DEPLOYMENT
EMBEDDING_DEPLOYMENT = OPENAI_EMBEDDING_MODEL if USE_OPENAI_COMPATIBLE else AZURE_EMBEDDING_DEPLOYMENT

# Best-effort determinism hint (same seed -> API tries to reuse the same sampling
# path). Reasoning models may still vary run-to-run despite this.
GENERATION_SEED = int(os.getenv("AZURE_OPENAI_SEED", "42"))


def _default_headers() -> dict:
    """UAIS-style gateway headers — projectId is required by the gateway (PROJECT_ID_REQUIRED)."""
    headers = {"projectId": os.getenv("OPENAI_PROJECT_ID", ""), "x-idp": "azuread"}
    upstream_env = os.getenv("OPENAI_UPSTREAM_ENV", "")
    if upstream_env:
        headers["x-upstream-env"] = upstream_env
    return headers


def _build_openai_compatible_client():
    """Standard OpenAI SDK pointed at any OpenAI-compatible base URL
    (Google Gemini, Groq, OpenRouter, Mistral, local Ollama, ...)."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=120)
    logger.info("OpenAI-compatible client initialised (base_url=%s)", OPENAI_BASE_URL)
    return client


def _build_client():
    if USE_OPENAI_COMPATIBLE:
        return _build_openai_compatible_client()

    if not ENDPOINT:
        logger.warning(
            "No LLM configured — set OPENAI_BASE_URL + OPENAI_API_KEY (free tier) "
            "or AZURE_OPENAI_ENDPOINT in backend/.env"
        )
        return None

    try:
        from openai import AzureOpenAI
    except ImportError:
        logger.error("openai package not installed")
        return None

    ad_token = get_azure_ad_token()
    if ad_token:
        client = AzureOpenAI(
            azure_ad_token_provider=get_azure_ad_token,
            api_version=API_VERSION,
            azure_endpoint=ENDPOINT,
            default_headers=_default_headers(),
            timeout=120,
        )
        logger.info("Azure OpenAI client initialised via Azure AD token provider")
        return client

    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        client = AzureOpenAI(
            api_key=api_key,
            api_version=API_VERSION,
            azure_endpoint=ENDPOINT,
            default_headers=_default_headers(),
            timeout=120,
        )
        logger.info("Azure OpenAI client initialised via API key")
        return client

    logger.warning("No Azure OpenAI credentials configured (no AD token, no API key)")
    return None


@lru_cache(maxsize=1)
def get_client():
    """Single shared client (OpenAI-compatible or Azure) for chat + embeddings, or None."""
    return _build_client()


def is_configured() -> bool:
    return get_client() is not None


def normalize_chat_kwargs(**kwargs):
    """gpt-5* reasoning deployments reject temperature/top_p and use
    max_completion_tokens instead of max_tokens - strip/rename as needed."""
    model = str(kwargs.get("model", "")).lower()
    if model.startswith("gpt-5"):
        for param in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
            kwargs.pop(param, None)
        if "max_tokens" in kwargs and "max_completion_tokens" not in kwargs:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
    return kwargs
