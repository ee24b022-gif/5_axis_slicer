import uuid
import pytest
from main import app
from dependencies import get_current_actor
from models import User  # Import your SQLAlchemy User model

TEST_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")

class MockActor:
    def __init__(self, user=None, scopes=None):
        self.user = user or User(
            id=TEST_UUID,
            username="mockuser",
            email="mock@example.com",
            hashed_password="mockpassword",
            is_active=True
        )
        self.scopes = scopes or ["read_jobs", "write_jobs"]
        self.id = self.user.id

    @property
    def user_id(self):
        return self.user.id

@pytest.fixture
def mock_actor(test_user):
    return MockActor(user=test_user)

@pytest.fixture(scope="session", autouse=True)
def override_auth():
    app.dependency_overrides[get_current_actor] = lambda: MockActor()
    yield
    app.dependency_overrides.clear()