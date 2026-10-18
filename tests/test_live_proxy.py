"""Explicit proxy trust and coarse login limits without database or real users."""
import pytest
from starlette.testclient import TestClient
import live_pages as L

ORIGIN='https://kindergarten.test'

def test_proxy_limit_separates_clients_but_does_not_trust_unconfigured_headers(monkeypatch):
    monkeypatch.setattr(L.A,'login',lambda *args:None)
    def attempt(client,ip):
        return client.post('/api/login',json={'username':'user','password':'wrong'},
            headers={'Origin':ORIGIN,'X-Forwarded-For':ip}).status_code
    trusted=L.make_app('unused',ORIGIN,trusted_proxies=['127.0.0.1'])
    with TestClient(trusted,base_url=ORIGIN,client=('127.0.0.1',1000)) as c:
        assert [attempt(c,'192.0.2.1') for _ in range(20)]==[401]*20
        assert attempt(c,'192.0.2.1')==429
        assert attempt(c,'192.0.2.2')==401
    untrusted=L.make_app('unused',ORIGIN,trusted_proxies=['127.0.0.1'])
    with TestClient(untrusted,base_url=ORIGIN,client=('192.0.2.3',1000)) as c:
        assert [attempt(c,f'198.51.100.{i}') for i in range(20)]==[401]*20
        assert attempt(c,'198.51.100.21')==429
    default=L.make_app('unused',ORIGIN)
    with TestClient(default,base_url=ORIGIN,client=('127.0.0.1',1000)) as c:
        assert [attempt(c,f'198.51.100.{i}') for i in range(20)]==[401]*20
        assert attempt(c,'198.51.100.21')==429

def test_successful_logins_do_not_exhaust_shared_office_ip(monkeypatch):
    monkeypatch.setattr(L.A,'login',lambda *args:'synthetic-opaque-session')
    with TestClient(L.make_app('unused',ORIGIN),base_url=ORIGIN) as c:
        for _ in range(25):
            assert c.post('/api/login',json={'username':'user','password':'valid'},headers={'Origin':ORIGIN}).status_code==200

def test_limiter_expires_without_deleting_concurrent_new_window(monkeypatch):
    clock=[0.0];monkeypatch.setattr(L.time,'monotonic',lambda:clock[0])
    limit=L.LoginAttempts()
    assert [limit.reserve('ip') for _ in range(20)]==[0.0]*20
    assert limit.reserve('ip') is None
    clock[0]=301.0
    assert limit.reserve('ip')==301.0
    limit.success('ip',0.0)
    assert limit.attempts['ip']==(301.0,1)

@pytest.mark.parametrize('proxy',['*','0.0.0.0/0','unknown-host'])
def test_no_wildcard_or_unresolved_proxy_trust(proxy):
    with pytest.raises(ValueError):L.make_app('unused',ORIGIN,trusted_proxies=[proxy])
