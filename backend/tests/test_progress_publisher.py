import pytest
from unittest.mock import patch, MagicMock
from progress_publisher import RedisProgressPublisher
from progress_model import StageProgressEvent
from enums import JobStage
import redis
import json

@pytest.fixture
def mock_redis():
    with patch("progress_publisher.redis.Redis.from_url") as mock:
        yield mock

def test_progress_publisher_success(mock_redis):
    # Setup mock
    mock_client = MagicMock()
    mock_redis.return_value = mock_client
    
    publisher = RedisProgressPublisher(redis_url="redis://fake:6379/0")
    
    # Create event
    event = StageProgressEvent(
        job_id="test-job-id",
        stage=JobStage.SECTIONING,
        progress=0.5
    )
    
    publisher.publish(event)
    
    # Verify publish was called correctly
    assert mock_client.publish.called
    args, kwargs = mock_client.publish.call_args
    assert args[0] == "job_progress:test-job-id"
    
    payload = json.loads(args[1])
    assert payload["job_id"] == "test-job-id"
    assert payload["stage"] == "sectioning"
    assert payload["progress"] == 0.5
    assert "timestamp" in payload

def test_progress_publisher_initialization_error(mock_redis):
    # Setup mock to raise error on init
    mock_redis.side_effect = redis.exceptions.ConnectionError("Redis is down")
    
    publisher = RedisProgressPublisher(redis_url="redis://fake:6379/0")
    
    # Verify client is None and exception was swallowed
    assert publisher.client is None
    
    event = StageProgressEvent(
        job_id="test-job-id",
        stage=JobStage.SECTIONING,
        progress=0.5
    )
    
    # Publishing should not raise an error
    publisher.publish(event)

def test_progress_publisher_publish_error(mock_redis):
    # Setup mock to raise error on publish
    mock_client = MagicMock()
    mock_client.publish.side_effect = redis.exceptions.RedisError("Publish failed")
    mock_redis.return_value = mock_client
    
    publisher = RedisProgressPublisher(redis_url="redis://fake:6379/0")
    
    event = StageProgressEvent(
        job_id="test-job-id",
        stage=JobStage.SECTIONING,
        progress=0.5
    )
    
    # Publishing should not raise an error
    publisher.publish(event)
    
    # Verify publish was actually attempted
    assert mock_client.publish.called
