"""Liveness/readiness endpoints."""


def test_health_is_ok_without_dependencies(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_200_when_session_loads(client):
    # conftest's client overrides get_session with a FakeSession → ready.
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_ready_503_when_not_connected(client):
    import deps
    from fastapi import HTTPException
    from main import app

    def not_connected():
        raise HTTPException(status_code=503, detail="not connected")

    app.dependency_overrides[deps.get_session] = not_connected
    assert client.get("/ready").status_code == 503
