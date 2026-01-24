import logging
import tweepy
from app.config import settings

logger = logging.getLogger(__name__)

def get_client():
    return tweepy.Client(
        consumer_key=settings.TWITTER_API_KEY,
        consumer_secret=settings.TWITTER_API_SECRET,
        access_token=settings.TWITTER_ACCESS_TOKEN,
        access_token_secret=settings.TWITTER_ACCESS_TOKEN_SECRET
    )

def post_tweet(text: str) -> str:
    """
    Post a tweet to X.
    Returns the Tweet ID on success.
    Raises Exception on failure.
    """
    if settings.DRY_RUN:
        logger.info(f"[DRY RUN] Would post: {text}")
        return "dry_run_id_12345"

    try:
        client = get_client()
        response = client.create_tweet(text=text)
        if response.data:
            tweet_id = response.data['id']
            logger.info(f"Posted to X: {tweet_id}")
            return tweet_id
        else:
            raise Exception("No data in response")
    except Exception as e:
        logger.error(f"Failed to post to X: {e}")
        raise e
