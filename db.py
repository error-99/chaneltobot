import logging
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from config import MONGO_URI, MONGO_DB

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]

users_col  = db["users"]
videos_col = db["videos"]

COUNTER_ID = "__counter"


def init_db():
    videos_col.update_one(
        {"_id": COUNTER_ID},
        {"$setOnInsert": {"video_seq": 0, "user_seq": 0}},
        upsert=True,
    )
    users_col.create_index([("id", ASCENDING)], unique=True, sparse=True)
    users_col.create_index([("last_active", DESCENDING)])
    videos_col.create_index([("id", ASCENDING)], unique=True, sparse=True)
    videos_col.create_index(
        [("message_id", ASCENDING), ("channel_id", ASCENDING)],
        unique=True, sparse=True,
    )
    videos_col.create_index([("created_at", ASCENDING), ("id", ASCENDING)])
    logging.info("DB initialized")


def next_seq(field: str) -> int:
    doc = videos_col.find_one_and_update(
        {"_id": COUNTER_ID},
        {"$inc": {field: 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc[field])