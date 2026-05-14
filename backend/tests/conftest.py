import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DB_PATH", str(tmp_path / "logs.db"))


@pytest.fixture
def mock_garmin():
    mock = MagicMock()
    with patch("garmin._get_client", return_value=mock):
        yield mock


@pytest.fixture
def client(mock_garmin):
    from main import app
    return TestClient(app)
