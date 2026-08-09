import os

# Set env vars once for the entire test session before any app import
os.environ.update({
    "DATABASE_URL":      "postgresql+psycopg://u:p@localhost:5432/db",
    "REDIS_URL":         "redis://localhost:6379/0",
    "OPENAI_API_KEY":    "sk-test",
    "FINE_TUNED_MODEL_ID": "ft:gpt-4o-mini:test:triage:abc",
    "JWT_SECRET_KEY":    "a" * 32,
    "INTERNAL_API_KEY":  "test-internal-key",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    "POSTGRES_USER":     "u",
    "POSTGRES_PASSWORD": "p",
    "POSTGRES_DB":       "db",
})
