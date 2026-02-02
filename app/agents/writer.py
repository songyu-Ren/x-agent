import json
from openai import OpenAI

from app.agents.base import BaseAgent
from app.config import settings
from app.models import DraftCandidate, DraftCandidates, Materials, StyleProfile, ThreadPlan, TopicPlan
from app.services.retry import with_retry

class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__("WriterAgent")
        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    def run(self, input_data: tuple[TopicPlan, ThreadPlan, StyleProfile, Materials]) -> DraftCandidates:
        topic_plan, thread_plan, style, materials = input_data

        git_subjects = [c.raw_snippet for c in materials.git_commits][:50]
        devlog_text = materials.devlog.raw_snippet if materials.devlog else ""
        notes = [n.raw_snippet for n in materials.notes][:20]
        links = [f"{l.title or ''} {l.url or ''}".strip() for l in materials.links][:20]

        if not thread_plan.enabled:
            prompt = f"""
You are a ghostwriter for a senior full-stack engineer building in public.

Materials (facts only):
- git subjects: {json.dumps(git_subjects)}
- devlog: {devlog_text[:2000]}
- notes: {json.dumps(notes)}
- links: {json.dumps(links)}

Topic angles: {json.dumps(topic_plan.angles)}
Key points: {json.dumps(topic_plan.key_points)}

Personal style:
- preferred_openers: {json.dumps(style.preferred_openers)}
- forbidden_phrases: {json.dumps(style.forbidden_phrases)}
- sentence_length_preference: {style.sentence_length_preference}
- tone_rules: {json.dumps(style.tone_rules)}
- formatting_rules: {json.dumps(style.formatting_rules)}

Hard rules:
- No emojis. No hashtags. No marketing tone.
- Do not invent facts. If materials are empty, produce a reflection and clearly label it as opinion.
- Each candidate must be <= 260 characters.

Return JSON only:
{{"candidates": [{{"mode":"single","text":"..."}},{{"mode":"single","text":"..."}},{{"mode":"single","text":"..."}}]}}
"""
        else:
            prompt = f"""
You are a ghostwriter for an X thread (2-5 tweets).

Materials (facts only):
- git subjects: {json.dumps(git_subjects)}
- devlog: {devlog_text[:2000]}
- notes: {json.dumps(notes)}
- links: {json.dumps(links)}

Thread plan: tweets_count={thread_plan.tweets_count}; tweet_key_points={json.dumps(thread_plan.tweet_key_points)}
Personal style:
- preferred_openers: {json.dumps(style.preferred_openers)}
- forbidden_phrases: {json.dumps(style.forbidden_phrases)}

Hard rules:
- No emojis. No hashtags. No marketing tone.
- Do not invent facts. If materials are empty, produce opinions and label them as opinion.
- Produce 3 candidate threads; each thread is a list of {thread_plan.tweets_count} tweets.
- Each tweet must be <= 270 characters (leaving space for numbering if enabled).

Return JSON only:
{{"candidates": [
  {{"mode":"thread","tweets":["...","..."]}},
  {{"mode":"thread","tweets":["...","..."]}},
  {{"mode":"thread","tweets":["...","..."]}}
]}}
"""

        response = with_retry(
            lambda: self.client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            ),
            max_attempts=3,
        )
        data = json.loads(response.choices[0].message.content)
        return DraftCandidates(**data)
