"""Translates every new fr key into the machine-translated locales, one module file at a time.

fr and en are reviewed reference locales and never touched here. A key
already present in a target locale is kept as-is, never re-translated - only
what fr has and the target doesn't gets machine-translated.
"""

import json
import os
import sys

import legacy_format
from translation_budget import TranslationBudget, estimate_cost_usd
from translation_engine import TranslationEngine

TRANSLATIONS_DIR = "translations"
FR = "fr"
LANGUAGES = ["de", "es", "it", "nl", "pt"]
BUDGET_FILE = ".translation_budget.json"
DAILY_CHARACTER_BUDGET = int(os.environ.get("TRANSLATION_DAILY_CHARACTER_BUDGET", "200000"))


def reorder_and_merge(target: dict, source: dict, lang: str, engine: TranslationEngine) -> dict:
    """Rebuilds target with source's key order; a source key missing from target is translated.

    A key present in target but not in source is dropped, so a target module
    stays a strict mirror of fr's own current keys.
    """
    new_data = {}

    for key, source_value in source.items():
        if isinstance(source_value, dict):
            target_value = target.get(key, {})
            if not isinstance(target_value, dict):
                target_value = {}
            new_data[key] = reorder_and_merge(target_value, source_value, lang, engine)
        elif key in target:
            new_data[key] = target[key]
        else:
            translated = engine.translate(source_value, lang)
            if translated is None:
                continue
            new_data[key] = translated
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

        for module_file in modules:
            fr_data = load_json(os.path.join(fr_dir, module_file))
            lang_data = load_json(os.path.join(lang_dir, module_file))
            new_data = reorder_and_merge(lang_data, fr_data, lang, engine)

            with open(os.path.join(lang_dir, module_file), "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)

        # A module removed from fr is removed from every target locale too.
        for existing in os.listdir(lang_dir):
            if existing not in modules:
                os.remove(os.path.join(lang_dir, existing))
                print(f"  [{lang}] removed stale module: {existing}")


def main() -> None:
    report_backlog_estimate()

    force = os.environ.get("TRANSLATION_FORCE_BUDGET", "").lower() in ("1", "true", "yes")
    budget = TranslationBudget(BUDGET_FILE, DAILY_CHARACTER_BUDGET, force=force)
    engine = TranslationEngine(budget)

    translate_modules(engine)
    budget.save()

    en_present = os.path.isdir(os.path.join(TRANSLATIONS_DIR, "en"))
    legacy_format.rebuild_all([FR, *LANGUAGES, *(["en"] if en_present else [])])

    print("Done.")


if __name__ == "__main__":
    main()
