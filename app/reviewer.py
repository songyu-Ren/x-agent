import logging
from typing import List, Tuple
from app.config import settings
from app.storage import get_recent_posted_drafts

logger = logging.getLogger(__name__)

def jaccard_similarity(str1: str, str2: str) -> float:
    set1 = set(str1.lower().split())
    set2 = set(str2.lower().split())
    if not set1 and not set2:
        return 0.0
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return len(intersection) / len(union)

def check_sensitive_info(text: str) -> List[str]:
    """Return list of detected sensitive words."""
    detected = []
    text_lower = text.lower()
    for word in settings.sensitive_words_list:
        if word.lower() in text_lower:
            detected.append(word)
    return detected

def review_draft(text: str) -> Tuple[bool, List[str]]:
    """
    Review the draft against rules.
    Returns (passed: bool, reasons: List[str])
    """
    reasons = []
    passed = True

    # 1. Length check
    if len(text) > 280:
        passed = False
        reasons.append(f"Length {len(text)} > 280")

    # 2. Sensitive info
    sensitive = check_sensitive_info(text)
    if sensitive:
        passed = False
        reasons.append(f"Contains sensitive words: {', '.join(sensitive)}")

    # 3. Thread marker check
    if "1/" in text or "/1" in text: # Simple heuristic
        # We don't want strict fail maybe? The prompt says "Avoid thread markers".
        # Let's flag it.
        passed = False
        reasons.append("Contains thread markers (1/, /1)")

    # 4. Similarity check
    recent_posts = get_recent_posted_drafts(days=14)
    for post in recent_posts:
        sim = jaccard_similarity(text, post)
        if sim > 0.6: # Configurable threshold
            passed = False
            reasons.append(f"Too similar to recent post (Jaccard {sim:.2f})")
            break

    return passed, reasons
