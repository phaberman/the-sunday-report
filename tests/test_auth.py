from fastapi.testclient import TestClient

from app.auth import login_required
from app.main import app


def test_anonymous_scoreboard_redirects_to_login():
    app.dependency_overrides.pop(login_required, None)
    with TestClient(app) as client:
        r = client.get("/scoreboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_sixth_attempt_is_locked_out():
    app.dependency_overrides.pop(login_required, None)
    headers = {"x-forwarded-for": "203.0.113.9"}
    with TestClient(app) as client:
        for _ in range(5):
            client.post(
                "/login",
                data={"username": "tester", "password": "nope"},
                headers=headers,
            )
        r = client.post(
            "/login",
            data={"username": "tester", "password": "secret"},
            headers=headers,
        )
    assert r.status_code == 200
    assert "Try again later." in r.text
