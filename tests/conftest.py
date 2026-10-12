"""Safe, synthetic test bootstrap; cannot connect to production by accident."""
import os
from unittest.mock import patch
import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_monthly_prices():
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        yield
        return
    # Explicit name and loopback-only guard; never seed prices in app/db startup.
    from urllib.parse import urlparse
    parsed=urlparse(dsn)
    if parsed.hostname not in ("127.0.0.1","localhost") or parsed.path != "/kindergarten_test":
        raise RuntimeError("Unsafe TEST_POSTGRES_DSN; test fixture requires disposable local DB")
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import db
    import monthly_finance as F
    def isolated():
        c=psycopg2.connect(dsn,cursor_factory=RealDictCursor)
        c.autocommit=False
        return c
    admin=isolated()
    admin.autocommit=True
    try:
        with patch.object(db,"get_connection",return_value=admin):
            db.init_db()
        with patch.object(db,"new_transaction_connection",side_effect=isolated):
            F.update_tariffs(1000,2000,3000,"fixture-only")
        yield
    finally:
        admin.close()
