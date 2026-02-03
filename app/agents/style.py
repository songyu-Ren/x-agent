import json

from openai import OpenAI

from app.agents.base import BaseAgent
from app.config import settings
from app.models import StyleProfile
from app.services.retry import with_retry


class StyleAgent(BaseAgent):
    def __init__(self):
        super().__init__("StyleAgent")
        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    def run(self, input_data: tuple[list[str], str]) -> StyleProfile:
        posts, devlog_excerpt = input_data
        prompt = f"""
You are learning a writer's personal style.

Inputs:
- Approved/posted tweets (most recent first): {json.dumps(posts[:50])}
- Devlog excerpt (may be empty): {devlog_excerpt[:2000]}

Output a JSON style profile:
{{
  "preferred_openers": ["..."],
  "forbidden_phrases": ["..."],
  "sentence_length_preference": "short"|"medium",
  "tone_rules": ["..."],
  "formatting_rules": ["...", "optional: multiline"]
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
            return StyleProfile(**data)
        except Exception:
            return StyleProfile(
                preferred_openers=["Today:", "One thing I learned:", "Quick note:"],
                forbidden_phrases=["game changer", "revolutionary"],
                sentence_length_preference="short",
                tone_rules=["No marketing", "Prefer concrete trade-offs", "Avoid exaggeration"],
                formatting_rules=["Prefer 1-2 short lines"],
            )
