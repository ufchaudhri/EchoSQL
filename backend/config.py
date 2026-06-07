"""
Configuration settings for EchoSQL backend.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ==================== Database ====================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/echosql"
)

# ==================== Redis ====================
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Cache TTLs
EMBEDDING_CACHE_TTL_HOURS = int(os.getenv("EMBEDDING_CACHE_TTL_HOURS", 24))
QUERY_RESULT_CACHE_TTL_MINUTES = int(os.getenv("QUERY_RESULT_CACHE_TTL_MINUTES", 5))

# ==================== Ollama ====================
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen:7b-chat-q4_K_M")
OLLAMA_INFERENCE_TIMEOUT = int(os.getenv("OLLAMA_INFERENCE_TIMEOUT", 5))

# ==================== API ====================
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", 10))

# ==================== Embeddings ====================
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_CACHE_ENABLED = os.getenv("EMBEDDING_CACHE_ENABLED", "true").lower() == "true"
QUERY_RESULT_CACHE_ENABLED = os.getenv("QUERY_RESULT_CACHE_ENABLED", "true").lower() == "true"

# ==================== SQL ====================
SQL_SIMILARITY_THRESHOLD = float(os.getenv("SQL_SIMILARITY_THRESHOLD", 0.85))
MAX_INFERENCE_QUEUE_SIZE = int(os.getenv("MAX_INFERENCE_QUEUE_SIZE", 50))
