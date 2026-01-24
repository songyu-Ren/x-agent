import logging
import json
from typing import List, Dict, Any
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url=settings.OPENROUTER_BASE_URL,
    api_key=settings.OPENROUTER_API_KEY,
)

SYSTEM_PROMPT = """
You are a Daily X (Twitter) Agent for a senior full-stack engineer who builds in public.
Your goal is to generate 3 distinct tweet drafts based on the provided daily materials (git logs, devlogs).

Style Guidelines:
- "Build-in-public" tone: authentic, technical but accessible, sharing progress/lessons.
- NO marketing speak ("game changer", "revolutionary").
- NO emojis.
- NO hashtags.
- NO fabrication: strictly based on provided materials.
- If materials are empty, generate a generic "Reflection/Lesson" tweet based on general software engineering wisdom, but clearly label it as a thought/opinion.
- Length: Each draft must be under 260 characters (leaving room for edits).

Output Format:
Return ONLY a JSON array of strings. Example:
["Draft 1 text...", "Draft 2 text...", "Draft 3 text..."]
"""

def generate_candidates(materials: Dict[str, Any]) -> List[str]:
    """Generate 3 candidate tweets."""
    prompt = f"""
    Materials:
    Git Logs (Last 24h):
    {materials.get('git_logs', '(None)')}

    Devlog (Snippet):
    {materials.get('devlog', '(None)')}

    Generate 3 drafts.
    """

    try:
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        
        candidates = json.loads(content)
        if isinstance(candidates, list):
            return candidates[:3]
        return []
    except Exception as e:
        logger.error(f"LLM Generation failed: {e}")
        return ["Error generating drafts. Please check logs."]

def rewrite_draft(draft: str, feedback: str) -> str:
    """Rewrite a draft based on reviewer feedback."""
    prompt = f"""
    Original Draft: "{draft}"
    Critique: {feedback}
    
    Please rewrite this tweet to fix the issues. Keep it under 280 chars. No emojis/hashtags.
    Return ONLY the raw text of the new draft.
    """
    
    try:
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful editor. Rewrite the tweet to satisfy the critique."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM Rewrite failed: {e}")
        return draft  # Return original if fail
