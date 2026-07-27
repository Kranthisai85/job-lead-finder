from typing import Any, Final

from beanie import init_beanie  # pyright: ignore[reportMissingImports]
from motor.motor_asyncio import AsyncIOMotorClient  # pyright: ignore[reportMissingImports]

from app.core.config import settings
from app.core.logger import get_logger
from app.models import DOCUMENT_MODELS

logger = get_logger(__name__)

client: AsyncIOMotorClient[dict[str, Any]] | None = None
REGISTERED_MODEL_NAMES: Final[list[str]] = ["Company", "Contact", "EmailDraft", "ScraperJob"]


async def connect_to_mongo() -> None:
    global client
    logger.info("Connecting to MongoDB...")
    try:
        client = AsyncIOMotorClient(settings.mongodb_uri)
        await client.admin.command("ping")
    except Exception:
        logger.exception("MongoDB connection failed")
        client = None
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
        raise

    logger.info("Beanie initialized successfully")
    logger.info("Registered document models")
    for model_name in REGISTERED_MODEL_NAMES:
        logger.info("%s", model_name)
    logger.info("Backend startup complete")


async def close_mongo_connection() -> None:
    global client
    if client is not None:
        client.close()
        client = None


async def ping_mongodb() -> bool:
    if client is None:
        return False
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        logger.exception("MongoDB ping failed")
        return False
