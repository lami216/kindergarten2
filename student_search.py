"""Literal child/parent search, including Arabic digits and formatted phones."""
import re
import unicodedata

FIELDS=('full_name','father_name','mother_name','father_mobile','mother_mobile')
TRANSLATION=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹أإآٱى','01234567890123456789ااااي')


def normalized(value):
    value=str(value or '').translate(TRANSLATION).casefold()
    value=''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))
    return ' '.join(value.split())


def matches(row,term):
    term=normalized(term)
    if not term:
        return True
    phone_query=re.sub(r'[\s()+.\-]','',term)
    for field in FIELDS:
        value=row.get(field,'')
        if value is None or isinstance(value,float):
            value=''
        text=normalized(value)
        if term in text:
            return True
        if field.endswith('_mobile') and phone_query.isdecimal() and phone_query in re.sub(r'\D','',text):
            return True
    return False


def filter_children(frame,term):
    if not normalized(term) or frame.empty:
        return frame
    return frame[frame.apply(lambda row:matches(row,term),axis=1)]


def child_labels(frame):
    """Human context disambiguates names; stable ID is only a last resort."""
    from collections import Counter
    def clean(value):
        return value.strip() if isinstance(value,str) else ''
    labels={}
    for row in frame.to_dict('records'):
        family=' / '.join(filter(None,(clean(row.get('father_name')),clean(row.get('mother_name')))))
        phones=' / '.join(filter(None,(clean(row.get('father_mobile')),clean(row.get('mother_mobile')))))
        labels[row['student_id']]=' · '.join(filter(None,(clean(row.get('full_name')),family,phones)))
    duplicates=Counter(labels.values())
    return {key:text+(f' · {key}' if duplicates[text]>1 else '') for key,text in labels.items()}
