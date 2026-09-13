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
            latest_key = f"job_progress_latest:{event.job_id}"
            payload = event.model_dump_json()
            
            # Use pipeline to ensure atomic publish and set
            pipe = self.client.pipeline()
            pipe.set(latest_key, payload, ex=86400) # expire in 1 day
            pipe.publish(channel, payload)
            pipe.execute()
        except redis.exceptions.RedisError as e:
            logger.warning(f"Failed to publish progress to Redis for job {event.job_id}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error publishing progress for job {event.job_id}: {e}")
