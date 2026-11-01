import os
from dotenv import load_dotenv
import psycopg

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL is missing from .env")

try:
    with psycopg.connect(
        database_url,
        connect_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

    if result == (1,):
        print("SUCCESS: Supabase PostgreSQL connection works!")


except Exception as error:
    print("Connection failed.")
    print("Error type:", type(error).__name__)
    raise SystemExit(1)

