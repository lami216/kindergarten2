"""Private deterministic TLS/PostgreSQL fixture for collection follow-up.

Only the disposable loopback kindergarten_test database is accepted. The
business-day override belongs to this QA process, never the production app.
Credentials, certificates and connection settings stay outside Git.
"""
import argparse
import base64
from datetime import date
import io
import json
from pathlib import Path
import uuid

from tests import qa_live_pages as QA


BUSINESS_DAY = date(2026, 11, 10)
ORIGIN = 'https://127.0.0.1:8531'


def freeze_business_day():
    import monthly_finance as F
    F.today = lambda: BUSINESS_DAY


def setup(root):
    freeze_business_day()
    QA.setup(root)
    try:
        state = json.loads((root / 'state.json').read_text())
        state.update(origin=ORIGIN, business_day=BUSINESS_DAY.isoformat())
        import web_runtime as W
        import db
        import access_control as A
        import school_departments as D
        from live_pages import mutate
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGB', (80, 80), '#69b5a7').save(image, format='PNG')
        photo = base64.b64encode(image.getvalue()).decode('ascii')
        with W.request_context(state['dsn']):
            token = A.login(state['username'], state['password'])
            with W.request_context(state['dsn'], {'auth_session': token}):
                sections = [D.create(name) for name in ('قسم البراعم', 'قسم الزهور')]
                conn = db.new_transaction_connection()
                try:
                    profile = A.refresh(conn)
                    conn.commit()
                    conn.autocommit = True
                    scenarios = [
                        ('مريم أحمد', '2026-10-08', 0),
                        ('محمد سالم', '2026-10-11', 0),
                        ('خديجة علي', '2026-10-12', 1000),
                        ('أحمد محمود', '2026-10-17', 0),
                        ('آمنة المختار', '2026-10-18', 0),
                        ('زينب محمد', '2026-09-08', 0),
                        ('عمر عبد الله', '2026-10-12', 18000),
                    ]
                    for index, (name, anchor, paid) in enumerate(scenarios):
                        mutate(conn, 'students.create', dict(
                            department_id=sections[index % 2], name=name,
                            birth=f'2022-0{index % 4 + 1}-12',
                            gender='ذكر' if index % 2 else 'أنثى',
                            father='والد ' + name.split()[0], fatherPhone=str(22000000 + index),
                            mother='والدة ' + name.split()[0], motherPhone=str(33000000 + index),
                            mode='pay', amount=str(paid), registration=False, gilet=False,
                            start_date=anchor, photo=photo, request_token=str(uuid.uuid4())), profile)
                finally:
                    conn.close()
        (root / 'state.json').write_text(json.dumps(state), encoding='utf-8')
        (root / 'state.json').chmod(0o600)
    except BaseException:
        QA.cleanup(root)
        raise
    print('ISOLATED_STUDENT_FOLLOWUP_FIXTURE_READY')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'serve', 'cleanup'))
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    if args.action == 'setup':
        setup(root)
    elif args.action == 'cleanup':
        QA.cleanup(root)
    else:
        state = json.loads((root / 'state.json').read_text(encoding='utf-8'))
        QA.guard(state['dsn'])
        if state['origin'] != ORIGIN or state.get('business_day') != BUSINESS_DAY.isoformat():
            raise RuntimeError('Student follow-up requires its own deterministic QA fixture')
        freeze_business_day()
        import uvicorn
        from live_pages import make_app
        uvicorn.run(make_app(state['dsn'], state['origin']), host='127.0.0.1', port=8531,
                    access_log=False, proxy_headers=False,
                    ssl_keyfile=str(root / 'tls.key'), ssl_certfile=str(root / 'tls.crt'))


if __name__ == '__main__':
    main()
