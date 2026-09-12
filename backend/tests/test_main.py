import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_readiness_endpoint():
    response = client.get("/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
