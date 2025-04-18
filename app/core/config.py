# app/core/config.py

import os
from databases import Database
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

database = Database(DATABASE_URL)

async def load_config():
    # Extend as needed to pull dynamic settings or tenant config
    pass
