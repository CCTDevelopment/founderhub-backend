from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core import Base
from sqlalchemy.ext.declarative import declarative_base

import os
from dotenv import load_dotenv
load_dotenv()
Base = declarative_base()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set!")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
