from sqlalchemy import Column, String, Text, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    message_id = Column(String, primary_key=True)
    from_msisdn = Column(String, nullable=False)
    to_msisdn = Column(String, nullable=False)
    ts = Column(String, nullable=False)         # ISO-8601 UTC string
    text = Column(Text, nullable=True)
    created_at = Column(String, nullable=False) # server time ISO-8601

def get_engine(database_url: str):
    # echo=True is just for visibility; you can turn it off later
    return create_engine(database_url, echo=True, future=True)

def init_db(engine):
    # This should create app.db and the messages table if they don't exist
    Base.metadata.create_all(bind=engine)
