from app.storage import create_draft, get_draft, update_draft_status, update_draft_text

def test_create_and_get_draft(clean_db):
    token = create_draft({"git": "log"}, ["cand1", "cand2"], "final_text")
    draft = get_draft(token)
    assert draft is not None
    assert draft['final_text'] == "final_text"
    assert draft['status'] == "pending"

def test_update_status(clean_db):
    token = create_draft({}, [], "text")
    update_draft_status(token, "posted", tweet_id="123")
    draft = get_draft(token)
    assert draft['status'] == "posted"
    assert draft['tweet_id'] == "123"

def test_update_text(clean_db):
    token = create_draft({}, [], "old")
    update_draft_text(token, "new")
    draft = get_draft(token)
    assert draft['final_text'] == "new"
