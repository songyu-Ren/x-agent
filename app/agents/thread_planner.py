import json

from openai import OpenAI

from app.agents.base import BaseAgent
from app.config import settings
from app.models import Materials, StyleProfile, ThreadPlan, TopicPlan
from app.runtime_config import get_bool, get_int
from app.services.retry import with_retry


class ThreadPlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__("ThreadPlannerAgent")
        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    def run(self, input_data: tuple[TopicPlan, Materials, StyleProfile]) -> ThreadPlan:
        topic_plan, materials, style = input_data

        thread_enabled = get_bool("thread_enabled", bool(settings.THREAD_ENABLED))
        max_tweets = get_int("thread_max_tweets", int(settings.THREAD_MAX_TWEETS))
        numbering = get_bool("thread_numbering_enabled", bool(settings.THREAD_NUMBERING_ENABLED))

        devlog = materials.devlog.raw_snippet if materials.devlog else ""
        user_force = "THREAD: true" in devlog

        should_thread = thread_enabled and (user_force or len(topic_plan.key_points) >= 3)
        if not should_thread:
            return ThreadPlan(
                enabled=False, tweets_count=1, numbering_enabled=numbering, reason="single"
            )

        tweets_count = min(max_tweets, max(2, min(5, len(topic_plan.key_points))))

        prompt = f"""
You are planning an X thread.

Topic angles: {json.dumps(topic_plan.angles)}
Key points: {json.dumps(topic_plan.key_points)}
Style rules: openers={json.dumps(style.preferred_openers)}, forbidden={json.dumps(style.forbidden_phrases)}

Return JSON:
{{
  "enabled": true,
  "tweets_count": {tweets_count},
  "numbering_enabled": {str(numbering).lower()},
  "reason": "...",
  "tweet_key_points": [["..."],["..."]]
}}
"""
        try:
            resp = with_retry(
                lambda: self.client.chat.completions.create(
                    model=settings.OPENROUTER_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                ),
                max_attempts=3,
            )
            data = json.loads(resp.choices[0].message.content)
            return ThreadPlan(**data)
        except Exception:
            chunks: list[list[str]] = []
            points = topic_plan.key_points[:tweets_count]
            for i in range(tweets_count):
                chunk = [points[i]] if i < len(points) else []
                chunks.append(chunk)
            return ThreadPlan(
                enabled=True,
                tweets_count=tweets_count,
                numbering_enabled=numbering,
                reason="heuristic",
                tweet_key_points=chunks,
            )
