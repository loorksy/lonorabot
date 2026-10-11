import os

os.environ["LONORA_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["LONORA_JWT_SECRET"] = "lonora-test-jwt-signing-secret-1234567890"
