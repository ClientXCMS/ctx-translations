import json
import os
import re
import translators as ts
import sys

def protect_placeholders(text):
    if not isinstance(text, str):
        return text, []
    # Placeholders like {_keyword}
    placeholders = re.findall(r'\{_.*?\}', text)
    protected_text = text
    for i, p in enumerate(placeholders):
        protected_text = protected_text.replace(p, f' [[[{i}]]] ')
    return protected_text, placeholders

def restore_placeholders(text, placeholders):
    if not isinstance(text, str):
        return text
    restored_text = text
    for i, p in enumerate(placeholders):
        # Handle potential spaces added by translator
        pattern = re.compile(rf'\s*\[\[\[{i}\]\]\]\s*')
        restored_text = pattern.sub(p, restored_text)
    return restored_text

def translate_text(text, to_lang):
    if not text or not isinstance(text, str) or text.strip() == "":
        return text
    
    protected_text, placeholders = protect_placeholders(text)
    try:
        translated = ts.translate_text(protected_text, from_language='fr', to_language=to_lang, translator='google')
        return restore_placeholders(translated, placeholders)
    except Exception as e:
        print(f"Error translating to {to_lang}: {e}")
        return text

def reorder_and_merge(target, source, lang, lang_name=None):
    """
    Creates a new dictionary with keys ordered as in 'source'.
    Translates any keys missing from 'target'.
    Preserves 'language' key if lang_name is provided.
    """
    new_data = {}
    updated = False
    
    # 1. Handle "language" key first to keep it at the top
    if lang_name:
        current_lang_val = target.get("language", lang_name)
        new_data["language"] = current_lang_val
        if "language" not in target:
            updated = True
    elif "language" in target:
        new_data["language"] = target["language"]

    # 2. Identify target keys NOT in source (and not "language")
    for k in target:
        if k not in source and k != "language":
            new_data[k] = target[k]

    # 3. Iterate through source keys to maintain order
    for key, source_value in source.items():
        if key == "language":
            continue
            
        if isinstance(source_value, dict):
            target_value = target.get(key, {})
            if not isinstance(target_value, dict):
                target_value = {}
            
            res_data, res_updated = reorder_and_merge(target_value, source_value, lang)
            new_data[key] = res_data
            if res_updated:
                updated = True
        else:
            if key in target:
                new_data[key] = target[key]
            else:
                translated_val = translate_text(source_value, lang)
                new_data[key] = translated_val
                print(f"  [{lang}] {key} -> {translated_val}")
                updated = True
                
    return new_data, updated

def cleanup_corruption(data):
    """
    Moves incorrectly nested lang -> fr -> ... keys back to top-level lang.fr. ... keys
    """
    cleaned = False
    if 'lang' in data and isinstance(data['lang'], dict) and 'fr' in data['lang'] and isinstance(data['lang']['fr'], dict):
        print("Found corrupted 'lang.fr' structure. Cleaning up...")
        fr_data = data['lang']['fr']
        
        def merge_recursive(t, s):
            for k, v in s.items():
                if k in t and isinstance(t[k], dict) and isinstance(v, dict):
                    merge_recursive(t[k], v)
                else:
                    t[k] = v

        for key, value in list(fr_data.items()):
            top_key = f"lang.fr.{key}"
            if top_key not in data:
                data[top_key] = value
            elif isinstance(data[top_key], dict) and isinstance(value, dict):
                merge_recursive(data[top_key], value)
            else:
                data[top_key] = value
            del fr_data[key]
            cleaned = True
        
        if not data['lang']['fr']:
            del data['lang']['fr']
        if not data['lang']:
            del data['lang']
            
    return cleaned

def main():
    translations_dir = "translations"
    source_file = os.path.join(translations_dir, "fr.json")
    locales_file = "locales.json"
    
    if not os.path.exists(source_file):
        print(f"Source file {source_file} not found.")
        sys.exit(1)

    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            fr_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in fr.json: {e}")
        sys.exit(1)

    # Load locales for language names
    lang_names = {}
    if os.path.exists(locales_file):
        try:
            with open(locales_file, 'r', encoding='utf-8') as f:
                locales_data = json.load(f)
                for entry in locales_data.values():
                    if 'key' in entry and 'name' in entry:
                        lang_names[entry['key']] = entry['name']
        except Exception as e:
            print(f"Error reading locales.json: {e}")

    languages = ["de", "en", "es", "it", "nl", "pt", "zh"]
    
    for lang in languages:
        lang_file = os.path.join(translations_dir, f"{lang}.json")
        if not os.path.exists(lang_file):
            print(f"Language file {lang_file} not found, skipping.")
            continue
            
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                lang_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error reading {lang_file}: {e}")
            continue
        
        print(f"Processing {lang}...")
        
        # Cleanup existing corruption first
        cleanup_corruption(lang_data)
        
        # Reorder and Merge/Translate
        lang_name = lang_names.get(lang)
        new_lang_data, updated = reorder_and_merge(lang_data, fr_data, lang, lang_name)
        
        # Save results
        with open(lang_file, 'w', encoding='utf-8') as f:
            json.dump(new_lang_data, f, indent=2, ensure_ascii=False)
        print(f"Saved {lang_file}")
    
    print("Done.")

if __name__ == "__main__":
    main()
