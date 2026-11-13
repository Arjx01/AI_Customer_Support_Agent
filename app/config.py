import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "orders.db"))
CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", str(BASE_DIR / "chat_checkpoints.db"))

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# RAG & Embedding Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers").lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHROMA_DIR = os.getenv("CHROMA_DIR", str(BASE_DIR / "data" / "chroma_db"))
DOCS_DIR = os.getenv("DOCS_DIR", str(BASE_DIR / "data" / "docs"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.45"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# Refund Business Rules Configuration
REFUND_WINDOW_DAYS = int(os.getenv("REFUND_WINDOW_DAYS", "30"))
NON_REFUNDABLE_KEYWORDS = [
    "gift card",
    "prepaid voucher",
    "software license",
    "digital key",
    "clearance",
    "final sale"
]
