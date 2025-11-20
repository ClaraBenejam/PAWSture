from pathlib import Path
import re
from datetime import datetime, timedelta
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio

import sys
from pathlib import Path

# Agregar carpeta padre (ruben/) al path
sys.path.append(str(Path(__file__).resolve().parent / "PAWSture-main"))

# Ahora sí podemos importar cloud_db
from cloud_db import log_user_response
# ================================
# CONFIGURACIÓN DE RUTAS Y BOT
# ================================
REPO_ROOT = Path(__file__).resolve().parent

BOT_TOKEN = "8151081242:AAGZCZucopD3f5FrQTrtw-JW6mAf5aUruCM"  
CHAT_IDS = set()  # Usuarios suscritos

# ================================
# ALERTAS
# ================================
NEGATIVE_EMOTIONS = ["sad", "fear", "angry"]

def check_alerts():
    """
    Revisa la base de datos de emociones y genera alertas.
    """
    alerts = []

    # Leer Supabase URL/KEY de cloud_db.py
    try:
        cloud_db_path = REPO_ROOT / "cloud_db.py"
        txt = cloud_db_path.read_text(encoding="utf-8")
        m_url = re.search(r"SUPABASE_URL\s*=\s*[\"'](.+?)[\"']", txt)
        m_key = re.search(r"SUPABASE_KEY\s*=\s*[\"'](.+?)[\"']", txt)
        if not m_url or not m_key:
            print("No se encontraron SUPABASE_URL/SUPABASE_KEY en cloud_db.py")
            return alerts
        SUPABASE_URL = m_url.group(1).strip()
        SUPABASE_KEY = m_key.group(1).strip()
    except Exception as e:
        print(f"Error leyendo cloud_db.py: {e}")
        return alerts

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }

    base = SUPABASE_URL.rstrip("/") + "/rest/v1/emotions"

    now = datetime.now()

    # 1) Aumento de emociones negativas en últimos 2 minutos
    try:
        since = (now - timedelta(minutes=2)).isoformat(sep=" ", timespec="seconds")
        in_list = ",".join(NEGATIVE_EMOTIONS)
        url = f"{base}?select=id,emotion,created_at&emotion=in.({in_list})&created_at=gte.{since}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if len(data) >= 3:
            alerts.append("🔴 *Aumento repentino de emociones negativas* (≥3 en 2 minutos).")
    except Exception as e:
        print(f"Error consultando emociones negativas: {e}")

    # 2) Stress alto (último registro)
    try:
        url = f"{base}?select=stress_level&order=created_at.desc&limit=1"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if data and data[0].get("stress_level") == "alto":
            alerts.append("🔴 *Nivel de estrés ALTO detectado*.") 
    except Exception as e:
        print(f"Error consultando estrés: {e}")

    # 3) Fear loop
    try:
        url = f"{base}?select=emotion,created_at&emotion=eq.fear&order=created_at.desc&limit=2"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if len(data) == 2:
            t1 = datetime.fromisoformat(data[0]["created_at"])
            t2 = datetime.fromisoformat(data[1]["created_at"])
            if (t1 - t2).total_seconds() <= 60:
                alerts.append("🔴 *Patrón repetido de miedo (fear loop).*")
    except Exception as e:
        print(f"Error consultando fear loop: {e}")

    # 4) Neutrales prolongadas
    try:
        since = (now - timedelta(minutes=10)).isoformat(sep=" ", timespec="seconds")
        url = f"{base}?select=id&emotion=eq.neutral&created_at=gte.{since}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if len(data) >= 20:
            alerts.append("🟠 *Demasiadas detecciones 'neutral' (posible error de cámara).*")
    except Exception as e:
        print(f"Error consultando neutrales: {e}")

    return alerts

# ================================
# BOT TELEGRAM
# ================================
async def send_alerts_periodically(context: ContextTypes.DEFAULT_TYPE):
    alerts = check_alerts()
    if not alerts:
        message = "🟢 *Todo en orden.* No hay alertas."
    else:
        message = "📢 *Alertas detectadas:*\n\n" + "\n".join(alerts)

    for chat_id in CHAT_IDS:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        except Exception as e:
            print(f"Error enviando mensaje a {chat_id}: {e}")


# ================================
# COMANDOS DEL BOT
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS.add(update.message.chat_id)
    await update.message.reply_text(
        "🐾 *PAWSture Alert Bot*\n"
        "Te has suscrito correctamente.\n"
        "Recibirás alertas cada X minutos.\n\n"
        "Usa /alertas para ver el estado.",
        parse_mode="Markdown"
    )

async def alertas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts = check_alerts()
    if not alerts:
        await update.message.reply_text("🟢 No se han detectado alertas.", parse_mode="Markdown")
    else:
        mensaje = "📢 *Alertas detectadas:*\n\n" + "\n".join(alerts)
        await update.message.reply_text(mensaje, parse_mode="Markdown")

# ================================
# COMANDOS PARA ACEPTAR / RECHAZAR RECOMENDACIONES
# ================================
async def _fetch_latest_recommendation():
    """Devuelve el último registro de `recommendations` desde Supabase (o None)."""
    try:
        cloud_db_path = REPO_ROOT / "cloud_db.py"
        txt = cloud_db_path.read_text(encoding="utf-8")
        m_url = re.search(r"SUPABASE_URL\s*=\s*[\"'](.+?)[\"']", txt)
        m_key = re.search(r"SUPABASE_KEY\s*=\s*[\"'](.+?)[\"']", txt)
        if not m_url or not m_key:
            return None
        SUPABASE_URL = m_url.group(1).strip()
        SUPABASE_KEY = m_key.group(1).strip()
    except Exception:
        return None

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    base = SUPABASE_URL.rstrip("/") + "/rest/v1/recommendations"
    try:
        url = f"{base}?select=*&order=created_at.desc&limit=1"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
    except Exception:
        return None

    return None


async def aceptar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rec = await _fetch_latest_recommendation()
    if rec:
        # registrar respuesta en la BD
        log_user_response(rec.get('activity_name') or rec.get('name'), rec.get('activity_type') or rec.get('type'), True)
        await update.message.reply_text(f"🎉 Has aceptado: {rec.get('activity_name') or rec.get('name')}")
    else:
        await update.message.reply_text("❌ No hay recomendación activa.")


async def rechazar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rec = await _fetch_latest_recommendation()
    if rec:
        log_user_response(rec.get('activity_name') or rec.get('name'), rec.get('activity_type') or rec.get('type'), False)
        await update.message.reply_text(f"❌ Has rechazado: {rec.get('activity_name') or rec.get('name')}")
    else:
        await update.message.reply_text("❌ No hay recomendación activa.")

# ================================
# MAIN: INICIALIZAR BOT Y JOB
# ================================
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alertas", alertas))
    app.add_handler(CommandHandler("aceptar", aceptar))
    app.add_handler(CommandHandler("rechazar", rechazar))

    # JobQueue: alerta cada 5 min
    app.job_queue.run_repeating(send_alerts_periodically, interval=20   , first=0)

    print("🤖 Bot corriendo…")
    app.run_polling()  # Bloqueante. Maneja su propio event loop internamente.


if __name__ == "__main__":
    main()

