import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.collector import collect_materials
from app.llm import generate_candidates, rewrite_draft
from app.reviewer import review_draft
from app.storage import create_draft, update_draft_status
from app.notifier import notify_user

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def run_daily_cycle(source: str = "scheduler"):
    logger.info(f"Starting daily cycle from {source}...")
    
    # 1. Collect
    materials = collect_materials()
    logger.info("Materials collected.")

    # 2. Generate
    candidates = generate_candidates(materials)
    logger.info(f"Generated {len(candidates)} candidates.")

    if not candidates:
        logger.error("No candidates generated.")
        return

    # 3. Review & Select
    final_text = candidates[0] # Default to first
    is_attention_needed = False
    
    # Try to find a passing candidate
    found_passing = False
    for cand in candidates:
        passed, reasons = review_draft(cand)
        if passed:
            final_text = cand
            found_passing = True
            break
        else:
            logger.info(f"Candidate rejected: {cand} Reasons: {reasons}")
    
    # If none passed, try rewrite the first one once
    if not found_passing:
        logger.info("No candidates passed. Attempting rewrite of first candidate...")
        passed, reasons = review_draft(candidates[0]) # Get reasons again
        final_text = rewrite_draft(candidates[0], "; ".join(reasons))
        
        # Check again
        passed, reasons = review_draft(final_text)
        if not passed:
            logger.warning(f"Rewrite still failed: {reasons}. Marking for human attention.")
            is_attention_needed = True

    # 4. Store
    token = create_draft(
        materials=materials,
        candidates=candidates,
        final_text=final_text,
        source=source
    )
    
    if is_attention_needed:
        update_draft_status(token, "needs_human_attention")

    logger.info(f"Draft created: {token}")

    # 5. Notify
    notify_user(token, final_text, is_attention_needed)
    logger.info("User notified.")

def start_scheduler():
    trigger = CronTrigger(
        hour=settings.SCHEDULE_HOUR,
        minute=settings.SCHEDULE_MINUTE,
        timezone=settings.TIMEZONE
    )
    scheduler.add_job(run_daily_cycle, trigger)
    scheduler.start()
    logger.info(f"Scheduler started. Next run at {settings.SCHEDULE_HOUR}:{settings.SCHEDULE_MINUTE} {settings.TIMEZONE}")
