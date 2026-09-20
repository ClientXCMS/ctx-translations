"""Translation engines: Cloudflare Workers AI first, Google Translate as a fallback.

A dedicated translation model (m2m100) rather than a general one: it only
translates, so it carries no prompt-injection surface even though the
project's own strings are not attacker-controlled. Falls back to Google
Translate when Cloudflare credentials are absent, or once Cloudflare refuses
a request for quota/plan reasons - checked once per run, not retried
per-call, so a run degrades to a single engine instead of flapping.
"""

import os

import requests
import translators as ts

import placeholders
from translation_budget import TranslationBudget

CLOUDFLARE_MODEL = "@cf/meta/m2m100-1.2b"
CLOUDFLARE_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
CLOUDFLARE_TIMEOUT = 15


class CloudflareUnavailable(Exception):
    """Raised for anything that should make the run fall back to Google Translate."""


def cloudflare_credentials_present() -> bool:
    return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID")) and bool(os.environ.get("CLOUDFLARE_AI_TOKEN"))


def cloudflare_translate(text: str, target_lang: str) -> str:
    url = CLOUDFLARE_ENDPOINT.format(account=os.environ["CLOUDFLARE_ACCOUNT_ID"], model=CLOUDFLARE_MODEL)
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_AI_TOKEN']}"},
        json={"text": text, "source_lang": "fr", "target_lang": target_lang},
        timeout=CLOUDFLARE_TIMEOUT,
    )
    if response.status_code == 429:
        raise CloudflareUnavailable(f"rate limited (HTTP 429): {response.text[:200]}")
    if response.status_code in (401, 402, 403):
        raise CloudflareUnavailable(f"plan/auth limit (HTTP {response.status_code}): {response.text[:200]}")
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise CloudflareUnavailable(f"engine refused the request: {payload.get('errors')}")
    translated = payload.get("result", {}).get("translated_text", "")
    if not translated:
        raise RuntimeError("Cloudflare returned an empty translation")
    return translated


def google_translate(text: str, target_lang: str) -> str:
    return ts.translate_text(text, from_language="fr", to_language=target_lang, translator="google")


class TranslationEngine:
    """Picks an engine once, translates through it, verifies placeholders survived."""

    def __init__(self, budget: TranslationBudget):
        self.budget = budget
        self.engine = None

    def _pick_engine(self) -> str:
        if cloudflare_credentials_present():
            return "cloudflare"
        print("Cloudflare credentials not configured, using Google Translate for this run.")
        return "google"

    def translate(self, text: str, target_lang: str) -> str | None:
        if not text or not isinstance(text, str) or text.strip() == "":
            return text

        if self.engine is None:
            self.engine = self._pick_engine()

        if not self.budget.allows(len(text)):
            return None

        protected_text, tokens = placeholders.protect(text)
        translated = None

        if self.engine == "cloudflare":
            try:
                translated = cloudflare_translate(protected_text, target_lang)
            except CloudflareUnavailable as e:
                print(f"Cloudflare unavailable ({e}), switching to Google Translate for the rest of this run.")
                self.engine = "google"
            except Exception as e:
                print(f"Cloudflare error ({e}), switching to Google Translate for the rest of this run.")
                self.engine = "google"

        if translated is None:
            try:
                translated = google_translate(protected_text, target_lang)
            except Exception as e:
                print(f"  Error translating to {target_lang}: {e}")
                return None

        restored = placeholders.restore(translated, tokens)
        if not placeholders.survived_intact(text, restored):
            print(f"  Placeholder mismatch translating to {target_lang}, skipping this key: {text!r} -> {restored!r}")
            return None

        self.budget.spend(len(text))
        return restored
