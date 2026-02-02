import json
from datetime import datetime

from openai import OpenAI

from app.agents.base import BaseAgent
from app.config import settings
from app.models import WeeklyReport
from app.services.retry import with_retry


class WeeklyAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__("WeeklyAnalystAgent")
        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    def run(self, input_data: tuple[datetime, datetime, list[str]]) -> WeeklyReport:
        week_start, week_end, posts = input_data
        prompt = f"""
You are an analyst for weekly content performance.

Week window: {week_start.isoformat()} to {week_end.isoformat()}
Posted texts: {json.dumps(posts[:100])}

Generate a weekly report JSON:
{{
  "week_start": "{week_start.isoformat()}",
  "week_end": "{week_end.isoformat()}",
  "top_topic_buckets": ["..."],
  "recommendations": ["..."],
  "next_week_topics": ["...", "...", "..."]
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
            data["week_start"] = week_start
            data["week_end"] = week_end
            return WeeklyReport(**data)
        except Exception:
            return WeeklyReport(
                week_start=week_start,
                week_end=week_end,
                top_topic_buckets=["Engineering"],
                recommendations=["Ship smaller updates more consistently."],
                next_week_topics=["A trade-off I made", "A debugging lesson", "A small refactor"],
            )
