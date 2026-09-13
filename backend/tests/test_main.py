import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

from unittest.mock import patch

@patch("main.redis.Redis.from_url")
def test_readiness_endpoint(mock_from_url):
    mock_from_url.return_value.ping.return_value = True
    response = client.get("/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
