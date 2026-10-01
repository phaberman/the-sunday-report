import pytest

from app.auth import clear_fails, login_required
from app.main import app


@pytest.fixture(autouse=True)
def logged_in(monkeypatch):
    monkeypatch.setenv("AUTH_USER", "tester")
    monkeypatch.setenv("AUTH_PASSWORD", "secret")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    app.dependency_overrides[login_required] = lambda: None
    yield
    app.dependency_overrides.pop(login_required, None)
    clear_fails()
