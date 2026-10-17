"""Image validation and real private, audited, atomic student photo operations."""
import base64
import io
import json
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
import access_control as A
import db
import records as R
import student_photos as P
import monthly_finance as F
from tests.test_access_control import access, worker, sign, child


def picture(color='teal',size=(900,700),fmt='PNG'):
    output=io.BytesIO();Image.new('RGB',size,color).save(output,format=fmt);return output.getvalue()


def test_normalized_image_size_metadata_and_transparency():
    original=Image.new('RGBA',(1200,600),(255,0,0,0));output=io.BytesIO()
    exif=Image.Exif();exif[270]='PRIVATE camera description';exif[274]=6
    original.convert('RGB').save(output,format='JPEG',exif=exif)
    result=P.normalize(output.getvalue())
    assert (result['width'],result['height'])==(320,640)
    with Image.open(io.BytesIO(result['image_data'])) as normalized:
        assert normalized.format=='JPEG' and not normalized.getexif()
    output=io.BytesIO();original.save(output,format='PNG')
    with Image.open(io.BytesIO(P.normalize(output.getvalue())['image_data'])) as normalized:
        assert normalized.getpixel((0,0))==(255,255,255)
    assert b'PRIVATE camera' not in result['image_data']


@pytest.mark.parametrize('raw',[b'',b'not an image',b'<svg xmlns="http://www.w3.org/2000/svg"/>',picture(fmt='GIF')])
def test_invalid_content_rejected(raw):
    with pytest.raises(ValueError): P.normalize(raw)


def test_limits_and_animated_webp_rejected(monkeypatch):
    with pytest.raises(ValueError,match='5'): P.normalize(b'x'*(P.MAX_UPLOAD+1))
    monkeypatch.setattr(P,'MAX_PIXELS',100)
    with pytest.raises(ValueError,match='أبعاد'): P.normalize(picture(size=(11,10)))
    monkeypatch.setattr(P,'MAX_PIXELS',12_000_000)
    out=io.BytesIO();Image.new('RGB',(10,10),'red').save(out,format='WEBP',save_all=True,
        append_images=[Image.new('RGB',(10,10),'blue')],duration=100,loop=0)
    with pytest.raises(ValueError,match='متحركة'): P.normalize(out.getvalue())


def intake(photo,request=None,cash=0):
    data=dict(full_name='طفل الصورة',birth_date='2022-01-01',gender='ذكر',birth_place='',address='',
        medical_details='معلومة صحية',allergies='',general_notes='',authorized_pickups=[])
    family=dict(father_name='أب الصورة',father_mobile='22334455',mother_name='',mother_mobile='',contact_email='')
    return db.save_child_with_family(data,family,None,request or str(uuid.uuid4()),photo=photo,
        finance=dict(mode='regular',cash=cash,registration=bool(cash),gilet=False,start_date=str(F.today()),payer='أب الصورة'))


def test_create_only_photo_intake_is_atomic_idempotent_and_private(access):
    conn,_,_,owner_token=access
    uid,token=worker(['students.create']);sign(token)
    request=str(uuid.uuid4());raw=picture();sid,new=intake(raw,request)
    assert new and intake(raw,request)==(sid,False)
    with pytest.raises(ValueError,match='تعارض'): intake(picture('red'),request)
    with pytest.raises(A.AccessDenied): P.get(conn,sid)
    with pytest.raises(A.AccessDenied): P.save(sid,raw,expected=1,reason='محاولة تعديل')
    sign(owner_token)
    photo=P.get(conn,sid);assert photo['revision']==1 and bytes(photo['image_data'])==P.normalize(raw)['image_data']
    with conn.cursor() as c:
        c.execute("SELECT actor_user_id,after_state FROM record_changes WHERE table_name='student_photos' AND record_key=%s",(sid,))
        events=c.fetchall();assert len(events)==1 and str(events[0]['actor_user_id'])==uid
        assert 'image_data' not in events[0]['after_state']
        c.execute('SELECT COUNT(*) AS n FROM students');count=c.fetchone()['n']
    with pytest.raises(ValueError): intake(b'invalid photo')
    with pytest.raises(ValueError): intake(picture(),cash=1)
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM students');assert c.fetchone()['n']==count


def test_replace_remove_stale_version_and_unrelated_child_edit(access):
    conn,_,_,owner_token=access;sid,_=intake(picture())
    with conn.cursor() as c:
        c.execute('SELECT * FROM students WHERE student_id=%s',(sid,));before=dict(c.fetchone())
    _,viewer=worker(['students.view'],name='viewer');sign(viewer)
    assert P.get(conn,sid)['image_data']
    with pytest.raises(A.AccessDenied): P.save(sid,picture('red'),expected=1,reason='مرفوض')
    sign(owner_token);_,editor=worker(['students.edit'],name='editor');sign(editor)
    assert P.save(sid,picture('red'),expected=1,reason='تحديث الصورة')==2
    with pytest.raises(ValueError,match='تغيّرت'): P.save(sid,expected=1,remove=True,reason='نافذة قديمة')
    # Portrait changes have their own revision; they do not stale text drafts.
    R.edit('students',sid,{'address':'العنوان الجديد'},reason='تعديل العنوان',actor='spoofed',expected=R.revision(before))
    assert P.get(conn,sid)['revision']==2
    assert P.save(sid,expected=2,remove=True,reason='طلب الأسرة')==3
    assert P.get(conn,sid)['image_data'] is None
    assert P.save(sid,picture('blue'),expected=3,reason='صورة جديدة')==4
    with pytest.raises(ValueError,match='تغيّرت'): P.save(sid,picture(),expected=1,reason='نسخة قديمة')
    with conn.cursor() as c:
        c.execute("SELECT action,before_state,after_state FROM record_changes WHERE table_name='student_photos' AND record_key=%s ORDER BY change_id",(sid,))
        events=c.fetchall();assert [e['action'] for e in events]==['created','updated','deleted','created']
        assert all('image_data' not in (e['before_state'] or {}) and 'image_data' not in (e['after_state'] or {}) for e in events)
        c.execute('SELECT medical_details,address FROM students WHERE student_id=%s',(sid,))
        assert dict(c.fetchone())==dict(medical_details='معلومة صحية',address='العنوان الجديد')


def test_concurrent_photo_replacement_accepts_one_and_keeps_export_complete(access):
    conn,_,_,_=access;sid,_=intake(picture())
    def replace(color):
        try: return P.save(sid,picture(color),expected=1,reason='تعديل متزامن')
        except ValueError: return 'stale'
    with ThreadPoolExecutor(2) as pool: assert sorted(map(str,pool.map(replace,['red','blue'])))==['2','stale']
    from data_export import build_export
    archive=build_export()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        photos=json.loads(z.read('data/student_photos.json'))
        saved=next(r for r in photos if r['student_id']==sid)
        assert base64.b64decode(saved['image_data']['base64'])==bytes(P.get(conn,sid)['image_data'])
    with conn.cursor() as c:
        c.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(sid,))
    with pytest.raises(ValueError,match='مؤرشف'): P.save(sid,picture(),expected=2,reason='صورة بعد الأرشفة')
    assert P.save(sid,expected=2,remove=True,reason='إزالة الصورة من الأرشيف')==3
