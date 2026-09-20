"""Translates every new or changed fr key into the other locales, one module file at a time.

fr is the only reference never machine-translated. Every other locale,
including en, keeps a key it already has (whether that came from a
ClientXCMS pull request or a previous run here) and only gets a key
machine-translated when fr has it and the locale doesn't yet, or when fr's
own text changed since the last successful translation of that exact key
(tracked per key via HASHES_FILENAME, not per module: editing one string in
fr never forces a retranslation of its whole module).
"""

import hashlib
import json
import os
import sys

import legacy_format
from translation_budget import TranslationBudget, estimate_cost_usd
from translation_engine import TranslationEngine

TRANSLATIONS_DIR = "translations"
FR = "fr"
LANGUAGES = ["en", "de", "es", "it", "nl", "pt"]
BUDGET_FILE = ".translation_budget.json"
HASHES_FILENAME = ".translation_hashes"
DAILY_CHARACTER_BUDGET = int(os.environ.get("TRANSLATION_DAILY_CHARACTER_BUDGET", "200000"))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reorder_and_merge(target: dict, source: dict, lang: str, engine: TranslationEngine, hashes: dict, path: str = "") -> dict:
    """Rebuilds target with source's key order; a source key missing from target,
    or whose fr text changed since the last translation, is (re)translated.

    A key present in target but not in source is dropped, so a target module
    stays a strict mirror of fr's own current keys.
    """
    new_data = {}

    for key, source_value in source.items():
        key_path = f"{path}.{key}" if path else key

        if isinstance(source_value, dict):
            target_value = target.get(key, {})
            if not isinstance(target_value, dict):
                target_value = {}
            new_data[key] = reorder_and_merge(target_value, source_value, lang, engine, hashes, key_path)
            continue

        current_hash = _hash(source_value) if isinstance(source_value, str) else None
        previous_hash = hashes.get(key_path)
        fr_changed = previous_hash is not None and previous_hash != current_hash

        # en is a tracked reference like fr, exported straight from ClientXCMS
        # before this runs: a key it already has must never be overwritten by
        # a machine retranslation of fr, even when fr changed in the same run.
        if key in target and (not fr_changed or lang == "en"):
            new_data[key] = target[key]
            if current_hash:
                hashes[key_path] = current_hash
            continue

        translated = engine.translate(source_value, lang)
        if translated is None:
            if key in target:
                new_data[key] = target[key]
            continue
        new_data[key] = translated
        if current_hash:
            hashes[key_path] = current_hash
        print(f"  [{lang}] {key} -> {translated}")

    return new_data


def count_missing_characters(source: dict, target: dict) -> int:
    """Sums the character length of every source string missing from target, recursively."""
    total = 0
    for key, source_value in source.items():
        if isinstance(source_value, dict):
            target_value = target.get(key, {})
            total += count_missing_characters(source_value, target_value if isinstance(target_value, dict) else {})
        elif key not in target and isinstance(source_value, str):
            total += len(source_value)
    return total


def report_backlog_estimate() -> None:
    """Prints, upfront, roughly what translating today's full backlog would cost.

    A dry run: no network call, no budget spent. Lets a maintainer judge the
    price of forcing the run past the daily cap before deciding to.
    """
    fr_dir = os.path.join(TRANSLATIONS_DIR, FR)
    if not os.path.isdir(fr_dir):
        return

    modules = sorted(f for f in os.listdir(fr_dir) if f.endswith(".json"))
    total_characters = 0

    for lang in LANGUAGES:
        lang_dir = os.path.join(TRANSLATIONS_DIR, lang)
        for module_file in modules:
            fr_data = load_json(os.path.join(fr_dir, module_file))
            lang_data = load_json(os.path.join(lang_dir, module_file))
            total_characters += count_missing_characters(fr_data, lang_data)

    estimated_cost = estimate_cost_usd(total_characters)
    print(
        f"Backlog estimate: {total_characters} characters missing across "
        f"{len(LANGUAGES)} languages, ~${estimated_cost:.4f} if translated today "
        "(rough estimate, see translation_budget.py)."
    )


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def translate_modules(engine: TranslationEngine) -> None:
    fr_dir = os.path.join(TRANSLATIONS_DIR, FR)
    if not os.path.isdir(fr_dir):
        print(f"Reference directory {fr_dir} not found.")
        sys.exit(1)

    modules = sorted(f for f in os.listdir(fr_dir) if f.endswith(".json"))

    for lang in LANGUAGES:
        lang_dir = os.path.join(TRANSLATIONS_DIR, lang)
        os.makedirs(lang_dir, exist_ok=True)
        print(f"Processing {lang}...")

        hashes_path = os.path.join(lang_dir, HASHES_FILENAME)
        hashes = load_json(hashes_path)

        for module_file in modules:
            module = module_file[: -len(".json")]
            fr_data = load_json(os.path.join(fr_dir, module_file))
            lang_data = load_json(os.path.join(lang_dir, module_file))
            module_hashes = hashes.setdefault(module, {})
            new_data = reorder_and_merge(lang_data, fr_data, lang, engine, module_hashes)

            with open(os.path.join(lang_dir, module_file), "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)

        # A module removed from fr is removed from every target locale too.
        for existing in os.listdir(lang_dir):
            if existing in (HASHES_FILENAME,):
                continue
            module = existing[: -len(".json")] if existing.endswith(".json") else existing
            if existing not in modules:
                os.remove(os.path.join(lang_dir, existing))
                hashes.pop(module, None)
                print(f"  [{lang}] removed stale module: {existing}")

        with open(hashes_path, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2, sort_keys=True)


def main() -> None:
    report_backlog_estimate()

    force = os.environ.get("TRANSLATION_FORCE_BUDGET", "").lower() in ("1", "true", "yes")
    budget = TranslationBudget(BUDGET_FILE, DAILY_CHARACTER_BUDGET, force=force)
    engine = TranslationEngine(budget)

    translate_modules(engine)
    budget.save()

    legacy_format.rebuild_all([FR, *LANGUAGES])

    print("Done.")


if __name__ == "__main__":
    main()
