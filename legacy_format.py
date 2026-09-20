"""Rebuilds the pre-2.17 single-file-per-locale format from the per-module split.

Instances running ClientXCMS older than 2.17 never learned about the
per-module directories and keep downloading one translations/<locale>.json
keying every module path under "fr" (ImportFileTranslationCommand on their
side rewrites that to their own locale). Regenerating it here, from the
per-module files, keeps those instances receiving real updates without a
second, manually maintained copy of the same content.
"""

import json
import os

TRANSLATIONS_DIR = "translations"
LOCALES_FILE = "locales.json"


def rebuild_locale(locale: str, language_name: str) -> dict:
    lang_dir = os.path.join(TRANSLATIONS_DIR, locale)
    legacy = {"language": language_name}
    if not os.path.isdir(lang_dir):
        return legacy

    for module_file in sorted(os.listdir(lang_dir)):
        if not module_file.endswith(".json"):
            continue
        module = module_file[: -len(".json")]
        with open(os.path.join(lang_dir, module_file), "r", encoding="utf-8") as f:
            legacy[f"lang.fr.{module}"] = json.load(f)

    return legacy


def rebuild_all(locales: list[str]) -> None:
    with open(LOCALES_FILE, "r", encoding="utf-8") as f:
        locales_meta = json.load(f)
    names_by_key = {entry["key"]: entry["name"] for entry in locales_meta.values() if "key" in entry}

    for locale in locales:
        legacy = rebuild_locale(locale, names_by_key.get(locale, locale))
        with open(os.path.join(TRANSLATIONS_DIR, f"{locale}.json"), "w", encoding="utf-8") as f:
            json.dump(legacy, f, indent=2, ensure_ascii=False)
        print(f"Rebuilt legacy file: translations/{locale}.json")
