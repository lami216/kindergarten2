"""Original Pages shell backed by real authenticated services; no demo identity."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest


def test_request_identities_are_isolated_and_reset():
    import web_runtime as W
    def identify(name):
        with W.request_context('isolated',{'auth_user':name}):
            assert W.state()['auth_user']==name
            with W.request_context('other',{'auth_user':'nested'}):
                assert W.state()['auth_user']=='nested'
            return W.state()['auth_user']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(identify,['first','second']))==['first','second']
    assert W.active() is None


def test_web_authorization_never_uses_a_streamlit_identity():
    import access_control as A
    import web_runtime as W
    from tests.qa_auth import ORIGINAL
    with W.request_context('isolated',{}):
        assert not ORIGINAL['can']('students.view')
        with pytest.raises(A.AccessDenied): ORIGINAL['current']()


def test_original_design_assets_are_served_not_rebuilt():
    import live_pages
    root=Path(__file__).resolve().parents[1]
    assert live_pages.DESIGN_ROOT==root/'docs'
    html=live_pages.index_html()
    assert '<section id="content"' in html
    assert 'live/bridge.js' in html
    assert 'live/runtime.js' in html
    for filename in ('preview.css','student-profile.js','edit-windows.js'):
        assert filename in html
    assert 'iframe' not in html
