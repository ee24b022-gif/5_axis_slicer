import pytest
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal, Base, engine
from models import User, RefreshToken
from auth_service import get_password_hash
import uuid

# Recreate tables for clean state
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)

@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def test_user(db):
    user = db.query(User).filter(User.username == "testuser").first()
    if not user:
        user = User(
            username="testuser",
            email="testuser@example.com",
            hashed_password=get_password_hash("testpassword"),
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

@pytest.fixture
def inactive_user(db):
    user = db.query(User).filter(User.username == "inactiveuser").first()
    if not user:
        user = User(
            username="inactiveuser",
            email="inactive@example.com",
            hashed_password=get_password_hash("testpassword"),
            is_active=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def test_login_success(test_user):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in response.cookies

def test_login_invalid_credentials(test_user):
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_login_inactive_user(inactive_user):
    response = client.post(
        "/auth/login",
        data={"username": "inactiveuser", "password": "testpassword"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Inactive user"

def test_refresh_token(test_user, db):
    # First login to get the refresh token
    login_response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"}
    )
    refresh_token = login_response.cookies.get("refresh_token")
    assert refresh_token is not None

    # Now refresh
    client.cookies.set("refresh_token", refresh_token)
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert "access_token" in data
    
    new_refresh_token = refresh_response.cookies.get("refresh_token")
    assert new_refresh_token is not None
    assert new_refresh_token != refresh_token
    
    # Try reusing the old one
    client.cookies.set("refresh_token", refresh_token)
    reuse_response = client.post("/auth/refresh")
    assert reuse_response.status_code == 401
    assert reuse_response.json()["detail"] == "Refresh token revoked"

def test_logout(test_user):
    login_response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpassword"}
    )
    refresh_token = login_response.cookies.get("refresh_token")
    
    client.cookies.set("refresh_token", refresh_token)
    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200
    
    # Verify cookie is cleared (FastAPI test client deletes it if max_age=0/expires=past)
    # Trying to refresh should now fail
    client.cookies.set("refresh_token", refresh_token)
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401
    assert refresh_response.json()["detail"] == "Refresh token revoked"

def test_get_me(test_user):
    saved_overrides = app.dependency_overrides.copy()
    try:
        app.dependency_overrides.clear()
        
        login_response = client.post(
            "/auth/login",
            data={"username": "testuser", "password": "testpassword"}
        )
        access_token = login_response.json()["access_token"]
        
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "testuser@example.com"
    finally:
        # Reapply global mock overrides for subsequent test files
        app.dependency_overrides.update(saved_overrides)