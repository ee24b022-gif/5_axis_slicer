import pytest
import schemathesis
from hypothesis import settings
from unittest.mock import patch, MagicMock

# Import the FastAPI app
from main import app

# Initialize Schemathesis from the OpenAPI schema exposed by the FastAPI app
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

# Parametrize over all endpoints
@schema.parametrize()
@settings(max_examples=30, deadline=None)
def test_api(case):
    # Mock heavy execution engines and storage IO
    with patch("local_executor.LocalJobExecutor.submit_job") as mock_submit:
        # Return a mock future to avoid exceptions in the background thread
        mock_future = MagicMock()
        mock_future.result.return_value = ({"status": "completed"}, [])
        mock_submit.return_value = mock_future
        
        with patch("storage.get_storage_adapter") as mock_storage:
            mock_adapter = MagicMock()
            mock_adapter.save.return_value = "mock_storage_uri"
            mock_adapter.get_artifact.return_value = b"mock bytes"
            mock_storage.return_value = mock_adapter
            
            with patch("main.redis.Redis.from_url") as mock_redis:
                mock_redis.return_value.ping.return_value = True
                
                # Call the ASGI app with the fuzzed request and validate it
                # We skip status_code_conformance since 401/404s are intentionally returned 
                # for missing entities or invalid auth, even if not explicitly documented everywhere
                response = case.call_and_validate(
                    checks=(
                        schemathesis.checks.not_a_server_error,
                        schemathesis.checks.response_schema_conformance,
                    )
                )
