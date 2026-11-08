"""Private, disposable TLS fixture for monthly payroll browser checks.

Reuses the guarded loopback kindergarten_test fixture. Credentials, TLS keys
and connection settings stay in the runner's temporary directory, never Git.
"""
import argparse
import json
from datetime import date
from pathlib import Path

from tests import qa_live_pages as QA


def setup(root):
    QA.setup(root)
    state = json.loads((root / 'state.json').read_text())
    state['origin'] = 'https://127.0.0.1:8530'
    import web_runtime as W
    import db
    import access_control as A
    import payroll_finance as P
    from live_pages import mutate
    import uuid
    with W.request_context(state['dsn']):
        token = A.login(state['username'], state['password'])
        with W.request_context(state['dsn'], {'auth_session': token}):
            conn = db.new_transaction_connection()
            try:
                profile = A.refresh(conn)
                conn.commit()
                conn.autocommit = True
                first = mutate(conn, 'tools.change', dict(table='teachers', mode='create',
                    values=dict(full_name='آمنة أحمد', national_id='TEACHER-1', salary='2000',
                                hire_date='2026-09-01', department_id=1),
                    confirmed=True, reason='Disposable browser fixture', request_token=str(uuid.uuid4())), profile)
                tid = first['id']
                P.save_salary(tid, '2026-09', 2000, actor=state['username'], on_date=date(2026, 10, 2), reason='September')
                aid, _ = P.save_advance(tid, '2026-10', 500, actor=state['username'], on_date=date(2026, 10, 10), reason='October advance')
                P.save_salary(tid, '2026-10', 2000, actor=state['username'], on_date=date(2026, 11, 2),
                    reason='Partial October', managed=True, payment_cash=1000, settlements=[{'id': aid, 'amount': 500}])
                P.save_advance(tid, '2026-11', 600, actor=state['username'], on_date=date(2026, 11, 3), reason='November advance')
            finally:
                conn.close()
    (root / 'state.json').write_text(json.dumps(state))
    (root / 'state.json').chmod(0o600)


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
        state = json.loads((root / 'state.json').read_text())
        QA.guard(state['dsn'])
        import uvicorn
        from live_pages import make_app
        uvicorn.run(make_app(state['dsn'], state['origin']), host='127.0.0.1', port=8530,
                    access_log=False, proxy_headers=False,
                    ssl_keyfile=str(root / 'tls.key'), ssl_certfile=str(root / 'tls.crt'))


if __name__ == '__main__':
    main()
