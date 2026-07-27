from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


client: AsyncIOMotorClient | None = None


async def connect_to_mongo() -> None:
    global client
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await client.admin.command("ping")


async def close_mongo_connection() -> None:
    global client
    if client is not None:
        client.close()
        client = None
