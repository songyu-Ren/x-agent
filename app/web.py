import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings
from app.storage import get_draft, update_draft_status, update_draft_text, get_recent_drafts
from app.reviewer import review_draft
from app.twitter_client import post_tweet
from app.scheduler import run_daily_cycle

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    if not settings.BASIC_AUTH_USER or not settings.BASIC_AUTH_PASS:
        return "anonymous"
    
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = settings.BASIC_AUTH_USER.encode("utf8")
    is_correct_username = secrets.compare_digest(current_username_bytes, correct_username_bytes)
    
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = settings.BASIC_AUTH_PASS.encode("utf8")
    is_correct_password = secrets.compare_digest(current_password_bytes, correct_password_bytes)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

def auth_wrapper(func):
    """Dependency wrapper for optional auth."""
    if settings.BASIC_AUTH_USER and settings.BASIC_AUTH_PASS:
        return Depends(get_current_username)
    return lambda: None

def render_html(title: str, content: str, error: str = "") -> str:
    error_html = f'<div style="color:red; background:#ffe6e6; padding:10px; margin-bottom:10px;">{error}</div>' if error else ""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title} - Daily X Agent</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 20px; max_width: 600px; margin: 0 auto; }}
            button {{ padding: 10px 20px; font-size: 16px; cursor: pointer; }}
            textarea {{ width: 100%; height: 150px; font-size: 16px; padding: 10px; margin-bottom: 10px; }}
            .status {{ padding: 10px; margin-bottom: 20px; border-radius: 5px; }}
            .pending {{ background-color: #e6f7ff; }}
            .posted {{ background-color: #d4edda; color: #155724; }}
            .error {{ background-color: #f8d7da; color: #721c24; }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        {error_html}
        {content}
    </body>
    </html>
    """

@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.get("/approve/{token}", response_class=HTMLResponse, dependencies=[auth_wrapper(get_current_username)])
def approve_draft(token: str):
    draft = get_draft(token)
    if not draft:
        return render_html("Error", "Draft not found.", error="Invalid Token")
    
    if draft['status'] in ['posted', 'skipped', 'dry_run_posted']:
        return render_html("Info", f"Draft already processed. Status: <strong>{draft['status']}</strong>")
    
    # Re-review
    passed, reasons = review_draft(draft['final_text'])
    if not passed:
        return render_html(
            "Security Check Failed", 
            f"<p>Cannot approve. Issues found:</p><ul><li>{'</li><li>'.join(reasons)}</li></ul>"
            f"<p><a href='/edit/{token}'>Go to Edit</a></p>"
        )

    try:
        tweet_id = post_tweet(draft['final_text'])
        new_status = "dry_run_posted" if settings.DRY_RUN else "posted"
        update_draft_status(token, new_status, tweet_id=tweet_id)
        
        msg = f"Tweet posted successfully! ID: {tweet_id}"
        if settings.DRY_RUN:
            msg = f"[DRY RUN] Status updated. Tweet ID: {tweet_id} (Fake)"
            
        return render_html("Success", f"<p>{msg}</p>")
    except Exception as e:
        update_draft_status(token, "error", error=str(e))
        return render_html("Error", f"Failed to post tweet.", error=str(e))

@router.get("/edit/{token}", response_class=HTMLResponse, dependencies=[auth_wrapper(get_current_username)])
def edit_draft_page(token: str):
    draft = get_draft(token)
    if not draft:
        return render_html("Error", "Draft not found.")
    
    passed, reasons = review_draft(draft['final_text'])
    review_html = ""
    if not passed:
        review_html = f'<div style="color:orange">⚠️ Issues: {", ".join(reasons)}</div>'
    else:
        review_html = '<div style="color:green">✅ Review passed</div>'

    form = f"""
    <div class="status {draft['status']}">Status: {draft['status']}</div>
    {review_html}
    <form method="post">
        <textarea name="text">{draft['final_text']}</textarea>
        <br>
        <button type="submit">Save & Check</button>
        <a href="/approve/{token}" style="margin-left:20px">Approve (if passed)</a>
    </form>
    """
    return render_html("Edit Draft", form)

@router.post("/edit/{token}", response_class=HTMLResponse, dependencies=[auth_wrapper(get_current_username)])
def edit_draft_save(token: str, text: str = Form(...)):
    draft = get_draft(token)
    if not draft:
        return render_html("Error", "Draft not found.")
    
    update_draft_text(token, text)
    
    passed, reasons = review_draft(text)
    msg = "Draft updated."
    if passed:
        msg += " ✅ Review passed. You can now Approve."
    else:
        msg += f" ⚠️ Review failed: {', '.join(reasons)}"
        
    return render_html("Edit Draft", f"""
        <p>{msg}</p>
        <p><a href="/edit/{token}">Back to Edit</a> | <a href="/approve/{token}">Try Approve</a></p>
    """)

@router.get("/skip/{token}", response_class=HTMLResponse, dependencies=[auth_wrapper(get_current_username)])
def skip_draft(token: str):
    draft = get_draft(token)
    if not draft:
        return render_html("Error", "Draft not found.")
        
    update_draft_status(token, "skipped")
    return render_html("Skipped", "<p>Draft marked as skipped.</p>")

@router.post("/generate-now", dependencies=[auth_wrapper(get_current_username)])
async def generate_now(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_daily_cycle, source="manual")
    return {"message": "Generation triggered in background."}

@router.get("/drafts", response_class=HTMLResponse, dependencies=[auth_wrapper(get_current_username)])
def list_drafts():
    drafts = get_recent_drafts(limit=7)
    items = []
    for d in drafts:
        link = f"/edit/{d['token']}"
        items.append(f"""
            <li style="margin-bottom:10px; border-bottom:1px solid #eee; padding-bottom:5px;">
                <strong>{d['created_at'][:16]}</strong> [{d['status']}]<br>
                {d['final_text'][:50]}... <a href="{link}">View</a>
            </li>
        """)
    
    content = f"<ul>{''.join(items)}</ul>"
    return render_html("Recent Drafts", content)
