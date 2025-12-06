import os

class Settings:
    def __init__(self) -> None:
        self.DATABASE_URL = os.getenv("DATABASE_URL")
        self.WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
