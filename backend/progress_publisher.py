import logging
import redis
from progress_model import StageProgressEvent
from config import settings

logger = logging.getLogger(__name__)

class RedisProgressPublisher:
    """
    Broadcasts StageProgressEvent to a Redis pub/sub channel.
    Swallows connection errors to ensure Redis outage does not erase persisted job state 
    or crash the geometry processing worker.
    """
    def __init__(self, redis_url: str = None):
        url = redis_url or settings.redis_url
        try:
            self.client = redis.Redis.from_url(url)
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
            self.client = None

    def publish(self, event: StageProgressEvent) -> None:
        if not self.client:
            return
            
        try:
            channel = f"job_progress:{event.job_id}"
            payload = event.model_dump_json()
            self.client.publish(channel, payload)
        except redis.exceptions.RedisError as e:
            logger.warning(f"Failed to publish progress to Redis for job {event.job_id}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error publishing progress for job {event.job_id}: {e}")
