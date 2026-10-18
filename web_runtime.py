"""Request-local identity for the HTTP client; Streamlit remains the default.

Never share a Streamlit session/cache or a DB connection across HTTP requests.
Only the server supplies the DSN and the opaque, database-validated session token.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_request: ContextVar[dict | None] = ContextVar('kindergarten_http_request', default=None)


def active():
    return _request.get()


def state():
    request = active()
    if request is not None:
        return request['state']
    import streamlit as st
    return st.session_state


@contextmanager
def request_context(dsn, state=None):
    token = _request.set({'dsn': dsn, 'state': {} if state is None else state})
    try:
        yield _request.get()
    finally:
        _request.reset(token)
