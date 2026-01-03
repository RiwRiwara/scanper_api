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

    # MongoDB Atlas
    MONGODB_URL: str = os.getenv("MONGODB_URL", "")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "scanper")

    # Beam Payment Gateway (Production)
    BEAM_API_URL: str = os.getenv("BEAM_API_URL", "https://api.beamcheckout.com")
    BEAM_MERCHANT_ID: str = os.getenv("BEAM_MERCHANT_ID", "")
    BEAM_API_KEY: str = os.getenv("BEAM_API_KEY", "")
    BEAM_WEBHOOK_SECRET: str = os.getenv("BEAM_WEBHOOK_SECRET", "")

    # Frontend URL for redirects
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://liff.line.me")

    # LIFF URL for opening full OCR results
    LIFF_URL: str = os.getenv("LIFF_URL", "https://liff.line.me/YOUR_LIFF_ID")


settings = Settings()
