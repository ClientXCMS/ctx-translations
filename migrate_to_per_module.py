"""One-off migration: splits each existing translations/<locale>.json into
translations/<locale>/<module>.json, so already-translated content survives
the switch to the per-module format instead of looking missing and being
re-translated from scratch on the first run after this ships.

Run once, by hand, from a clean checkout. Leaves the old flat files in
place untouched: auto_translate.py regenerates them on every future run
anyway, and older ClientXCMS instances still read them during the
transition.
"""

import json
import os

TRANSLATIONS_DIR = "translations"


def migrate_locale(locale: str) -> int:
    flat_path = os.path.join(TRANSLATIONS_DIR, f"{locale}.json")
    if not os.path.exists(flat_path):
        return 0

    with open(flat_path, "r", encoding="utf-8") as f:
        flat = json.load(f)

    module_dir = os.path.join(TRANSLATIONS_DIR, locale)
    os.makedirs(module_dir, exist_ok=True)

    migrated = 0
    for key, value in flat.items():
        if key == "language":
            continue
        if not key.startswith("lang.fr."):
            print(f"  [{locale}] unexpected key shape, skipped: {key}")
            continue
        module = key[len("lang.fr.") :]
        with open(os.path.join(module_dir, f"{module}.json"), "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
        migrated += 1

    return migrated


def main() -> None:
    locales = sorted(
        f[: -len(".json")] for f in os.listdir(TRANSLATIONS_DIR) if f.endswith(".json")
    )
    for locale in locales:
        count = migrate_locale(locale)
        print(f"{locale}: {count} module(s) migrated")


if __name__ == "__main__":
    main()
