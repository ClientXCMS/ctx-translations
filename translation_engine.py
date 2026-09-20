"""Translation engines, tried in order: Cloudflare, then DeepL, then Google.

Cloudflare uses a dedicated translation model (m2m100) rather than a general
one: it only translates, so it carries no prompt-injection surface even
though the project's own strings are not attacker-controlled. DeepL sits
between the two as a paid-quality option with a free tier (500k
characters/month) far above Cloudflare's, and is a better fit for these 6
languages than Google in practice. Each engine is checked once per run, not
retried per-call: a run degrades down the chain instead of flapping between
engines call by call.
"""

import os

import requests
import translators as ts

import placeholders
from translation_budget import TranslationBudget

CLOUDFLARE_MODEL = "@cf/meta/m2m100-1.2b"
CLOUDFLARE_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
CLOUDFLARE_TIMEOUT = 15
DEEPL_TIMEOUT = 15
ENGINE_CHAIN = ["cloudflare", "deepl", "google"]


class EngineUnavailable(Exception):
    """Raised for anything that should make the run fall back to the next engine in the chain."""


def cloudflare_credentials_present() -> bool:
    return bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID")) and bool(os.environ.get("CLOUDFLARE_AI_TOKEN"))


def deepl_credentials_present() -> bool:
    return bool(os.environ.get("DEEPL_API_KEY"))


def cloudflare_translate(text: str, target_lang: str) -> str:
    url = CLOUDFLARE_ENDPOINT.format(account=os.environ["CLOUDFLARE_ACCOUNT_ID"], model=CLOUDFLARE_MODEL)
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_AI_TOKEN']}"},
        json={"text": text, "source_lang": "fr", "target_lang": target_lang},
        timeout=CLOUDFLARE_TIMEOUT,
    )
    if response.status_code == 429:
        raise EngineUnavailable(f"Cloudflare rate limited (HTTP 429): {response.text[:200]}")
    if response.status_code in (401, 402, 403):
        raise EngineUnavailable(f"Cloudflare plan/auth limit (HTTP {response.status_code}): {response.text[:200]}")
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise EngineUnavailable(f"Cloudflare refused the request: {payload.get('errors')}")
    translated = payload.get("result", {}).get("translated_text", "")
    if not translated:
        raise RuntimeError("Cloudflare returned an empty translation")
    return translated


def deepl_translate(text: str, target_lang: str) -> str:
    key = os.environ["DEEPL_API_KEY"]
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    response = requests.post(
        f"https://{host}/v2/translate",
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        json={"text": [text], "source_lang": "FR", "target_lang": target_lang.upper()},
        timeout=DEEPL_TIMEOUT,
    )
    if response.status_code == 429:
        raise EngineUnavailable(f"DeepL rate limited (HTTP 429): {response.text[:200]}")
    if response.status_code in (403, 456):
        raise EngineUnavailable(f"DeepL quota/auth limit (HTTP {response.status_code}): {response.text[:200]}")
    response.raise_for_status()
    translations = response.json().get("translations", [])
    if not translations or not translations[0].get("text"):
        raise RuntimeError("DeepL returned an empty translation")
    return translations[0]["text"]


def google_translate(text: str, target_lang: str) -> str:
    return ts.translate_text(text, from_language="fr", to_language=target_lang, translator="google")


ENGINE_CREDENTIALS = {"cloudflare": cloudflare_credentials_present, "deepl": deepl_credentials_present}
ENGINE_TRANSLATE = {"cloudflare": cloudflare_translate, "deepl": deepl_translate, "google": google_translate}


class TranslationEngine:
    """Walks the engine chain once per run: the first configured engine keeps
    serving calls until it fails, then the run permanently steps down to the
    next one in ENGINE_CHAIN, never back up - so a run degrades once instead
    of flapping between engines call by call."""

    def __init__(self, budget: TranslationBudget):
        self.budget = budget
        self.engine_index = self._first_available_index()

    def _first_available_index(self) -> int:
        for i, name in enumerate(ENGINE_CHAIN):
            check = ENGINE_CREDENTIALS.get(name)
            if check is None or check():
                return i
        return len(ENGINE_CHAIN) - 1

    def translate(self, text: str, target_lang: str) -> str | None:
        if not text or not isinstance(text, str) or text.strip() == "":
            return text

        if not self.budget.allows(len(text)):
            return None

        protected_text, tokens = placeholders.protect(text)
        translated = None

        while translated is None and self.engine_index < len(ENGINE_CHAIN):
            engine_name = ENGINE_CHAIN[self.engine_index]
            try:
                translated = ENGINE_TRANSLATE[engine_name](protected_text, target_lang)
            except EngineUnavailable as e:
                next_name = ENGINE_CHAIN[self.engine_index + 1] if self.engine_index + 1 < len(ENGINE_CHAIN) else None
                print(f"{e}, switching to {next_name or 'nothing left'} for the rest of this run.")
                self.engine_index += 1
            except Exception as e:
                print(f"  {engine_name} error translating to {target_lang}: {e}")
                return None

        if translated is None:
            return None

        restored = placeholders.restore(translated, tokens)
        if not placeholders.survived_intact(text, restored):
            print(f"  Placeholder mismatch translating to {target_lang}, skipping this key: {text!r} -> {restored!r}")
            return None

        self.budget.spend(len(text))
        return restored
