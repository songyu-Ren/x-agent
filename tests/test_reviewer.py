from app.reviewer import review_draft, jaccard_similarity
from app.config import settings

def test_jaccard_similarity():
    s1 = "hello world"
    s2 = "hello world"
    assert jaccard_similarity(s1, s2) == 1.0
    
    s3 = "hello python"
    assert jaccard_similarity(s1, s3) == 0.3333333333333333 # intersection 1 (hello), union 3 (hello, world, python)

def test_review_length():
    short_text = "a" * 280
    passed, _ = review_draft(short_text)
    assert passed
    
    long_text = "a" * 281
    passed, reasons = review_draft(long_text)
    assert not passed
    assert "Length" in reasons[0]

def test_review_sensitive():
    # Mock settings
    settings.SENSITIVE_WORDS = "secret"
    
    text = "This is a secret key"
    passed, reasons = review_draft(text)
    assert not passed
    assert "sensitive" in reasons[0]

def test_review_thread():
    text = "This is a thread 1/5"
    passed, reasons = review_draft(text)
    assert not passed
    assert "thread markers" in reasons[0]
