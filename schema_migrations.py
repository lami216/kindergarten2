"""Run explicitly at deployment: python -m schema_migrations.

All DDL/backfills and the version marker commit together. PostgreSQL relation
locks hold concurrent writes until the old/new audit triggers are available.
Opening a Streamlit page only checks readiness; it never runs this module.
"""
import argparse
import os

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import TRANSACTION_STATUS_IDLE

VERSION = 16
LOCK = 82416100


class SchemaNotReady(RuntimeError):
    pass


def upgrade(connection):
    if connection.get_transaction_status() != TRANSACTION_STATUS_IDLE:
        raise RuntimeError('Migration requires an idle, dedicated connection')
    previous = connection.autocommit
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            cursor.execute('''CREATE TABLE IF NOT EXISTS app_schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
            cursor.execute('SELECT MAX(version) AS version FROM app_schema_migrations')
            current = cursor.fetchone()['version']
            if current is not None and current > VERSION:
                raise RuntimeError('Database is newer than this application')
            if current == VERSION:
                connection.commit()
                return False
        import db
        db._apply_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO app_schema_migrations(version) VALUES(%s)', (VERSION,))
        connection.commit()
        return True
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.autocommit = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn-env', help='Read connection URL from this environment variable')
    args = parser.parse_args()
    if args.dsn_env:
        dsn = os.environ[args.dsn_env]
    else:
        import streamlit as st
        dsn = st.secrets['postgres']['url']
    connection = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    try:
        changed = upgrade(connection)
        print(f'Schema {VERSION}: ' + ('upgraded' if changed else 'already current'))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
