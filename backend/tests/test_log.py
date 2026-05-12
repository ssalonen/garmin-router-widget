def test_post_log_returns_ok(client):
    response = client.post("/api/log", json={"level": "INFO", "msg": "hello"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_post_log_accepts_full_payload(client):
    payload = {
        "ts": 1234567890,
        "level": "ERROR",
        "msg": "HTTP request failed",
        "state": "LOADING_LIST",
        "http_status": -300,
        "duration_ms": 3200,
    }
    response = client.post("/api/log", json=payload)
    assert response.status_code == 200


def test_post_log_accepts_empty_payload(client):
    response = client.post("/api/log", json={})
    assert response.status_code == 200


def test_get_logs_returns_stored_entries(client):
    client.post("/api/log", json={"level": "INFO", "msg": "entry1"})
    client.post("/api/log", json={"level": "ERROR", "msg": "entry2"})

    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.json()
    assert len(data["logs"]) == 2
    msgs = [log["payload"]["msg"] for log in data["logs"]]
    assert "entry1" in msgs
    assert "entry2" in msgs


def test_get_logs_filter_by_level(client):
    client.post("/api/log", json={"level": "INFO", "msg": "info"})
    client.post("/api/log", json={"level": "ERROR", "msg": "error"})

    response = client.get("/api/logs?level=ERROR")
    assert response.status_code == 200
    logs = response.json()["logs"]
    assert len(logs) == 1
    assert logs[0]["level"] == "ERROR"


def test_get_logs_respects_limit(client):
    for i in range(10):
        client.post("/api/log", json={"msg": f"entry{i}"})

    response = client.get("/api/logs?n=3")
    assert len(response.json()["logs"]) == 3
