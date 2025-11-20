from pathlib import Path
import re
from datetime import datetime, timedelta
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio

# ================================
# CONFIGURACIÓN DE RUTAS
# ================================

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "PAWSture-main" / "emotions_camara" / "emotions.db"

BOT_TOKEN = "8151081242:AAGZCZucopD3f5FrQTrtw-JW6mAf5aUruCM"  


# ================================
# SISTEMA DE ALERTAS
# ================================

NEGATIVE_EMOTIONS = ["sad", "fear", "angry"]

def check_alerts():
    # Load the Supabase client from the cloud_db.py module (located in PAWSture-main/emotions_camara2)
    alerts = []
    # Read SUPABASE_URL and SUPABASE_KEY from cloud_db.py as plain text (do NOT execute it)
    try:
        cloud_db_path = REPO_ROOT / "PAWSture-main" / "emotions_camara2" / "cloud_db.py"
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

    # 1) Aumento de emociones negativas en últimos 2 minutos
    try:
        since = (datetime.now() - timedelta(minutes=2)).isoformat(sep=" ", timespec="seconds")
        in_list = ",".join(NEGATIVE_EMOTIONS)
        url = f"{base}?select=id,emotion,created_at&emotion=in.({in_list})&created_at=gte.{since}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        negatives = len(data) if isinstance(data, list) else 0
        if negatives >= 3:
            alerts.append("🔴 *Aumento repentino de emociones negativas* (≥3 en 2 minutos).")
    except Exception as e:
        print(f"Error consultando emociones negativas en Supabase (REST): {e}")

    # 2) Stress alto (último registro)
    try:
        url = f"{base}?select=stress_level&order=created_at.desc&limit=1"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            stress = data[0].get("stress_level")
            if stress == "alto":
                alerts.append("🔴 *Nivel de estrés ALTO detectado*.")
    except Exception as e:
        print(f"Error consultando stress en Supabase (REST): {e}")

    # 3) Fear loop (dos miedos en <60s)
    try:
        url = f"{base}?select=emotion,created_at&emotion=eq.fear&order=created_at.desc&limit=2"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and len(data) == 2:
            t1 = datetime.fromisoformat(data[0]["created_at"])
            t2 = datetime.fromisoformat(data[1]["created_at"])
            if (t1 - t2).total_seconds() <= 60:
                alerts.append("🔴 *Patrón repetido de miedo (fear loop).*")
    except Exception as e:
        print(f"Error consultando fear loop en Supabase (REST): {e}")

    # 4) Neutrales prolongadas (últimos 10 minutos)
    try:
        since = (datetime.now() - timedelta(minutes=10)).isoformat(sep=" ", timespec="seconds")
        url = f"{base}?select=id&emotion=eq.neutral&created_at=gte.{since}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        neutral_count = len(data) if isinstance(data, list) else 0
        if neutral_count >= 20:
            alerts.append("🟠 *Demasiadas detecciones 'neutral' (posible error de cámara).*")
    except Exception as e:
        print(f"Error consultando neutrales en Supabase (REST): {e}")

    return alerts


# ================================
# TELEGRAM: ENVIAR ALERTAS CADA 5 MIN
# ================================

CHAT_IDS = set()   # usuarios suscritos


async def send_alerts_periodically(context: ContextTypes.DEFAULT_TYPE):
    """Jobqueue callback: envía las alertas cada intervalo a todos los chats suscritos.

    Se ejecuta en el mismo event loop que el bot y recibe `context` del JobQueue.
    """
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
        "Puedes usar /alertas para ver el estado en cualquier momento.",
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
# MAIN: BOT + SCHEDULER CADA 5 MIN
# ================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Schedule the periodic job using the bot's JobQueue so it runs in the same event loop.
    # run_repeating(callback, interval_seconds, first=delay_seconds)
    app.job_queue.run_repeating(send_alerts_periodically, interval=20, first=0)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alertas", alertas))

    print("Bot corriendo y enviando alertas cada 5 minutos…")
    app.run_polling()


if __name__ == "__main__":
    main()
