"""Worker codes have a length floor, with no composition requirements."""
import pytest
import access_control as A


@pytest.mark.parametrize('code', ['1234', '0000', '١٢٣٤', 'abcd', '!@#$'])
def test_worker_code_round_trip(code):
    encoded = A.password_hash(code, minimum_length=4)
    assert A.verify_password(code, encoded)
    assert not A.verify_password(code + 'wrong', encoded)
    assert encoded != A.password_hash(code, minimum_length=4)


@pytest.mark.parametrize('code', ['', '123', 'a' * 129, None])
def test_worker_code_rejects_invalid_length(code):
    with pytest.raises(ValueError, match='4'):
        A.password_hash(code, minimum_length=4)


def test_owner_bootstrap_password_policy_is_unchanged():
    with pytest.raises(ValueError, match='12'):
        A.password_hash('1234')
