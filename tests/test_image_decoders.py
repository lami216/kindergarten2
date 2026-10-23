"""Benign generated fixtures only: reject decoders before opening user bytes."""
import io
from unittest.mock import patch

import pytest
from PIL import Image

import student_photos as P
from live_pages import decode_photo
import base64


def image_bytes(fmt):
    out = io.BytesIO()
    Image.new('RGB', (40, 25), 'teal').save(out, format=fmt)
    return out.getvalue()


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP'])
def test_allowed_images_reencoded_and_both_opens_restricted(fmt):
    original_open = Image.open
    with patch.object(P.Image, 'open', wraps=original_open) as opened:
        result = P.normalize(image_bytes(fmt))
    assert opened.call_count == 2
    assert all(c.kwargs.get('formats') == ('JPEG', 'PNG', 'WEBP') for c in opened.call_args_list)
    with original_open(io.BytesIO(result['image_data']), formats=('JPEG',)) as clean:
        clean.load()
        assert clean.size == (40, 25)
        assert clean.mode == 'RGB'
        assert not clean.getexif()


@pytest.mark.parametrize('fmt', ['GIF', 'BMP', 'TIFF', 'ICO', 'JPEG2000'])
@pytest.mark.parametrize('extension', ['jpg', 'png', 'webp'])
def test_other_formats_disguised_as_allowed_image_rejected(fmt, extension, tmp_path):
    # The extension and MIME accepted by the client cannot select a decoder.
    disguised = tmp_path / ('portrait.' + extension)
    disguised.write_bytes(image_bytes(fmt))
    uploaded = decode_photo(base64.b64encode(disguised.read_bytes()).decode('ascii'))
    with pytest.raises(ValueError):
        P.normalize(uploaded)


def test_unapproved_opener_never_invoked():
    # A normal BMP, not an exploit, demonstrates exclusion before header parsing.
    from PIL import BmpImagePlugin
    Image.init()
    with patch.dict(Image.OPEN, {'BMP': (lambda fp, filename: pytest.fail('BMP decoder reached'),
                                      BmpImagePlugin._accept)}):
        with pytest.raises(ValueError):
            P.normalize(image_bytes('BMP'))


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP'])
def test_truncated_allowed_images_rejected(fmt):
    raw = image_bytes(fmt)
    with pytest.raises(ValueError):
        P.normalize(raw[:len(raw) // 2])
