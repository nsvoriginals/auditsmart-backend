import motor.motor_asyncio
from app.config import settings

client = None
db = None


async def connect_db():
    global client, db
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.MONGODB_URL)
        db = client[settings.DB_NAME]
        # Test connection
        await client.admin.command('ping')
        print(f"✅ MongoDB connected: {settings.DB_NAME}")
        
        # Ensure indexes for performance
        await db.users.create_index("email", unique=True)
        await db.audits.create_index([("user_id", 1), ("created_at", -1)])
        print("✅ MongoDB indexes ensured")
    except Exception as e:
        print(f"❌ MongoDB connection FAILED: {e}")
        raise


async def disconnect_db():
    if client:
        client.close()
        print("MongoDB disconnected")


def get_db():
    return db
