import sqlite3
import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)

DB_PATH = "daily_agent.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            token TEXT PRIMARY KEY,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            status TEXT NOT NULL,
            materials_json TEXT,
            candidates_json TEXT,
            final_text TEXT,
            tweet_id TEXT,
            last_error TEXT,
            source TEXT DEFAULT 'scheduler'
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def create_draft(
    materials: Dict[str, Any],
    candidates: List[str],
    final_text: str,
    source: str = "scheduler",
    expiration_hours: int = 36
) -> str:
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expiration_hours)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO drafts (
            token, created_at, expires_at, status, 
            materials_json, candidates_json, final_text, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token,
            now.isoformat(),
            expires_at.isoformat(),
            "pending",
            json.dumps(materials),
            json.dumps(candidates),
            final_text,
            source
        )
    )
    conn.commit()
    conn.close()
    return token

def get_draft(token: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM drafts WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def update_draft_status(token: str, status: str, tweet_id: Optional[str] = None, error: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    updates = ["status = ?"]
    params = [status]
    
    if tweet_id is not None:
        updates.append("tweet_id = ?")
        params.append(tweet_id)
    
    if error is not None:
        updates.append("last_error = ?")
        params.append(error)
        
    params.append(token)
    
    sql = f"UPDATE drafts SET {', '.join(updates)} WHERE token = ?"
    cursor.execute(sql, tuple(params))
    conn.commit()
    conn.close()

def update_draft_text(token: str, text: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE drafts SET final_text = ? WHERE token = ?", (text, token))
    conn.commit()
    conn.close()

def get_recent_posted_drafts(days: int = 14) -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    # Also include dry_run_posted for similarity checks if desired, 
    # but strictly "posted" implies public. Let's include both to be safe against repeating dry runs too?
    # User said "avoid repetition with past 14 days posted content".
    cursor.execute(
        """
        SELECT final_text FROM drafts 
        WHERE status IN ('posted', 'dry_run_posted') 
        AND created_at > ?
        """, 
        (cutoff,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [row['final_text'] for row in rows if row['final_text']]

def get_recent_drafts(limit: int = 7) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM drafts ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
