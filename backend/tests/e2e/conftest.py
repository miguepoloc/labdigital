"""E2E: `TestClient` contra la app real (`backend.entrypoints.web.app`) y Postgres real.

El cliente usa `https://testserver` (las cookies son `Secure`) y rutas públicas completas
(`/labdigital/api/v1/...`) para que el tarro de cookies aplique de verdad los `Path`."""

from collections.abc import Callable, Generator
import dataclasses

from fastapi import testclient
import pytest
import sqlalchemy as sa

from backend.commons.adapters import unit_of_work
from backend.entrypoints.web import app as app_module
from backend.entrypoints.worker import main as worker
from tests import capturing, helpers

API = "/labdigital/api/v1"
ORIGIN = "https://testserver"
CSRF = {"X-Requested-With": "labdigital", "Origin": ORIGIN}
PASSWORD = "caballo-bateria-grapa"


@dataclasses.dataclass
class Env:
    mailer: capturing.CapturingMailer
    make_client: Callable[[], testclient.TestClient]

    def deliver(self) -> None:
        worker.run_once(unit_of_work.build(), worker.build_handlers(self.mailer))

    def last_token(self, email: str) -> str:
        self.deliver()
        return helpers.token_from_message(self.mailer.to(email)[-1])

    def signup(
        self, email: str, *, full_name: str = "Ada Lovelace", remember: bool = True
    ) -> testclient.TestClient:
        client = self.make_client()
        response = client.post(
            f"{API}/auth/register",
            json={
                "email": email,
                "full_name": full_name,
                "password": PASSWORD,
                "accept_data_policy": True,
            },
            headers=CSRF,
        )
        assert response.status_code == 202, response.text
        verified = client.post(
            f"{API}/auth/verify-email", json={"token": self.last_token(email)}, headers=CSRF
        )
        assert verified.status_code == 204, verified.text
        login = client.post(
            f"{API}/auth/login",
            json={"email": email, "password": PASSWORD, "remember": remember},
            headers=CSRF,
        )
        assert login.status_code == 200, login.text
        return client

    def login(self, email: str, password: str = PASSWORD) -> testclient.TestClient:
        client = self.make_client()
        response = client.post(
            f"{API}/auth/login",
            json={"email": email, "password": password, "remember": True},
            headers=CSRF,
        )
        assert response.status_code == 200, response.text
        return client


@pytest.fixture
def env(db: sa.Engine) -> Generator[Env]:
    clients: list[testclient.TestClient] = []

    def make_client() -> testclient.TestClient:
        client = testclient.TestClient(app_module.app, base_url=ORIGIN)
        clients.append(client)
        return client

    yield Env(mailer=capturing.CapturingMailer(), make_client=make_client)
    for client in clients:
        client.close()
