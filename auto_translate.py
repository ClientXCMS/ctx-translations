import json
import os
import re
import translators as ts
import sys

def get_nested_keys(data, prefix=''):
    keys = {}
    for k, v in data.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.update(get_nested_keys(v, new_key))
        else:
            keys[new_key] = v
    return keys

def set_nested_key(data, key, value):
    keys = key.split('.')
    current = data
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    current[keys[-1]] = value

def protect_placeholders(text):
    # Placeholders like {_keyword}
    placeholders = re.findall(r'\{_.*?\}', text)
    protected_text = text
    for i, p in enumerate(placeholders):
        protected_text = protected_text.replace(p, f' [[[{i}]]] ')
    return protected_text, placeholders

def restore_placeholders(text, placeholders):
    restored_text = text
    for i, p in enumerate(placeholders):
        # Handle potential spaces added by translator
        pattern = re.compile(rf'\s*\[\[\[{i}\]\]\]\s*')
        restored_text = pattern.sub(p, restored_text)
    return restored_text

def translate_text(text, to_lang):
    if not text or text.strip() == "":
        return text
    
    protected_text, placeholders = protect_placeholders(text)
    try:
        translated = ts.translate_text(protected_text, from_language='fr', to_language=to_lang, translator='google')
        return restore_placeholders(translated, placeholders)
    except Exception as e:
        print(f"Error translating to {to_lang}: {e}")
        return text

def main():
    translations_dir = "translations"
    source_file = os.path.join(translations_dir, "fr.json")
    
    if not os.path.exists(source_file):
        print(f"Source file {source_file} not found.")
        sys.exit(1)

    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            fr_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in fr.json: {e}")
        sys.exit(1)

    fr_keys = get_nested_keys(fr_data)
    languages = ["de", "en", "es", "it", "nl", "pt", "zh"]
    
    updated = False
    for lang in languages:
        lang_file = os.path.join(translations_dir, f"{lang}.json")
        if not os.path.exists(lang_file):
            print(f"Language file {lang_file} not found, skipping.")
            continue
            
        with open(lang_file, 'r', encoding='utf-8') as f:
            lang_data = json.load(f)
        
        lang_keys = get_nested_keys(lang_data)
        missing_keys = [k for k in fr_keys if k not in lang_keys]
        
        if missing_keys:
            print(f"Translating {len(missing_keys)} keys for {lang}...")
            for key in missing_keys:
                if key == "language": # Special case
                    continue
                source_text = fr_keys[key]
                translated_text = translate_text(source_text, lang)
                set_nested_key(lang_data, key, translated_text)
                print(f"  [{lang}] {key} -> {translated_text}")
            
            with open(lang_file, 'w', encoding='utf-8') as f:
                json.dump(lang_data, f, indent=2, ensure_ascii=False)
            updated = True
    
    if updated:
        print("Translations updated successfully.")
    else:
        print("No new translations needed.")

if __name__ == "__main__":
    main()
