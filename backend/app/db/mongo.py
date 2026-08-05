from typing import Any, Final

from beanie import init_beanie  # pyright: ignore[reportMissingImports]
from beanie.exceptions import CollectionWasNotInitialized
from motor.motor_asyncio import AsyncIOMotorClient  # pyright: ignore[reportMissingImports]

from app.core.config import settings
from app.core.logger import get_logger
from app.models import DOCUMENT_MODELS
from app.models.company import Company

logger = get_logger(__name__)

client: AsyncIOMotorClient[dict[str, Any]] | None = None
_initialized: bool = False
REGISTERED_MODEL_NAMES: Final[list[str]] = ["Company", "Contact", "EmailDraft", "ScraperJob"]


def is_beanie_initialized() -> bool:
    """Return True when Beanie document models are already bound to a database."""
    try:
        Company.get_motor_collection()
        return True
    except CollectionWasNotInitialized:
        return False
    except Exception:
        return False


def is_mongo_ready() -> bool:
    """Return True when Mongo/Beanie is ready for repository operations."""
    return _initialized or is_beanie_initialized()


async def connect_to_mongo() -> None:
    """Connect to MongoDB and initialize Beanie. Idempotent."""
    global client, _initialized

    if is_beanie_initialized():
        _initialized = True
        logger.debug("Beanie already initialized; skipping connect_to_mongo")
        return

    if _initialized and client is not None:
        logger.debug("MongoDB client already connected; skipping connect_to_mongo")
        return

    logger.info("Connecting to MongoDB...")
    try:
        client = AsyncIOMotorClient(settings.mongodb_uri)
        await client.admin.command("ping")
    except Exception:
        logger.exception("MongoDB connection failed")
        client = None
        _initialized = False
        raise

    logger.info("Connected to MongoDB")
    logger.info("Initializing Beanie ODM...")
    try:
        await init_beanie(
            database=client[settings.mongodb_db_name],
            document_models=DOCUMENT_MODELS,
        )
    except Exception:
        logger.exception("Beanie initialization failed")
        _initialized = False
        raise

    _initialized = True
    logger.info("Beanie initialized successfully")
    logger.info("Registered document models")
    for model_name in REGISTERED_MODEL_NAMES:
        logger.info("%s", model_name)
    logger.info("Backend startup complete")


async def ensure_mongo_ready() -> None:
    """Idempotent bootstrap for FastAPI, CLI scripts, cron jobs, and tests.

    Reuses :func:`connect_to_mongo` and never re-runs ``init_beanie`` when Beanie
    is already initialized (including mongomock-based tests).
    """
    if is_mongo_ready():
        logger.debug("ensure_mongo_ready: database already initialized")
        return
    await connect_to_mongo()


async def close_mongo_connection() -> None:
    global client, _initialized
    if client is not None:
        client.close()
        client = None
    _initialized = False


async def ping_mongodb() -> bool:
    if client is None:
        return False
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        logger.exception("MongoDB ping failed")
        return False
