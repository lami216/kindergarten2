"""Financial views must use the authenticated identity, never an invented one."""
from unittest.mock import patch
import pytest
from sections import monthly_payments as M

@pytest.mark.parametrize('session',[{}, {'auth_user':None}, {'auth_user':''}, {'auth_user':'  \t '}])
def test_financial_actor_requires_session_identity(session):
    with patch.object(M.st,'session_state',session):
        with pytest.raises(ValueError,match='هوية'):
            M.actor()

def test_financial_actor_uses_normalized_session_identity():
    with patch.object(M.st,'session_state',{'auth_user':'  qa-operator  '}):
        assert M.actor()=='qa-operator'
