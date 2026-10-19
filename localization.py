"""Presentation-only localization. No translation of names, notes or stored values."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path
import re

CATALOG = json.loads((Path(__file__).parent/'locales/messages.json').read_text(encoding='utf-8'))
BY_SOURCE = {m['ar']: m for m in CATALOG.values()}
_language = ContextVar('language', default='ar')


def language():
    return _language.get()


def number(value):
    formatted = f'{value:,}'
    # The embedded receipt font has a regular space, but no narrow no-break space.
    return formatted.replace(',', ' ').replace('.', ',') if language() == 'fr' else formatted


@contextmanager
def using_language(value):
    token = _language.set('fr' if value == 'fr' else 'ar')
    try:
        yield
    finally:
        _language.reset(token)


def request_language(request):
    return 'fr' if request.headers.get('x-app-language', request.cookies.get('kg_language')) == 'fr' else 'ar'


def label(source):
    return BY_SOURCE.get(str(source), {}).get('fr', source) if language() == 'fr' else source


def message(source):
    source = str(source)
    if language() != 'fr':
        return source
    if source in BY_SOURCE:
        return label(source)
    for item in sorted(CATALOG.values(),key=lambda m:len(re.sub(r'\{p\d+\}', '', m['ar'])),reverse=True):
        parts = re.split(r'(\{p\d+\})', item['ar'])
        if len(parts) == 1:
            continue
        keys = [part[1:-1] for part in parts if re.fullmatch(r'\{p\d+\}', part)]
        pattern = ''.join('(.+?)' if re.fullmatch(r'\{p\d+\}', part) else re.escape(part) for part in parts)
        match = re.fullmatch(pattern, source, re.S)
        if match:
            params = dict(zip(keys, match.groups()))
            return re.sub(r'\{p\d+\}', lambda m: str(params[m[0][1:-1]]), item['fr'])
    return label('تعذّر إكمال العملية. حاول مرة أخرى أو تواصل مع المدير.')


REPORT_LABELS = {
    'registration_cash': 'Frais d’inscription encaissés', 'gilet_cash': 'Tenues scolaires encaissées',
    'monthly_cash': 'Mensualités encaissées', 'prepaid_cash': 'Paiements d’avance',
    'total_cash': 'Total encaissé', 'new_cash': 'Encaissements sur la période',
    'operational_cash': 'Dépenses de fonctionnement', 'salary_cash': 'Salaires versés',
    'advance_cash': 'Avances versées', 'expenses': 'Total décaissé',
    'remaining_cash': 'Solde de trésorerie', 'due_now': 'Sommes dues par les familles',
    'registration_children': 'Inscriptions réglées', 'gilet_count': 'Tenues scolaires réglées',
}


def report_rows(items):
    """Translate column headings and trusted status enums only; leave user data intact."""
    if language() != 'fr':
        return items
    states = {'active': 'Valide', 'cancelled': 'Annulé', 'corrected': 'Corrigé',
              'voided': 'Annulé', 'نشط': 'Actif', 'معفي': 'Exonéré', 'مؤرشف': 'Archivé'}
    return [{label(k): states.get(v, v) if k in ('الحالة', 'حالة المستند') else v
             for k, v in row.items()} for row in items]
