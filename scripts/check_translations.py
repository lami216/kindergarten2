"""Validate bilingual messages and statically referenced translation keys (no JS build dependency)."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def public_bundle():
    # Raw docs previews are also used by existing browser regression journeys.
    return '// Generated from locales/messages.json; run python scripts/check_translations.py --write\nwindow.APP_MESSAGES='+(ROOT/'locales/messages.json').read_text(encoding='utf-8')+';\n'


def validate():
    catalog = json.loads((ROOT/'locales/messages.json').read_text(encoding='utf-8'))
    errors = []
    bundle=ROOT/'docs/locales/messages.js'
    if not bundle.is_file() or bundle.read_text(encoding='utf-8') != public_bundle():
        errors.append('Regenerate the public catalog: python scripts/check_translations.py --write')
    for key, item in catalog.items():
        for language in ('ar','fr'):
            if not isinstance(item.get(language),str) or not item[language].strip():
                errors.append(f'{key}: missing {language}')
        if sorted(re.findall(r'\{\w+\}',item.get('ar',''))) != sorted(re.findall(r'\{\w+\}',item.get('fr',''))):
            errors.append(f'{key}: placeholder mismatch')
    for directory in ('docs','live','preview'):
        for file in (ROOT/directory).glob('*.js'):
            for key in re.findall(r'I18N\.tr\([\'"]([^\'"]+)',file.read_text(encoding='utf-8')):
                if key not in catalog:
                    errors.append(f'{file.name}: unknown key {key}')
    return errors


if __name__ == '__main__':
    if '--write' in sys.argv:
        bundle=ROOT/'docs/locales/messages.js'
        bundle.parent.mkdir(exist_ok=True)
        bundle.write_text(public_bundle(),encoding='utf-8')
    errors = validate()
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Translation catalog and referenced keys are complete.')
