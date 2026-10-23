"""Real Streamlit/Starlette HTTP image, ZIP and PDF responses after upgrade."""
import io
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

from PIL import Image
from playwright.sync_api import sync_playwright, expect
from pypdf import PdfReader


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'visual-evidence' / 'dependency-responses'
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    with (out / 'server.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run',
            str(root / 'tests/dependency_responses_app.py'), '--server.address', '127.0.0.1',
            '--server.port', str(port), '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false'], cwd=root, stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url + '/_stcore/health', timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Streamlit exited; see server.log')
                    time.sleep(.2)
            else:
                raise RuntimeError('Streamlit health timeout')
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page(accept_downloads=True)
                    page.goto(url)
                    image = page.locator('[data-testid="stImage"] img')
                    expect(image).to_be_visible(timeout=30000)
                    response = page.request.get(image.get_attribute('src'))
                    assert response.ok
                    with Image.open(io.BytesIO(response.body()), formats=('PNG', 'JPEG', 'WEBP')) as decoded:
                        decoded.load()
                        assert decoded.size == (80, 60)
                    for kind in ('ZIP', 'PDF'):
                        with page.expect_download() as download:
                            page.get_by_role('button', name=kind + ' compatibility', exact=True).click()
                        path = out / ('synthetic.' + kind.lower())
                        download.value.save_as(path)
                        if kind == 'ZIP':
                            with zipfile.ZipFile(path) as z:
                                assert z.testzip() is None
                                assert z.read('synthetic.txt') == b'package-response-check'
                        else:
                            assert '1200 MRO' in PdfReader(path).pages[0].extract_text()
                    assert not page.locator('[data-testid="stException"]').count()
                    print('DEPENDENCY_RESPONSES_OK: real image decode, ZIP contents and PDF text')
                finally:
                    browser.close()
        finally:
            server.terminate()
            server.wait(timeout=20)


if __name__ == '__main__':
    main()
