"""Shared pytest fixtures."""

import base64
import json

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the Home Assistant test harness load custom_components/lynkco."""
    yield


def unsigned_jwt(claims: dict) -> str:
    """A syntactically valid, unsigned JWT (header.payload.signature) carrying ``claims``."""

    def encode(part: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(claims)}.signature"


@pytest.fixture
def make_token():
    """Access tokens whose claims the API client can decode without logging a traceback."""
    return unsigned_jwt
