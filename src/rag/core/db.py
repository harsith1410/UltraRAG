import os

import sqlalchemy
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = sqlalchemy.create_engine(DATABASE_URL)

sessionLocal = sessionmaker(bind=engine)
Base = declarative_base()