import json

from openai import OpenAI

from app.agents.base import BaseAgent
from app.config import settings
from app.models import Materials, TopicPlan
from app.services.retry import with_retry


class CuratorAgent(BaseAgent):
    def __init__(self):
        super().__init__("CuratorAgent")
        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    def run(self, input_data: tuple[Materials, list[str]]) -> TopicPlan:
        materials, recent_posts = input_data

        git_subjects = [c.raw_snippet for c in materials.git_commits][:50]
        devlog_text = materials.devlog.raw_snippet if materials.devlog else ""
        notes = [n.raw_snippet for n in materials.notes][:20]
        links = [
            f"{link_item.title or ''} {link_item.url or ''}".strip()
            for link_item in materials.links
        ][:20]

        prompt = f"""
You are a content strategist for a developer building in public.

Materials (last 24h):
- Git commit subjects: {json.dumps(git_subjects)}
- Devlog excerpt: {devlog_text[:2000]}
- Notes: {json.dumps(notes)}
- Links: {json.dumps(links)}

Recent approved/posted texts (avoid repeating):
{json.dumps(recent_posts[:50])}

Task:
- Choose a topic plan for today.
- If materials are empty, choose a reflection/lesson and clearly label it as an opinion.
- Produce 2-3 possible angles.

Output JSON only:
{{
  "topic_bucket": 1,
  "angles": ["...", "..."],
  "key_points": ["...", "..."],
  "evidence_map": {{
    "<key_point>": [{{"source_name":"git|devlog|github|rss|notion","source_id":"...","quote":"..."}}]
  }}
}}
"""

        try:
            response = with_retry(
                lambda: self.client.chat.completions.create(
                    model=settings.OPENROUTER_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                ),
                max_attempts=3,
            )
            data = json.loads(response.choices[0].message.content)
            return TopicPlan(**data)
        except Exception:
            return TopicPlan(
                topic_bucket=3,
                angles=["A small reflection from today"],
                key_points=["A small, honest reflection is better than a vague claim"],
                evidence_map={},
            )
