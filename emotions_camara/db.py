import sqlite3
from datetime import datetime

DB_PATH = "emotions.db"

def init_db():
    """
    Crea la BD emotions.db y la tabla Emotions si no existen.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Emotions (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Emotion TEXT,
            Gender TEXT,
            StressScore REAL,
            StressLevel TEXT,
            CreatedAt TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_connection():
    """
    Devuelve conexión abierta a SQLite.
    """
    return sqlite3.connect(DB_PATH)

def insert_emotion(cursor, emotion, gender, stress_score, stress_level, created_at=None):
    if created_at is None:
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    cursor.execute(
        "INSERT INTO Emotions (Emotion, Gender, StressScore, StressLevel, CreatedAt) "
        "VALUES (?, ?, ?, ?, ?)",
        (emotion, gender, stress_score, stress_level, created_at)
    )

