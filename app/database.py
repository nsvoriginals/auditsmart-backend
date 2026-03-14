import motor.motor_asyncio
from app.config import settings

client = None
db = None

async def connect_db():
    global client, db
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]
    print(f"✓ MongoDB connected: {settings.DB_NAME}")

async def disconnect_db():
    if client:
        client.close()
        print("MongoDB disconnected")

def get_db():
    return db
