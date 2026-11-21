"""Private deterministic TLS/PostgreSQL fixture for daily attendance browsers.

Requires the disposable loopback kindergarten_test database. The official
schema migration and existing services create all synthetic records. Only
this QA process freezes the business date; production has no date override.
KG_QA_OUT/--directory must be outside the source tree and is never uploaded.
"""
import argparse
import base64
from datetime import date
import io
import json
import os
from pathlib import Path
import re
import uuid

from tests import qa_live_pages as QA


BUSINESS_DAY = date(2026, 11, 18)
ORIGIN = 'https://127.0.0.1:8532'
FIXTURE = 'daily-home-attendance-v1'
SOURCE = Path(__file__).resolve().parents[1]


def freeze_business_day():
    import monthly_finance as F
    F.today = lambda: BUSINESS_DAY


def private_directory(root):
    root = root.resolve()
    if root == SOURCE or SOURCE in root.parents:
        raise RuntimeError('Keep attendance QA state and TLS files outside the source tree')
    return root


def owned_state(root):
    state = json.loads((root / 'state.json').read_text(encoding='utf-8'))
    values = QA.guard(state['dsn'])
    if (state.get('fixture') != FIXTURE or state.get('origin') != ORIGIN
            or state.get('business_day') != BUSINESS_DAY.isoformat()
            or not re.fullmatch(r'original_pages_qa_[0-9a-f]{32}', state.get('schema', ''))
            or values.get('options') != '-c search_path=' + state['schema']):
        raise RuntimeError('Use only this private attendance QA fixture')
    return state


def setup(root):
    root = private_directory(root)
    if (root / 'state.json').exists():
        raise RuntimeError('An existing QA fixture must be stopped and cleaned up first')
    freeze_business_day()
    try:
        QA.setup(root)
        state = json.loads((root / 'state.json').read_text(encoding='utf-8'))
        state.update(origin=ORIGIN, business_day=BUSINESS_DAY.isoformat(), fixture=FIXTURE)
        import web_runtime as W
        import db
        import access_control as A
        import records as R
        import school_departments as D
        from live_pages import mutate
        from PIL import Image

        image = io.BytesIO()
        Image.new('RGB', (80, 80), '#69b5a7').save(image, format='PNG')
        photo = base64.b64encode(image.getvalue()).decode('ascii')
        with W.request_context(state['dsn']):
            token = A.login(state['username'], state['password'])
            with W.request_context(state['dsn'], {'auth_session': token}):
                conn = db.new_transaction_connection()
                try:
                    profile = A.refresh(conn)
                    conn.commit()
                    conn.autocommit = True
                    with conn.cursor() as cursor:
                        cursor.execute('SELECT MAX(version) AS version FROM app_schema_migrations')
                        if cursor.fetchone()['version'] != 21:
                            raise RuntimeError('Attendance QA requires official schema version 21')
                        cursor.execute('SELECT * FROM school_departments ORDER BY department_id')
                        initial = cursor.fetchall()
                    if len(initial) != 1:
                        raise RuntimeError('Use a newly created isolated attendance QA schema')
                    # Reuse the empty class from the base fixture rather than
                    # accidentally seeding a third, unrelated class.
                    first = initial[0]
                    mutate(conn, 'records.change', dict(type='departments', mode='edit',
                        id=first['department_id'], revision=R.revision(first),
                        values={'name': 'قسم البراعم'}, confirmed=True,
                        reason='Synthetic attendance fixture class'), profile)
                    sections = [first['department_id'], D.create('قسم الزهور')]
                    students = []
                    scenarios = [
                        ('مريم أحمد', '2026-10-08', 0),
                        ('محمد سالم', '2026-10-11', 0),
                        ('خديجة علي', '2026-10-12', 1000),
                        ('أحمد محمود', '2026-10-17', 0),
                        ('آمنة المختار', '2026-10-29', 1000),
                        ('زينب محمد', '2026-09-08', 3000),
                        ('عمر عبد الله', '2026-10-12', 18000),
                    ]
                    for index, (name, anchor, paid) in enumerate(scenarios):
                        created = mutate(conn, 'students.create', dict(
                            department_id=sections[index % 2], name=name,
                            birth=f'2022-0{index % 4 + 1}-12',
                            gender='ذكر' if index % 2 else 'أنثى',
                            father='والد ' + name.split()[0], fatherPhone=str(22000000 + index),
                            mother='والدة ' + name.split()[0], motherPhone=str(33000000 + index),
                            mode='pay', amount=str(paid), registration=index == 4, gilet=False,
                            start_date=anchor, photo=photo, request_token=str(uuid.uuid4())), profile)
                        students.append(created['id'])
                    teachers = []
                    for index, name in enumerate(('فاطمة أحمد', 'محمد محمود', 'مريم سالم')):
                        created = mutate(conn, 'tools.change', dict(table='teachers', mode='create',
                            values=dict(full_name=name, national_id=str(97000001 + index),
                                mobile=str(44000001 + index), salary='12000', hire_date='2026-09-01',
                                department_id=sections[index % 2]), confirmed=True,
                            reason='Synthetic attendance fixture teacher', request_token=str(uuid.uuid4())), profile)
                        teachers.append(str(created['id']))
                    history = {
                        '2026-11-18': (['present'] * 3 + ['absent'] * 2 + ['excused'], ['present'] * 2 + ['excused']),
                        '2026-11-17': (['present'] * 6 + ['absent'], ['present'] * 3),
                        '2026-11-16': (['present'] * 5 + ['absent', 'excused'], ['present'] * 2 + ['absent']),
                        '2026-11-11': (['present'] * 7, ['present'] * 3),
                    }
                    for on, (student_statuses, teacher_statuses) in history.items():
                        for kind, ids, statuses in (('students', students, student_statuses), ('teachers', teachers, teacher_statuses)):
                            entries = [dict(person=ident, status=status,
                                excuse='موعد طبي' if status == 'excused' else '', revision=0)
                                for ident, status in zip(ids, statuses)]
                            mutate(conn, 'attendance.save', dict(kind=kind, date=on, entries=entries,
                                reason='Synthetic saved attendance fixture'), profile)
                finally:
                    conn.close()
        (root / 'state.json').write_text(json.dumps(state), encoding='utf-8')
        (root / 'state.json').chmod(0o600)
    except BaseException:
        if (root / 'state.json').exists():
            QA.cleanup(root)
        raise
    print('ISOLATED_DAILY_ATTENDANCE_FIXTURE_READY')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'serve', 'cleanup'))
    parser.add_argument('--directory', type=Path, default=os.environ.get('KG_QA_OUT'))
    args = parser.parse_args()
    if args.directory is None:
        parser.error('Set KG_QA_OUT or provide --directory outside the source tree')
    root = private_directory(Path(args.directory))
    if args.action == 'setup':
        setup(root)
    elif args.action == 'cleanup':
        owned_state(root)
        QA.cleanup(root)
    else:
        state = owned_state(root)
        freeze_business_day()
        import uvicorn
        from live_pages import make_app
        uvicorn.run(make_app(state['dsn'], state['origin']), host='127.0.0.1', port=8532,
                    access_log=False, proxy_headers=False,
                    ssl_keyfile=str(root / 'tls.key'), ssl_certfile=str(root / 'tls.crt'))


if __name__ == '__main__':
    main()
