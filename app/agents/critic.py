import json

from openai import OpenAI

from app.agents.base import BaseAgent
from app.config import settings
from app.models import DraftCandidate, DraftCandidates, EditedDraft, Materials, StyleProfile, ThreadPlan
from app.services.retry import with_retry

class CriticAgent(BaseAgent):
    def __init__(self):
        super().__init__("CriticAgent")
        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    def run(self, input_data: tuple[DraftCandidates, Materials, StyleProfile, ThreadPlan]) -> EditedDraft:
        candidates, materials, style, thread_plan = input_data

        prompt = f"""
You are a senior editor.

Candidates JSON:
{candidates.model_dump_json()}

Context summary:
- git commits: {len(materials.git_commits)}
- notes: {len(materials.notes)}
- links: {len(materials.links)}
- thread_enabled: {thread_plan.enabled}
- numbering_enabled: {thread_plan.numbering_enabled}

Personal style:
- forbidden_phrases: {json.dumps(style.forbidden_phrases)}
- tone_rules: {json.dumps(style.tone_rules)}

Task:
- Pick the best candidate.
- Edit to reduce fluff, improve first sentence, and keep it grounded.
- If thread: ensure consistent flow across tweets.
- Strict char limit: each final tweet <= 280.

Return JSON only:
{{
  "mode": "single"|"thread",
  "selected_candidate_index": 0,
  "original": {{...}},
  "final_text": "...",  
  "final_tweets": ["..."],
  "numbering_added": false,
  "edit_notes": "..."
}}
"""

        resp = with_retry(
            lambda: self.client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            ),
            max_attempts=3,
        )
        data = json.loads(resp.choices[0].message.content)
        edited = EditedDraft(**data)

        if edited.mode == "thread" and edited.final_tweets and thread_plan.numbering_enabled:
            numbered = _add_numbering(edited.final_tweets)
            edited.final_tweets = numbered
            edited.numbering_added = True
        return edited


def _add_numbering(tweets: list[str]) -> list[str]:
    n = len(tweets)
    out: list[str] = []
    for i, t in enumerate(tweets, start=1):
        suffix = f" ({i}/{n})"
        text = t.strip()
        if len(text) + len(suffix) <= 280:
            out.append(text + suffix)
        else:
            out.append(text[: max(0, 280 - len(suffix))].rstrip() + suffix)
    return out
