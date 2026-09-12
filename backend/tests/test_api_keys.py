import pytest
# Ensure get_current_actor is imported from the exact same module path used by backend/routers/api_keys.py
from dependencies import get_current_actor, Actor 
from main import app

@pytest.fixture
def auth_client(client, test_user):
    # Ensure Actor explicitly mirrors test_user's ID and instance
    test_actor = Actor(
        id=test_user.id,
        user=test_user,
        role=getattr(test_user, "role", "user") or "user"
    )
    app.dependency_overrides[get_current_actor] = lambda: test_actor
    yield client
    app.dependency_overrides.clear()