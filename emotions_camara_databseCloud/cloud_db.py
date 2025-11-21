from datetime import datetime

from supabase import create_client, Client


SUPABASE_URL = "https://sunsfqthmwotlbfcgmay.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def insert_emotion(
    person_id: str,
    emotion: str,
    gender: str,
    stress_score: float,
    stress_level: str,
    created_at: str | None = None,
) -> None:
    """
    Inserta un registro en la tabla emotions de Supabase.
    """
    if created_at is None:
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    data = {
        "person_id": person_id,
        "emotion": emotion,
        "gender": gender,
        "stress_score": stress_score,
        "stress_level": stress_level,
        "created_at": created_at,
    }

    try:
        supabase.table("emotions").insert(data).execute()
    except Exception as e:
        # Evitar que un fallo de red tumbe toda la app
        print(f"[Supabase] Error insertando emoción: {e}")
