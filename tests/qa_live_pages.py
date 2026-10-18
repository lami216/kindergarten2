"""Reproducible PRIVATE fixture for the original Pages integration.

Requires a disposable loopback database literally named kindergarten_test.
Generates random test credentials/certificates OUTSIDE the repo; never upload it.
Not imported by production. No production bypass is provided.
"""
import argparse,json,os,re,secrets,subprocess,uuid
from pathlib import Path
from urllib.parse import urlparse
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn,parse_dsn


def guard(dsn):
    values=parse_dsn(dsn)
    if values.get('host') not in ('127.0.0.1','localhost') or values.get('dbname')!='kindergarten_test':
        raise RuntimeError('QA requires a disposable loopback kindergarten_test database')
    return values


def setup(root):
    dsn=os.environ['TEST_POSTGRES_DSN'];guard(dsn)
    root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
    if (root/'state.json').exists(): raise RuntimeError('Stop QA services and run cleanup before recreating the fixture')
    schema='original_pages_qa_'+uuid.uuid4().hex
    admin=psycopg2.connect(dsn);admin.autocommit=True
    with admin.cursor() as c: c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    admin.close()
    isolated=make_dsn(dsn,options='-c search_path='+schema)
    import web_runtime as W
    import db,schema_migrations as M,access_control as A,monthly_finance as F
    password=secrets.token_urlsafe(24)
    with W.request_context(isolated):
        conn=db.new_transaction_connection();conn.commit();M.upgrade(conn);conn.close()
        A.bootstrap('مدير اختبار مستقل','qa_owner',password)
        token=A.login('qa_owner',password)
        with W.request_context(isolated,{'auth_session':token}):F.update_tariffs(1000,2000,3000,'qa_owner')
    state={'dsn':isolated,'username':'qa_owner','password':password,'origin':'https://127.0.0.1:8520','schema':schema}
    (root/'state.json').write_text(json.dumps(state));(root/'state.json').chmod(0o600)
    (root/'.streamlit').mkdir(exist_ok=True)
    config=root/'.streamlit/secrets.toml'
    config.write_text('[postgres]\nurl = '+json.dumps(isolated)+'\n');config.chmod(0o600)
    with (root/'certificate-setup.log').open('w') as log:
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=127.0.0.1',
            '-addext','subjectAltName=IP:127.0.0.1','-keyout',str(root/'tls.key'),'-out',str(root/'tls.crt')],
            check=True,stdout=log,stderr=log)
    (root/'tls.key').chmod(0o600)
    from PIL import Image
    Image.new('RGB',(96,96),'#26976a').save(root/'portrait.png')
    for directory in ('client-temp','proxy-temp'): (root/directory).mkdir(exist_ok=True)
    nginx='''pid ROOT/nginx.pid;
error_log ROOT/nginx-error.log warn;
events {worker_connections 256;}
http {
  access_log off;
  client_body_temp_path ROOT/client-temp;
  proxy_temp_path ROOT/proxy-temp;
  map $http_upgrade $connection_upgrade {default upgrade; '' close;}
  server {
    listen 127.0.0.1:8520 ssl;
    server_name 127.0.0.1;
    ssl_certificate ROOT/tls.crt;
    ssl_certificate_key ROOT/tls.key;
    client_max_body_size 8m;
    location = /management {return 308 /management/;}
    location /management/ {
      proxy_pass http://127.0.0.1:8521;
      proxy_http_version 1.1;
      proxy_set_header Host $http_host;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_read_timeout 120s;
    }
    location / {
      proxy_pass http://127.0.0.1:8522;
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-For $remote_addr;
    }
  }
}
'''.replace('ROOT',str(root))
    (root/'nginx.conf').write_text(nginx)
    print('ISOLATED_ORIGINAL_PAGES_FIXTURE_READY')


def cleanup(root):
    state=json.loads((root/'state.json').read_text());guard(state['dsn'])
    if not re.fullmatch(r'original_pages_qa_[0-9a-f]{32}',state['schema']):raise RuntimeError('Unsafe QA schema')
    conn=psycopg2.connect(state['dsn']);conn.autocommit=True
    with conn.cursor() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(state['schema'])))
    conn.close();(root/'state.json').unlink()
    print('OWNED_SYNTHETIC_SCHEMA_REMOVED')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('setup','serve','cleanup'))
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--proxy-backend',action='store_true')
    args=p.parse_args();root=args.directory.resolve()
    if args.action=='setup':setup(root);return
    if args.action=='cleanup':cleanup(root);return
    state=json.loads((root/'state.json').read_text());guard(state['dsn'])
    from live_pages import make_app
    import uvicorn
    uvicorn.run(make_app(state['dsn'],state['origin'],management=args.proxy_backend,
        trusted_proxies=['127.0.0.1'] if args.proxy_backend else []),
        host='127.0.0.1',port=8522 if args.proxy_backend else 8520,access_log=False,proxy_headers=False,
        ssl_keyfile=None if args.proxy_backend else str(root/'tls.key'),
        ssl_certfile=None if args.proxy_backend else str(root/'tls.crt'))


if __name__=='__main__':main()
