from fastapi.testclient import TestClient

from app.main import app


def test_html_pages_render():
    with TestClient(app) as client:
        for path in ("/", "/past", "/results", "/season", "/upload"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "The Sunday Report" in r.text


def test_results_htmx_returns_board_fragment():
    with TestClient(app) as client:
        r = client.get("/results", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'id="board"' in r.text
        assert "<html" not in r.text.lower()
