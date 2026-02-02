import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.migrations.runner import run_migrations
from app.scheduler import start_scheduler
from app.web import router

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Daily X Agent...")
    run_migrations()
    start_scheduler()
    yield
    # Shutdown
    logger.info("Shutting down Daily X Agent...")

app = FastAPI(
    title="Daily X Agent",
    lifespan=lifespan
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
