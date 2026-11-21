"""Regresión (revisión de seguridad, punto 1): uvicorn no debe confiar en X-Forwarded-For de
cualquier origen (`--forwarded-allow-ips "*"` permitía falsear la IP y saltarse límites)."""

import pathlib

import pytest

pytestmark = pytest.mark.unit

_DOCKERFILE = pathlib.Path(__file__).resolve().parents[4] / "Dockerfile"


def test_uvicorn_does_not_trust_forwarded_headers_from_everyone() -> None:
    text = _DOCKERFILE.read_text()
    assert "--forwarded-allow-ips" not in text
    assert "ENV FORWARDED_ALLOW_IPS=127.0.0.1" in text
    assert '"--proxy-headers"' in text
