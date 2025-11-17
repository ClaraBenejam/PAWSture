# cloud_db.py
from datetime import datetime

from supabase import create_client, Client


SUPABASE_URL = "https://sunsfqthmwotlbfcgmay.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en las variables de entorno")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def insert_emotion(emotion: str, gender: str, stress_score: float, stress_level: str, created_at: str | None = None):
    """
    Inserta un registro en la tabla emotions de Supabase.
    """
    if created_at is None:
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    data = {
        "emotion": emotion,
        "gender": gender,
        "stress_score": stress_score,
        "stress_level": stress_level,
        "created_at": created_at,
    }

    # Llamada a la API de Supabase
    supabase.table("emotions").insert(data).execute()
