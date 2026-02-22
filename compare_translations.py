import json
import os

def get_keys(d, prefix=''):
    keys = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.update(get_keys(v, full_key))
        else:
            keys[full_key] = v
    return keys

def compare_translations(source_file, target_file):
    with open(source_file, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    with open(target_file, 'r', encoding='utf-8') as f:
        target_data = json.load(f)
    
    source_keys = get_keys(source_data)
    target_keys = get_keys(target_data)
    
    missing_keys = {k: source_keys[k] for k in source_keys if k not in target_keys}
    return missing_keys

if __name__ == "__main__":
    translations_dir = "translations"
    source_lang = "fr.json"
    languages = ["de.json", "en.json", "es.json", "it.json", "nl.json", "pt.json", "zh.json"]
    
    all_missing = {}
    for lang in languages:
        missing = compare_translations(os.path.join(translations_dir, source_lang), os.path.join(translations_dir, lang))
        all_missing[lang] = missing
        print(f"--- Missing keys in {lang} ({len(missing)}) ---")
        for k, v in missing.items():
            print(f"{k}: {v}")
        print("\n")
    
    with open("missing_translations.json", "w", encoding="utf-8") as f:
        json.dump(all_missing, f, indent=4, ensure_ascii=False)
