import re

import yaml

from app.agents.base import BaseAgent
from app.config import settings
from app.models import (
    EditedDraft,
    EvidenceItem,
    EvidenceRef,
    Materials,
    PolicyCheckResult,
    PolicyReport,
    StyleProfile,
)


class PolicyAgent(BaseAgent):
    def __init__(self):
        super().__init__("PolicyAgent")

    def run(
        self,
        input_data: tuple[EditedDraft, Materials, list[str], StyleProfile],
    ) -> PolicyReport:
        edited, materials, recent_posts, style = input_data

        tweets = _edited_to_tweets(edited)
        blocked_terms = _load_blocked_terms(
            getattr(settings, "BLOCKED_TERMS_PATH", "./blocked_terms.yaml")
        )
        similarity_threshold = float(getattr(settings, "SIMILARITY_THRESHOLD", 0.6) or 0.6)

        checks: list[PolicyCheckResult] = []
        offending_spans: list[str] = []

        length_ok, length_details = _check_length(tweets)
        checks.append(
            PolicyCheckResult(check_name="length_ok", passed=length_ok, details=length_details)
        )

        sensitive_ok, sensitive_hits = _check_blocked_terms(tweets, blocked_terms)
        checks.append(
            PolicyCheckResult(
                check_name="sensitive_ok",
                passed=sensitive_ok,
                details="none" if sensitive_ok else ",".join(sensitive_hits[:10]),
            )
        )
        offending_spans.extend(sensitive_hits)

        similarity_ok, sim_details = _check_similarity(tweets, recent_posts, similarity_threshold)
        checks.append(
            PolicyCheckResult(check_name="similarity_ok", passed=similarity_ok, details=sim_details)
        )

        thread_marker_ok, thread_details = _check_thread_markers(edited, tweets)
        checks.append(
            PolicyCheckResult(
                check_name="thread_marker_ok",
                passed=thread_marker_ok,
                details=thread_details,
            )
        )

        tone_ok, tone_details = _check_tone(tweets, style)
        checks.append(PolicyCheckResult(check_name="tone_ok", passed=tone_ok, details=tone_details))

        claims = _extract_claims(tweets)
        evidence_map, unsupported = _map_evidence(claims, materials)
        fact_ok = len(unsupported) == 0
        checks.append(
            PolicyCheckResult(
                check_name="fact_grounded_ok",
                passed=fact_ok,
                details="all grounded" if fact_ok else f"unsupported={len(unsupported)}",
            )
        )

        if unsupported:
            offending_spans.extend(unsupported[:10])

        failures = [c for c in checks if not c.passed]
        if not failures:
            return PolicyReport(
                checks=checks,
                risk_level="LOW",
                action="PASS",
                claims=claims,
                evidence_map=evidence_map,
                unsupported_claims=[],
                offending_spans=[],
            )

        action, risk = _decide_action(failures)
        return PolicyReport(
            checks=checks,
            risk_level=risk,
            action=action,
            claims=claims,
            evidence_map=evidence_map,
            unsupported_claims=unsupported,
            offending_spans=offending_spans,
        )


def _edited_to_tweets(edited: EditedDraft) -> list[str]:
    if edited.mode == "thread" and edited.final_tweets:
        return [t.strip() for t in edited.final_tweets if t.strip()]
    if edited.final_text:
        return [edited.final_text.strip()]
    return []


def _check_length(tweets: list[str]) -> tuple[bool, str]:
    bad = [f"{i}:{len(t)}" for i, t in enumerate(tweets, start=1) if len(t) > 280]
    return len(bad) == 0, "ok" if not bad else "too_long=" + ";".join(bad)


def _load_blocked_terms(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        terms = data.get("blocked_terms", [])
        return [str(t).strip().lower() for t in terms if str(t).strip()]
    except Exception:
        return [w.strip().lower() for w in settings.sensitive_words_list]


def _check_blocked_terms(tweets: list[str], blocked_terms: list[str]) -> tuple[bool, list[str]]:
    hits: list[str] = []
    for t in tweets:
        low = t.lower()
        for term in blocked_terms:
            if term and term in low:
                hits.append(term)
    return len(hits) == 0, sorted(set(hits))


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_]+", text.lower())
    return {w for w in words if len(w) >= 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _check_similarity(
    tweets: list[str], recent_posts: list[str], threshold: float
) -> tuple[bool, str]:
    if not recent_posts:
        return True, "no_recent_posts"
    worst = 0.0
    for t in tweets:
        tset = _tokenize(t)
        for p in recent_posts:
            score = _jaccard(tset, _tokenize(p))
            worst = max(worst, score)
            if score >= threshold:
                return False, f"jaccard={score:.2f}>=threshold"
    return True, f"max_jaccard={worst:.2f}"


def _check_thread_markers(edited: EditedDraft, tweets: list[str]) -> tuple[bool, str]:
    if edited.mode == "thread":
        return True, "thread_allowed"
    markers = [t for t in tweets if "1/" in t or "/1" in t]
    return len(markers) == 0, "ok" if not markers else "thread_marker_in_single"


def _check_tone(tweets: list[str], style: StyleProfile) -> tuple[bool, str]:
    forbidden = {p.lower() for p in style.forbidden_phrases}
    marketing = ["game changer", "revolutionary", "explosive growth", "world changing"]
    forbidden |= set(marketing)
    if any("#" in t for t in tweets):
        return False, "hashtags_not_allowed"
    if any(_contains_emoji(t) for t in tweets):
        return False, "emoji_not_allowed"
    hits: list[str] = []
    for t in tweets:
        low = t.lower()
        for phrase in forbidden:
            if phrase and phrase in low:
                hits.append(phrase)
    if hits:
        return False, "forbidden_phrases=" + ",".join(sorted(set(hits))[:10])
    if any(_is_exaggerated(t) for t in tweets):
        return False, "exaggeration_detected"
    return True, "ok"


def _contains_emoji(text: str) -> bool:
    return bool(re.search(r"[\U0001F300-\U0001FAFF]", text))


def _is_exaggerated(text: str) -> bool:
    low = text.lower()
    patterns = ["insane", "unbelievable", "guarantee", "always", "never", "massive"]
    return any(p in low for p in patterns)


def _extract_claims(tweets: list[str]) -> list[str]:
    claims: list[str] = []
    for t in tweets:
        parts = re.split(r"[\n\.!?]", t)
        for p in parts:
            s = p.strip()
            if not s:
                continue
            if _looks_like_opinion(s):
                continue
            if len(_tokenize(s)) < 4:
                continue
            claims.append(s)
    return claims[:20]


def _looks_like_opinion(sentence: str) -> bool:
    low = sentence.lower()
    markers = ["i think", "i feel", "my take", "opinion", "i learned", "lesson"]
    return any(m in low for m in markers)


def _materials_evidence(materials: Materials) -> list[EvidenceItem]:
    ev: list[EvidenceItem] = []
    ev.extend(materials.git_commits)
    if materials.devlog:
        ev.append(materials.devlog)
    ev.extend(materials.notes)
    ev.extend(materials.links)
    return ev


def _map_evidence(
    claims: list[str], materials: Materials
) -> tuple[dict[str, list[EvidenceRef]], list[str]]:
    evidence_items = _materials_evidence(materials)
    evidence_map: dict[str, list[EvidenceRef]] = {}
    unsupported: list[str] = []
    for claim in claims:
        cset = _tokenize(claim)
        scored: list[tuple[float, EvidenceItem]] = []
        for item in evidence_items:
            eset = _tokenize(item.raw_snippet)
            score = _jaccard(cset, eset)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [s for s in scored[:2] if s[0] >= 0.2]
        if not top:
            unsupported.append(claim)
            continue
        refs: list[EvidenceRef] = []
        for _, item in top:
            refs.append(
                EvidenceRef(
                    source_name=item.source_name,
                    source_id=item.source_id,
                    quote=item.raw_snippet[:180],
                )
            )
        evidence_map[claim] = refs
    return evidence_map, unsupported


def _decide_action(failures: list[PolicyCheckResult]) -> tuple[str, str]:
    names = {f.check_name for f in failures}
    if "sensitive_ok" in names:
        return "HOLD", "HIGH"
    if "fact_grounded_ok" in names:
        return "REWRITE", "HIGH"
    if "length_ok" in names or "similarity_ok" in names or "tone_ok" in names:
        return "REWRITE", "MEDIUM"
    return "HOLD", "HIGH"
