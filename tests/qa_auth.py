"""Explicit trusted identity for pre-existing isolated finance tests only.

Production code has no QA bypass. Authentication tests restore ORIGINAL.
"""
import os
from urllib.parse import urlparse
from unittest.mock import patch
import access_control as A

ORIGINAL={name:getattr(A,name) for name in ('can','require','actor','current')}
PROFILE=dict(user_id='00000000-0000-0000-0000-000000000001',employee_name='Isolated legacy QA',
    username='qa',active=True,is_admin=True,permissions=[],auth_version=1)


def trusted():
    from contextlib import ExitStack
    stack=ExitStack()
    stack.enter_context(patch.object(A,'can',lambda permission:True))
    stack.enter_context(patch.object(A,'require',lambda cursor,permission,**kwargs:dict(PROFILE)))
    stack.enter_context(patch.object(A,'actor',lambda cursor,permission,legacy_actor=None:legacy_actor))
    stack.enter_context(patch.object(A,'current',lambda cursor=None,lock=False:dict(PROFILE)))
    return stack


_stack=None
def install():
    global _stack
    parsed=urlparse(os.environ.get('TEST_POSTGRES_DSN',''))
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.path!='/kindergarten_test':
        raise RuntimeError('Trusted QA identity requires disposable loopback database')
    if _stack is None: _stack=trusted()
