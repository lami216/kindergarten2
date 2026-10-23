"""Private, normalized student portraits with independent optimistic revisions."""
import hashlib
import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
import access_control as A
import db
import record_history as H

MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
ALLOWED_FORMATS = ('JPEG', 'PNG', 'WEBP')


def normalize(raw):
    if not isinstance(raw, (bytes, bytearray, memoryview)) or not raw:
        raise ValueError('اختر صورة أولًا.')
    raw = bytes(raw)
    if len(raw) > MAX_UPLOAD:
        raise ValueError('حجم الصورة أكبر من 5 ميغابايت؛ اختر صورة أصغر.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            # Restrict decoder selection before inspecting untrusted content.
            # Filename/MIME and a format check after open cannot enforce this.
            with Image.open(io.BytesIO(raw), formats=ALLOWED_FORMATS) as probe:
                if probe.format not in ALLOWED_FORMATS:
                    raise ValueError('الصورة يجب أن تكون JPG أو PNG أو WebP.')
                if getattr(probe, 'n_frames', 1) != 1:
                    raise ValueError('اختر صورة ثابتة، وليست صورة متحركة.')
                if probe.width * probe.height > MAX_PIXELS:
                    raise ValueError('أبعاد الصورة كبيرة جدًا؛ اختر صورة أصغر من 12 مليون بكسل.')
                probe.verify()
            with Image.open(io.BytesIO(raw), formats=ALLOWED_FORMATS) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                # Flatten transparency and omit EXIF/location/name metadata.
                rgba = image.convert('RGBA')
                clean = Image.new('RGB', rgba.size, 'white')
                clean.paste(rgba, mask=rgba.getchannel('A'))
                output = io.BytesIO()
                clean.save(output, format='JPEG', quality=86, optimize=True)
                data = output.getvalue()
                return dict(image_data=data, image_sha256=hashlib.sha256(data).hexdigest(),
                            width=clean.width, height=clean.height, byte_size=len(data), mime_type='image/jpeg')
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('تعذّر قراءة الصورة. اختر ملف صورة سليمًا بصيغة JPG أو PNG أو WebP.') from None


def migrate(conn):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS student_photos (
            student_id VARCHAR(20) PRIMARY KEY REFERENCES students(student_id),
            image_data BYTEA, image_sha256 TEXT, width INTEGER, height INTEGER,
            byte_size INTEGER, mime_type TEXT, revision INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK ((image_data IS NULL AND image_sha256 IS NULL AND width IS NULL AND height IS NULL
                     AND byte_size IS NULL AND mime_type IS NULL)
                OR (image_data IS NOT NULL AND image_sha256 IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL
                    AND byte_size IS NOT NULL AND mime_type IS NOT NULL AND width BETWEEN 1 AND 640
                    AND height BETWEEN 1 AND 640 AND byte_size=octet_length(image_data)
                    AND mime_type='image/jpeg')));''')


def insert_in_transaction(cursor, student_id, photo):
    cursor.execute('''INSERT INTO student_photos
        (student_id,image_data,image_sha256,width,height,byte_size,mime_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s)''', (student_id, *[photo[k] for k in
            ('image_data','image_sha256','width','height','byte_size','mime_type')]))


def get(conn, student_id):
    with conn.cursor() as c:
        A.require(c, 'students.view', lock=False)
        c.execute('SELECT * FROM student_photos WHERE student_id=%s', (student_id,))
        row = c.fetchone()
        return dict(row) if row else dict(student_id=student_id, revision=0, image_data=None)


def save(student_id, raw=None, *, expected, remove=False, reason=''):
    if not reason.strip():
        raise ValueError('أدخل سبب تغيير الصورة.')
    photo = None if remove else normalize(raw)
    conn = db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            A.require(c, 'students.edit')
            H.context(c, None, reason.strip())
            # Student lock serializes first upload, replacement, removal and archive.
            c.execute('SELECT archived_at FROM students WHERE student_id=%s FOR UPDATE', (student_id,))
            child = c.fetchone()
            if not child: raise ValueError('ملف الطالب غير موجود.')
            if child['archived_at'] and not remove:
                raise ValueError('ملف الطالب مؤرشف؛ لا يمكن إضافة صورة جديدة له.')
            c.execute('SELECT * FROM student_photos WHERE student_id=%s FOR UPDATE', (student_id,))
            old = c.fetchone()
            if expected != (old['revision'] if old else 0):
                raise ValueError('تغيّرت الصورة من جلسة أخرى. حدّث الصورة قبل المحاولة مجددًا.')
            if remove and (not old or old['image_data'] is None):
                raise ValueError('لا توجد صورة لحذفها.')
            if old and photo and old['image_sha256'] == photo['image_sha256']:
                conn.commit(); return old['revision']
            if not old:
                insert_in_transaction(c, student_id, photo)
                revision = 1
            else:
                values = [photo[k] if photo else None for k in
                    ('image_data','image_sha256','width','height','byte_size','mime_type')]
                c.execute('''UPDATE student_photos SET image_data=%s,image_sha256=%s,width=%s,height=%s,
                    byte_size=%s,mime_type=%s,revision=revision+1,updated_at=now() WHERE student_id=%s
                    RETURNING revision''', (*values, student_id))
                revision = c.fetchone()['revision']
        conn.commit(); return revision
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
