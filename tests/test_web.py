from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.storage import create_draft

client = TestClient(app)
auth = ("admin", "secret")

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@patch("app.web.review_draft")
@patch("app.web.post_tweet")
def test_approve_flow(mock_post, mock_review, clean_db):
    # Setup
    mock_review.return_value = (True, [])
    mock_post.return_value = "tweet_123"
    
    token = create_draft({}, [], "valid text")
    
    # Act
    response = client.get(f"/approve/{token}", auth=auth)
    
    # Assert
    assert response.status_code == 200
    assert "Success" in response.text
    assert "tweet_123" in response.text
    
    # Verify DB
    from app.storage import get_draft
    draft = get_draft(token)
    # Status depends on DRY_RUN in env, default is True -> dry_run_posted
    assert "posted" in draft['status'] 

def test_edit_flow(clean_db):
    token = create_draft({}, [], "original")
    
    # Get edit page
    response = client.get(f"/edit/{token}", auth=auth)
    assert response.status_code == 200
    assert "original" in response.text
    
    # Post edit
    response = client.post(f"/edit/{token}", data={"text": "updated"}, auth=auth)
    assert response.status_code == 200
    assert "updated" in response.text
    
    from app.storage import get_draft
    draft = get_draft(token)
    assert draft['final_text'] == "updated"
