import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LINE Messaging API
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")

    # Azure Document Intelligence
    AZURE_DOC_INTEL_ENDPOINT: str = os.getenv("AZURE_DOC_INTEL_ENDPOINT", "")
    AZURE_DOC_INTEL_KEY: str = os.getenv("AZURE_DOC_INTEL_KEY", "")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")


settings = Settings()
