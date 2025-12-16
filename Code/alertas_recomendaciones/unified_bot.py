# unified_bot.py
from pathlib import Path
import re
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest
import asyncio
import os
import json
import sys
import signal
import time
from collections import defaultdict

# Add the project root to Python path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.append(str(REPO_ROOT))

# Import recommendation system and database functions
from recommendation_system import RecommendationSystem
from cloud_db import insert_recommendation_response, get_recommendation_responses, get_user_response_stats

# ================================
# CONFIGURATION - UNIFIED SYSTEM IMPROVED
# ================================

# Timing configuration
POSTURE_WINDOW_SECONDS = 10       # Posture analysis window
EMOTION_WINDOW_SECONDS = 50       # Emotion analysis window
CHECK_INTERVAL_SECONDS = 10       # Check interval
POSTURE_COOLDOWN_SECONDS = 30     # Posture cooldown
EMOTION_COOLDOWN_SECONDS = 30     # Emotion cooldown

# Posture thresholds - DETECT LEVEL 2 BUT ONLY RECOMMEND FOR LEVEL 3+
POSTURE_CRITICAL_THRESHOLD = 4    # Minimum 4 zone 4+ measurements
POSTURE_HIGH_THRESHOLD = 5        # Minimum 5 zone 3+ measurements
POSTURE_MEDIUM_THRESHOLD = 6      # Minimum 6 zone 2+ measurements (for display only)
SPECIFIC_POSTURE_THRESHOLD = 4    # Minimum 4 specific issue measurements

# Emotion thresholds - reduced sensitivity
EMOTION_THRESHOLD = 5             # Minimum 5 negative emotions
STRESS_THRESHOLD = 4              # Minimum 4 high stress records
SPECIFIC_EMOTION_THRESHOLD = 4    # Minimum 4 same emotion records

CHAT_IDS = set()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8151081242:AAGZCZucopD3f5FrQTrtw-JW6mAf5aUruCM")
CHAT_STORE = REPO_ROOT / "unified_chat_ids.json"

# Initialize recommendation system
recommendation_system = RecommendationSystem(REPO_ROOT)

# Supabase credentials
SUPABASE_URL = "https://sunsfqthmwotlbfcgmay.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Accept": "application/json",
}

# Global control variables
running = True
# Structure: {user_id: {chat_id: last_alert_time}} for posture Level 3+
POSTURE_COOLDOWNS = defaultdict(lambda: defaultdict(lambda: None))
# Structure: {user_id: {chat_id: last_alert_time}} for posture Level 2
POSTURE_LEVEL2_COOLDOWNS = defaultdict(lambda: defaultdict(lambda: None))
# Structure: {user_id: {chat_id: last_alert_time}} for emotions
EMOTION_COOLDOWNS = defaultdict(lambda: defaultdict(lambda: None))

NEGATIVE_EMOTIONS = ["sad", "fear", "angry", "disgust"]

# ================================
# SIGNAL HANDLER
# ================================

def signal_handler(sig, frame):
    """
    Handle Ctrl+C to gracefully terminate the bot
    
    Args:
        sig (int): Signal number
        frame: Current stack frame
    """
    global running
    print(f"\nSignal {sig} received. Stopping bot...")
    running = False
    time.sleep(0.5)
    sys.exit(0)

# Register signal handler
signal.signal(signal.SIGINT, signal_handler)

# ================================
# CHAT ID MANAGEMENT
# ================================

def load_persisted_chat_ids():
    """
    Load persisted chat IDs from JSON file
    
    Returns:
        set: Set of chat IDs
    """
    try:
        if CHAT_STORE.exists():
            txt = CHAT_STORE.read_text(encoding="utf-8")
            arr = json.loads(txt)
            return set(arr)
    except Exception as e:
        print(f"Error loading persisted chat_ids: {e}")
    return set()

def save_persisted_chat_ids(chat_ids):
    """
    Save chat IDs to JSON file
    
    Args:
        chat_ids (set): Set of chat IDs to save
    """
    try:
        CHAT_STORE.write_text(json.dumps(list(chat_ids), ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Error saving persisted chat_ids: {e}")

CHAT_IDS.update(load_persisted_chat_ids())

# ================================
# UNIFIED DETECTION SYSTEM - IMPROVED FOR ALL USERS
# ================================

def escape_telegram_text(text):
    """
    Escape Markdown special characters for Telegram
    
    Args:
        text (str): Text to escape
        
    Returns:
        str: Escaped text
    """
    if not text:
        return text
    
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    return text

def determine_posture_risk_type(alerts):
    """
    Determine posture risk type based on alerts
    
    Args:
        alerts (list): List of alert strings
        
    Returns:
        str: Risk type identifier
    """
    if not alerts:
        return "general_posture"
    
    # Priority of posture risks (from most to least critical)
    for alert in alerts:
        alert_lower = alert.lower()
        if "critical" in alert_lower or "zone 4" in alert:
            return "critical_posture"
        elif "high risk" in alert_lower or "zone 3" in alert:
            return "general_posture"
        elif "flexion" in alert_lower or "neck" in alert_lower:
            return "neck_flexion"
        elif "shoulders" in alert_lower:
            return "shoulder_alignment"
    
    return "general_posture"

def determine_emotion_risk_type(alerts):
    """
    Determine emotion risk type based on alerts
    
    Args:
        alerts (list): List of alert strings
        
    Returns:
        str: Risk type identifier
    """
    if not alerts:
        return "general_posture"
    
    for alert in alerts:
        alert_lower = alert.lower()
        if "stress" in alert_lower:
            return "stress_high"
        elif any(word in alert_lower for word in ["anger", "sadness", "fear", "disgust", "emotions"]):
            return "negative_emotion"
    
    return "negative_emotion"

def check_posture_alerts_all_users():
    """
    Check for posture alert conditions for ALL users
    
    Returns:
        tuple: (user_alerts, user_recommendation_alerts, user_risk_types)
            - user_alerts: dict {user_id: [all_alerts]}
            - user_recommendation_alerts: dict {user_id: [level3+_alerts]}
            - user_risk_types: dict {user_id: risk_type}
    """
    user_alerts = {}  # {user_id: [alerts]}
    user_recommendation_alerts = {}  # {user_id: [recommendation_alerts]}
    user_risk_types = {}  # {user_id: risk_type}
    
    base = SUPABASE_URL.rstrip("/") + "/rest/v1/posture"
    
    print(f"Analyzing posture for ALL users (window: {POSTURE_WINDOW_SECONDS}s)...")
    
    # 1) Check for ALL posture levels in last 10 seconds for ALL users
    try:
        since = (datetime.now() - timedelta(seconds=POSTURE_WINDOW_SECONDS)).isoformat(sep=" ", timespec="seconds")
        # Modified: Remove user filter to get all users
        url = f"{base}?select=id_usuario,overall_zone,overall_risk,timestamp&overall_zone=gte.2&timestamp=gte.{since}&order=timestamp.desc"
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                # Group by user
                users_data = defaultdict(list)
                for item in data:
                    user_id = item.get('id_usuario')
                    if user_id:
                        users_data[user_id].append(item)
                
                # Analyze each user
                for user_id, measurements in users_data.items():
                    user_id_str = str(user_id)
                    total_measurements = len(measurements)
                    latest_posture = measurements[0]
                    zone = latest_posture.get('overall_zone', 0)
                    
                    # Initialize lists for this user
                    user_alerts[user_id_str] = []
                    user_recommendation_alerts[user_id_str] = []
                    
                    # DETECT ALL LEVELS for display
                    if zone >= 4 and total_measurements >= POSTURE_CRITICAL_THRESHOLD:
                        user_alerts[user_id_str].append(f"CRITICAL POSTURE - Zone {zone} ({total_measurements} measurements)")
                        user_recommendation_alerts[user_id_str].append(f"CRITICAL POSTURE - Zone {zone} ({total_measurements} measurements)")
                        print(f"Alert for User {user_id}: Critical posture zone {zone}")
                    elif zone >= 3 and total_measurements >= POSTURE_HIGH_THRESHOLD:
                        user_alerts[user_id_str].append(f"HIGH RISK - Zone {zone} ({total_measurements} measurements)")
                        user_recommendation_alerts[user_id_str].append(f"HIGH RISK - Zone {zone} ({total_measurements} measurements)")
                        print(f"Alert for User {user_id}: High risk zone {zone}")
                    elif zone >= 2 and total_measurements >= POSTURE_MEDIUM_THRESHOLD:
                        # Level 2: Display only, NO recommendation
                        user_alerts[user_id_str].append(f"MEDIUM RISK - Zone {zone} ({total_measurements} measurements)")
                        print(f"Info for User {user_id}: Medium risk zone {zone} (no recommendation)")
                
    except Exception as e:
        print(f"Error querying general posture for all users: {e}")

    # 2) Check for specific posture issues - ALL USERS
    try:
        since = (datetime.now() - timedelta(seconds=20)).isoformat(timespec="seconds")
        # Modified: Get data for all users
        url = f"{base}?select=id_usuario,neck_flexion_zone,shoulder_alignment_zone,neck_lateral_bend_zone,timestamp&timestamp=gte.{since}&order=timestamp.desc&limit=100"
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                # Group by user
                users_data = defaultdict(list)
                for item in data:
                    user_id = item.get('id_usuario')
                    if user_id:
                        users_data[user_id].append(item)
                
                # Analyze each user
                for user_id, measurements in users_data.items():
                    user_id_str = str(user_id)
                    
                    # Initialize lists if not exists
                    if user_id_str not in user_alerts:
                        user_alerts[user_id_str] = []
                        user_recommendation_alerts[user_id_str] = []
                    
                    # Count by levels
                    neck_flexion_count_level2 = sum(1 for item in measurements if item.get('neck_flexion_zone', 0) == 2)
                    neck_flexion_count_level3 = sum(1 for item in measurements if item.get('neck_flexion_zone', 0) >= 3)
                    
                    shoulder_count_level2 = sum(1 for item in measurements if item.get('shoulder_alignment_zone', 0) == 2)
                    shoulder_count_level3 = sum(1 for item in measurements if item.get('shoulder_alignment_zone', 0) >= 3)
                    
                    neck_bend_count_level2 = sum(1 for item in measurements if item.get('neck_lateral_bend_zone', 0) == 2)
                    neck_bend_count_level3 = sum(1 for item in measurements if item.get('neck_lateral_bend_zone', 0) >= 3)
                    
                    print(f"Posture details for User {user_id}: Neck(L2={neck_flexion_count_level2}, L3+={neck_flexion_count_level3}), Shoulders(L2={shoulder_count_level2}, L3+={shoulder_count_level3})")
                    
                    # Level 2: Display only
                    if neck_flexion_count_level2 >= SPECIFIC_POSTURE_THRESHOLD:
                        user_alerts[user_id_str].append(f"NECK FLEXION - Medium (Level 2: {neck_flexion_count_level2} measurements)")
                        print(f"Info for User {user_id}: Neck flexion (Level 2)")
                    if shoulder_count_level2 >= SPECIFIC_POSTURE_THRESHOLD:
                        user_alerts[user_id_str].append(f"SHOULDER MISALIGNMENT - Medium (Level 2: {shoulder_count_level2} measurements)")
                        print(f"Info for User {user_id}: Shoulder misalignment (Level 2)")
                    if neck_bend_count_level2 >= SPECIFIC_POSTURE_THRESHOLD:
                        user_alerts[user_id_str].append(f"NECK INCLINATION - Medium (Level 2: {neck_bend_count_level2} measurements)")
                        print(f"Info for User {user_id}: Neck inclination (Level 2)")
                    
                    # Level 3+: For display AND recommendation
                    if neck_flexion_count_level3 >= SPECIFIC_POSTURE_THRESHOLD:
                        user_alerts[user_id_str].append(f"NECK FLEXION - High (Level 3+: {neck_flexion_count_level3} measurements)")
                        user_recommendation_alerts[user_id_str].append(f"NECK FLEXION - High (Level 3+: {neck_flexion_count_level3} measurements)")
                        print(f"Alert for User {user_id}: Neck flexion (Level 3+)")
                    if shoulder_count_level3 >= SPECIFIC_POSTURE_THRESHOLD:
                        user_alerts[user_id_str].append(f"SHOULDER MISALIGNMENT - High (Level 3+: {shoulder_count_level3} measurements)")
                        user_recommendation_alerts[user_id_str].append(f"SHOULDER MISALIGNMENT - High (Level 3+: {shoulder_count_level3} measurements)")
                        print(f"Alert for User {user_id}: Shoulder misalignment (Level 3+)")
                    if neck_bend_count_level3 >= SPECIFIC_POSTURE_THRESHOLD:
                        user_alerts[user_id_str].append(f"NECK INCLINATION - High (Level 3+: {neck_bend_count_level3} measurements)")
                        user_recommendation_alerts[user_id_str].append(f"NECK INCLINATION - High (Level 3+: {neck_bend_count_level3} measurements)")
                        print(f"Alert for User {user_id}: Neck inclination (Level 3+)")
                
    except Exception as e:
        print(f"Error querying specific posture issues for all users: {e}")

    # Determine risk type for each user based only on level 3+ alerts
    for user_id_str, rec_alerts in user_recommendation_alerts.items():
        user_risk_types[user_id_str] = determine_posture_risk_type(rec_alerts)
    
    print(f"Posture detection completed for {len(user_alerts)} users")
    return user_alerts, user_recommendation_alerts, user_risk_types

def check_emotion_alerts_all_users():
    """
    Check for emotion alert conditions for ALL users
    
    Returns:
        tuple: (user_alerts, user_risk_types)
            - user_alerts: dict {user_id: [alerts]}
            - user_risk_types: dict {user_id: risk_type}
    """
    user_alerts = {}  # {user_id: [alerts]}
    user_risk_types = {}  # {user_id: risk_type}
    
    base = SUPABASE_URL.rstrip("/") + "/rest/v1/emotions"
    
    current_time = datetime.now()
    since_time = current_time - timedelta(seconds=EMOTION_WINDOW_SECONDS)
    since_str = since_time.isoformat(sep=" ", timespec="seconds")
    
    print(f"Analyzing emotions for ALL users (window: {EMOTION_WINDOW_SECONDS}s)...")
    
    # 1) NEGATIVE EMOTIONS - ALL USERS
    try:
        in_list = ",".join([f'"{emotion}"' for emotion in NEGATIVE_EMOTIONS])
        # Modified: Remove user filter to get all users
        url = f"{base}?select=person_id,emotion,created_at&emotion=in.({in_list})&created_at=gte.{since_str}&order=created_at.desc"
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                # Group by user
                users_data = defaultdict(list)
                for item in data:
                    user_id = item.get('person_id')
                    if user_id:
                        users_data[user_id].append(item)
                
                # Analyze each user
                for user_id, measurements in users_data.items():
                    user_id_str = str(user_id)
                    total_negatives = len(measurements)
                    
                    if total_negatives >= EMOTION_THRESHOLD:
                        print(f"Negative emotions total for User {user_id}: {total_negatives}")
                        
                        emotion_counts = {}
                        for item in measurements:
                            emotion = item.get('emotion', 'unknown')
                            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
                        
                        # Initialize lists for this user
                        if user_id_str not in user_alerts:
                            user_alerts[user_id_str] = []
                        
                        for emotion, count in emotion_counts.items():
                            if count >= SPECIFIC_EMOTION_THRESHOLD:
                                if emotion == "angry":
                                    user_alerts[user_id_str].append(f"PERSISTENT ANGER ({count} times)")
                                    print(f"Alert for User {user_id}: Persistent anger")
                                elif emotion == "sad":
                                    user_alerts[user_id_str].append(f"PERSISTENT SADNESS ({count} times)")
                                    print(f"Alert for User {user_id}: Persistent sadness")
                                elif emotion == "fear":
                                    user_alerts[user_id_str].append(f"PERSISTENT FEAR ({count} times)")
                                    print(f"Alert for User {user_id}: Persistent fear")
                                elif emotion == "disgust":
                                    user_alerts[user_id_str].append(f"PERSISTENT DISGUST ({count} times)")
                                    print(f"Alert for User {user_id}: Persistent disgust")
                        
                        if not user_alerts[user_id_str] and total_negatives >= (EMOTION_THRESHOLD + 3):
                            user_alerts[user_id_str].append(f"MULTIPLE NEGATIVE EMOTIONS ({total_negatives} records)")
                            print(f"Alert for User {user_id}: Multiple negative emotions")
                    else:
                        print(f"Insufficient negative emotions for User {user_id}: {total_negatives}/{EMOTION_THRESHOLD}")
                        
    except Exception as e:
        print(f"Error querying negative emotions for all users: {e}")

    # 2) HIGH STRESS - ALL USERS
    try:
        # Modified: Remove user filter to get all users
        url = f"{base}?select=person_id,stress_level,created_at&stress_level=eq.alto&created_at=gte.{since_str}&order=created_at.desc"
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                # Group by user
                users_data = defaultdict(list)
                for item in data:
                    user_id = item.get('person_id')
                    if user_id:
                        users_data[user_id].append(item)
                
                for user_id, measurements in users_data.items():
                    user_id_str = str(user_id)
                    high_stress_count = len(measurements)
                    
                    if high_stress_count >= STRESS_THRESHOLD:
                        # Initialize lists if not exists
                        if user_id_str not in user_alerts:
                            user_alerts[user_id_str] = []
                        
                        user_alerts[user_id_str].append(f"PERSISTENT HIGH STRESS ({high_stress_count} records)")
                        print(f"Alert for User {user_id}: Persistent high stress")
                    else:
                        print(f"Insufficient high stress for User {user_id}: {high_stress_count}/{STRESS_THRESHOLD}")
    except Exception as e:
        print(f"Error querying stress for all users: {e}")
    
    # Determine risk type for each user
    for user_id_str, alerts in user_alerts.items():
        user_risk_types[user_id_str] = determine_emotion_risk_type(alerts)
    
    print(f"Emotion detection completed for {len(user_alerts)} users")
    return user_alerts, user_risk_types

def format_beautiful_message(title, alerts, recommendation, user_id):
    """
    Format a beautiful message for Telegram with user info
    
    Args:
        title (str): Message title
        alerts (list): List of alert strings
        recommendation (dict): Recommendation data
        user_id (str/int): User ID
        
    Returns:
        str: Formatted Telegram message
    """
    # Define urgency colors and icons
    urgency_styles = {
        "critical": {"icon": "🚨", "color": "#FF0000"},
        "high": {"icon": "🔥", "color": "#FF6B00"},
        "medium": {"icon": "⚠️", "color": "#FFC400"},
        "low": {"icon": "💡", "color": "#00C853"}
    }
    
    urgency = recommendation.get('urgency', 'medium')
    style = urgency_styles.get(urgency, urgency_styles['medium'])
    
    # Build the message
    message = f"{style['icon']} *{title}*\n"
    message += f"👤 *User:* {user_id}\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if alerts:
        message += "*Detected Issues:*\n"
        for alert in alerts[:3]:  # Max 3 alerts
            clean_alert = escape_telegram_text(alert)
            # Remove count indicators for cleaner display
            clean_alert = re.sub(r'\(\d+.*?\)', '', clean_alert).strip()
            message += f"• {clean_alert}\n"
        message += "\n"
    
    # Recommendation section
    message += "*Recommended Intervention*\n"
    message += f"📝 *{recommendation['name']}*\n"
    message += f"_{recommendation['description']}_\n\n"
    
    message += f"⏱️ *Duration:* {recommendation['duration']}\n"
    
    # Add steps with better formatting
    if recommendation.get('steps'):
        message += "\n*Steps to Follow:*\n"
        for i, step in enumerate(recommendation['steps'], 1):
            message += f"{i}. {step}\n"
    
    # Add timestamp
    message += f"\n📅 *Generated:* {datetime.now().strftime('%H:%M')}"
    
    return message

def create_level2_alert_message(alerts, user_id):
    """
    Create an alert message for Level 2 posture issues (without recommendation)
    
    Args:
        alerts (list): List of alert strings
        user_id (str/int): User ID
        
    Returns:
        str: Formatted message or None if no Level 2 alerts
    """
    # Filter only level 2 alerts
    level2_alerts = [alert for alert in alerts if "Medium" in alert or "Level 2" in alert]
    
    if not level2_alerts:
        return None
    
    message = f"📊 *POSTURE MONITORING - USER {user_id}*\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += "*MODERATE POSTURE ISSUES DETECTED*\n\n"
    
    message += "*Issues Found:*\n"
    for alert in level2_alerts[:3]:  # Max 3 alerts
        # Clean the alert text
        clean_alert = escape_telegram_text(alert)
        # Remove technical details for cleaner display
        clean_alert = re.sub(r'\(\d+.*?\)', '', clean_alert).strip()
        clean_alert = clean_alert.replace(" - Medium", "").replace("Medium", "").strip()
        message += f"• {clean_alert}\n"
    
    message += "\n💡 *Note:* These are moderate posture issues. No intervention required at this time.\n"
    message += "Continue monitoring your posture and consider taking a short break.\n\n"
    
    message += f"⏰ *Detection window:* {POSTURE_WINDOW_SECONDS} seconds\n"
    message += f"📅 *Detected at:* {datetime.now().strftime('%H:%M:%S')}"
    
    return message

def get_posture_recommendation(alerts, risk_type, user_id):
    """
    Generate specific recommendation for posture alerts - ONLY FOR LEVEL 3+
    
    Args:
        alerts (list): List of alert strings
        risk_type (str): Risk type identifier
        user_id (str/int): User ID
        
    Returns:
        tuple: (recommendation_dict, message_str) or (None, None)
    """
    if not alerts:
        return None, None
    
    print(f"Generating POSTURE recommendation for User {user_id} with risk: {risk_type}")
    print(f"Posture alerts received for User {user_id}: {len(alerts)}")
    
    # If no level 3+ alerts, don't generate recommendation
    if len(alerts) == 0:
        print(f"No Level 3+ posture alerts for User {user_id} - skipping recommendation")
        return None, None
    
    try:
        # Get recommendation from system
        recommendation = recommendation_system.generate_recommendation(
            user_id=user_id,
            risk_type=risk_type
        )
        
        if recommendation:
            print(f"Posture recommendation for User {user_id} generated: {recommendation['name']}")
            
            # Format beautiful message with user info
            if "critical_posture" in risk_type:
                title = "CRITICAL POSTURE ALERT"
            else:
                title = "POSTURE ADJUSTMENT NEEDED"
            
            message = format_beautiful_message(title, alerts, recommendation, user_id)
            return recommendation, message
        else:
            print(f"Could not generate posture recommendation for User {user_id} (empty)")
            
    except Exception as e:
        print(f"Error generating posture recommendation for User {user_id}: {e}")
        import traceback
        traceback.print_exc()
    
    return None, None

def get_emotion_recommendation(alerts, risk_type, user_id):
    """
    Generate specific recommendation for emotion alerts
    
    Args:
        alerts (list): List of alert strings
        risk_type (str): Risk type identifier
        user_id (str/int): User ID
        
    Returns:
        tuple: (recommendation_dict, message_str) or (None, None)
    """
    if not alerts:
        return None, None
    
    print(f"Generating EMOTION recommendation for User {user_id} with risk: {risk_type}")
    print(f"Emotion alerts received for User {user_id}: {len(alerts)}")
    
    try:
        # Get recommendation from system
        recommendation = recommendation_system.generate_recommendation(
            user_id=user_id,
            risk_type=risk_type
        )
        
        if recommendation:
            print(f"Emotion recommendation for User {user_id} generated: {recommendation['name']}")
            
            # Format beautiful message with user info
            if "stress_high" in risk_type:
                title = "HIGH STRESS DETECTED"
            else:
                title = "EMOTIONAL SUPPORT NEEDED"
            
            message = format_beautiful_message(title, alerts, recommendation, user_id)
            return recommendation, message
        else:
            print(f"Could not generate emotion recommendation for User {user_id} (empty)")
            
    except Exception as e:
        print(f"Error generating emotion recommendation for User {user_id}: {e}")
        import traceback
        traceback.print_exc()
    
    return None, None

# ================================
# INDEPENDENT COOLDOWNS PER USER - MODIFIED
# ================================

def is_posture_cooldown_active(chat_id, user_id):
    """
    Check if posture cooldown is active for specific user
    
    Args:
        chat_id (int): Telegram chat ID
        user_id (int): User ID
        
    Returns:
        bool: True if cooldown is active
    """
    if user_id not in POSTURE_COOLDOWNS:
        return False
    if chat_id not in POSTURE_COOLDOWNS[user_id]:
        return False
    
    last_sent = POSTURE_COOLDOWNS[user_id][chat_id]
    if last_sent is None:
        return False
    
    time_since_last = (datetime.now() - last_sent).total_seconds()
    
    if time_since_last < POSTURE_COOLDOWN_SECONDS:
        remaining = int(POSTURE_COOLDOWN_SECONDS - time_since_last)
        print(f"Posture cooldown active for User {user_id}: {remaining}s remaining (chat ID: {chat_id})")
        return True
    
    return False

def is_posture_level2_cooldown_active(chat_id, user_id):
    """
    Check if posture Level 2 alert cooldown is active for specific user
    
    Args:
        chat_id (int): Telegram chat ID
        user_id (int): User ID
        
    Returns:
        bool: True if cooldown is active
    """
    if user_id not in POSTURE_LEVEL2_COOLDOWNS:
        return False
    if chat_id not in POSTURE_LEVEL2_COOLDOWNS[user_id]:
        return False
    
    last_sent = POSTURE_LEVEL2_COOLDOWNS[user_id][chat_id]
    if last_sent is None:
        return False
    
    time_since_last = (datetime.now() - last_sent).total_seconds()
    
    # Level 2 alerts use the same cooldown
    if time_since_last < POSTURE_COOLDOWN_SECONDS:
        remaining = int(POSTURE_COOLDOWN_SECONDS - time_since_last)
        print(f"Posture Level 2 cooldown active for User {user_id}: {remaining}s remaining (chat ID: {chat_id})")
        return True
    
    return False

def is_emotion_cooldown_active(chat_id, user_id):
    """
    Check if emotion cooldown is active for specific user
    
    Args:
        chat_id (int): Telegram chat ID
        user_id (int): User ID
        
    Returns:
        bool: True if cooldown is active
    """
    if user_id not in EMOTION_COOLDOWNS:
        return False
    if chat_id not in EMOTION_COOLDOWNS[user_id]:
        return False
    
    last_sent = EMOTION_COOLDOWNS[user_id][chat_id]
    if last_sent is None:
        return False
    
    time_since_last = (datetime.now() - last_sent).total_seconds()
    
    if time_since_last < EMOTION_COOLDOWN_SECONDS:
        remaining = int(EMOTION_COOLDOWN_SECONDS - time_since_last)
        print(f"Emotion cooldown active for User {user_id}: {remaining}s remaining (chat ID: {chat_id})")
        return True
    
    return False

def update_posture_cooldown(chat_id, user_id):
    """
    Update last posture message time for specific user
    
    Args:
        chat_id (int): Telegram chat ID
        user_id (int): User ID
    """
    POSTURE_COOLDOWNS[user_id][chat_id] = datetime.now()
    print(f"Posture cooldown updated for User {user_id} (chat ID: {chat_id})")

def update_posture_level2_cooldown(chat_id, user_id):
    """
    Update last posture Level 2 alert time for specific user
    
    Args:
        chat_id (int): Telegram chat ID
        user_id (int): User ID
    """
    POSTURE_LEVEL2_COOLDOWNS[user_id][chat_id] = datetime.now()
    print(f"Posture Level 2 cooldown updated for User {user_id} (chat ID: {chat_id})")

def update_emotion_cooldown(chat_id, user_id):
    """
    Update last emotion message time for specific user
    
    Args:
        chat_id (int): Telegram chat ID
        user_id (int): User ID
    """
    EMOTION_COOLDOWNS[user_id][chat_id] = datetime.now()
    print(f"Emotion cooldown updated for User {user_id} (chat ID: {chat_id})")

# ================================
# TELEGRAM COMMAND HANDLERS
# ================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /start command - Subscribe to monitoring
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    chat_id = update.message.chat_id
    CHAT_IDS.add(chat_id)
    save_persisted_chat_ids(CHAT_IDS)

    welcome_message = """*PAWSture Health Monitor - Active*

✅ *Subscription confirmed*
Monitoring posture and emotions every 10 seconds

⏰ *Configuration:*
• Check interval: 10 seconds
• Posture: 10s window, 30s cooldown
• Emotions: 50s window, 30s cooldown
• Independent systems with separate cooldowns

🎯 *Posture detection:* ALL USERS, ALL LEVELS (2-4)
🎯 *Automatic alerts:* Level 2+ (info only), Level 3+ (with recommendation)
🎯 *Emotion detection:* ALL USERS, Persistent patterns

🔧 *Available Commands:*
• /status - Current health status
• /recommendation - Request manual intervention
• /stats - Response statistics
• /posture_status - Posture only status
• /emotion_status - Emotion only status
• /config - Current settings
• /model_status - AI system status"""

    await update.message.reply_text(welcome_message, parse_mode="Markdown")

async def model_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /model_status command - Show AI model status
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    try:
        model_info = """*🤖 AI RECOMMENDATION SYSTEM*

📊 *System Overview:*
• Model: P3FitRec (Personalized Posture & Emotion Fit)
• Training: Historical user response patterns
• Objective: Predict intervention acceptance

🎯 *How It Works:*
1. Analyzes response history to interventions
2. Learns patterns based on time of day and context
3. Predicts which interventions user is most likely to accept
4. Selects optimal activity for current situation

🔍 *Learning Metrics:*
• Three response types: reject, postpone, accept
• Context awareness: morning, afternoon, evening
• Continuous improvement with each response

💡 *Personalization Levels:*
• Basic Rules: When insufficient data is available
• AI-Personalized: After learning user preferences
• Context-Aware: Adjusts based on time and situation

📈 *To Improve Recommendations:*
1. Respond to intervention prompts (✅/⏸️/❌)
2. System learns preferences over time
3. Recommendations become more tailored"""
        
        await update.message.reply_text(model_info, parse_mode="Markdown")
    except Exception as e:
        print(f"Error in model_status: {e}")
        await update.message.reply_text("Error retrieving model status.", parse_mode="Markdown")

async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /config command - Show current configuration
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    config_message = f"""*⚙️ CURRENT CONFIGURATION*

⏱️ *Timing Settings:*
• Check interval: {CHECK_INTERVAL_SECONDS} seconds
• Posture: {POSTURE_WINDOW_SECONDS}s window, {POSTURE_COOLDOWN_SECONDS}s cooldown
• Emotions: {EMOTION_WINDOW_SECONDS}s window, {EMOTION_COOLDOWN_SECONDS}s cooldown
• ✅ Independent cooldown systems per user

🎯 *Posture Detection Thresholds (ALL USERS):*
• Critical (zone 4+): {POSTURE_CRITICAL_THRESHOLD}+ measurements
• High risk (zone 3+): {POSTURE_HIGH_THRESHOLD}+ measurements
• Medium risk (zone 2+): {POSTURE_MEDIUM_THRESHOLD}+ measurements
• Specific issues: {SPECIFIC_POSTURE_THRESHOLD}+ measurements

🎯 *Automatic Alerts:*
• Level 2: Info messages (no recommendation)
• Level 3+: Info messages with recommendations
• All messages include user ID

🎯 *Emotion Detection Thresholds (ALL USERS):*
• Negative emotions: {EMOTION_THRESHOLD}+ records
• High stress: {STRESS_THRESHOLD}+ records
• Specific emotion: {SPECIFIC_EMOTION_THRESHOLD}+ same type

🤖 *AI System Status:*
• Trained: {recommendation_system.is_model_ready}
• Users in model: {len(recommendation_system.data_loader.user_map) if hasattr(recommendation_system, 'data_loader') else 0}
• Available activities: {len(recommendation_system.activity_names) if hasattr(recommendation_system, 'activity_names') else 0}"""

    await update.message.reply_text(config_message, parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /status command - Show combined status for ALL users
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    posture_user_alerts, posture_user_recommendation_alerts, posture_user_risk_types = check_posture_alerts_all_users()
    emotion_user_alerts, emotion_user_risk_types = check_emotion_alerts_all_users()
    
    total_users = len(set(list(posture_user_alerts.keys()) + list(emotion_user_alerts.keys())))
    
    if total_users == 0:
        await update.message.reply_text(
            f"🟢 *Health Status (All Users):* Optimal\n"
            f"No risks detected in the last {max(POSTURE_WINDOW_SECONDS, EMOTION_WINDOW_SECONDS)} seconds.",
            parse_mode="Markdown"
        )
    else:
        msg = f"📊 *Current Status - All Users*\n"
        msg += f"👥 *Monitored users:* {total_users}\n\n"
        
        # Show summary by user
        for user_id in sorted(set(list(posture_user_alerts.keys()) + list(emotion_user_alerts.keys()))):
            msg += f"👤 *User {user_id}:*\n"
            
            if user_id in posture_user_alerts and posture_user_alerts[user_id]:
                posture_count = len(posture_user_alerts[user_id])
                rec_count = len(posture_user_recommendation_alerts.get(user_id, []))
                msg += f"  • Posture: {posture_count} alerts ({rec_count} level 3+)\n"
            
            if user_id in emotion_user_alerts and emotion_user_alerts[user_id]:
                emotion_count = len(emotion_user_alerts[user_id])
                msg += f"  • Emotions: {emotion_count} alerts\n"
            
            if user_id not in posture_user_alerts and user_id not in emotion_user_alerts:
                msg += f"  • 🟢 All normal\n"
            
            msg += "\n"
        
        msg += f"⚠️ *Independent monitoring systems (cooldown: {POSTURE_COOLDOWN_SECONDS}s per user)*"
        await update.message.reply_text(msg, parse_mode="Markdown")

async def posture_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /posture_status command - Show only posture status for ALL users
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    posture_user_alerts, posture_user_recommendation_alerts, posture_user_risk_types = check_posture_alerts_all_users()
    
    if not posture_user_alerts:
        await update.message.reply_text(
            f"💺 *Posture Status (All Users):* Optimal\n"
            f"No posture risks detected in the last {POSTURE_WINDOW_SECONDS} seconds.\n"
            f"System cooldown: {POSTURE_COOLDOWN_SECONDS} seconds between alerts per user.",
            parse_mode="Markdown"
        )
    else:
        msg = f"💺 *Posture Analysis - All Users*\n\n"
        
        for user_id in sorted(posture_user_alerts.keys()):
            alerts = posture_user_alerts[user_id]
            rec_alerts = posture_user_recommendation_alerts.get(user_id, [])
            
            msg += f"👤 *User {user_id}:*\n"
            
            # Count by levels
            level2_count = sum(1 for alert in alerts if "Medium" in alert or "Level 2" in alert)
            level3_count = sum(1 for alert in alerts if "High" in alert or "Level 3" in alert or "CRITICAL" in alert)
            
            if alerts:
                for alert in alerts[:2]:  # Show up to 2 alerts per user
                    clean_alert = escape_telegram_text(alert)
                    if "Medium" in clean_alert or "Level 2" in clean_alert:
                        msg += f"  • 📊 {clean_alert}\n"
                    else:
                        msg += f"  • ⚠️ {clean_alert}\n"
                
                msg += f"  📊 Total: {len(alerts)} ({level2_count} L2, {level3_count} L3+)\n"
                
                if level2_count > 0 and level3_count == 0:
                    msg += f"  💡 Level 2: Informational only\n"
            
            msg += "\n"
        
        msg += f"⏰ Detection window: {POSTURE_WINDOW_SECONDS}s | Cooldown: {POSTURE_COOLDOWN_SECONDS}s per user"
        await update.message.reply_text(msg, parse_mode="Markdown")

async def emotion_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /emotion_status command - Show only emotion status for ALL users
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    emotion_user_alerts, emotion_user_risk_types = check_emotion_alerts_all_users()
    
    if not emotion_user_alerts:
        await update.message.reply_text(
            f"🧠 *Emotion Status (All Users):* Stable\n"
            f"No emotional disturbances detected in the last {EMOTION_WINDOW_SECONDS} seconds.\n"
            f"System cooldown: {EMOTION_COOLDOWN_SECONDS} seconds between alerts per user.",
            parse_mode="Markdown"
        )
    else:
        msg = f"🧠 *Emotional Analysis - All Users*\n\n"
        
        for user_id in sorted(emotion_user_alerts.keys()):
            alerts = emotion_user_alerts[user_id]
            risk_type = emotion_user_risk_types.get(user_id, "general_posture")
            
            msg += f"👤 *User {user_id}:*\n"
            
            for alert in alerts[:2]:  # Show up to 2 alerts per user
                clean_alert = escape_telegram_text(alert)
                msg += f"  • {clean_alert}\n"
            
            msg += f"  🎯 Risk type: {risk_type}\n\n"
        
        msg += f"⏰ Detection window: {EMOTION_WINDOW_SECONDS}s | Cooldown: {EMOTION_COOLDOWN_SECONDS}s per user"
        await update.message.reply_text(msg, parse_mode="Markdown")

async def recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /recommendation command - Manual recommendation request for specific user
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    # Parse user_id from command if provided, otherwise use all users
    if context.args:
        try:
            target_user_id = int(context.args[0])
            # Check posture and emotion alerts for specific user
            posture_user_alerts, posture_user_recommendation_alerts, posture_user_risk_types = check_posture_alerts_all_users()
            emotion_user_alerts, emotion_user_risk_types = check_emotion_alerts_all_users()
            
            user_id_str = str(target_user_id)
            posture_alerts = posture_user_alerts.get(user_id_str, [])
            posture_recommendation_alerts = posture_user_recommendation_alerts.get(user_id_str, [])
            posture_risk = posture_user_risk_types.get(user_id_str, "general_posture")
            emotion_alerts = emotion_user_alerts.get(user_id_str, [])
            emotion_risk = emotion_user_risk_types.get(user_id_str, "general_posture")
            
        except ValueError:
            await update.message.reply_text(
                "❌ *Usage:* /recommendation [user_id]\nExample: /recommendation 1",
                parse_mode="Markdown"
            )
            return
    else:
        # If no user specified, check all users
        await update.message.reply_text(
            "ℹ️ *Usage:* /recommendation [user_id]\nSpecify the user ID.\nExample: /recommendation 1",
            parse_mode="Markdown"
        )
        return
    
    # For posture recommendations, use only level 3+ alerts
    all_alerts = posture_recommendation_alerts + emotion_alerts
    
    if not all_alerts:
        # Check if there are level 2 alerts to inform the user
        if posture_alerts and len(posture_recommendation_alerts) == 0:
            await update.message.reply_text(
                f"📊 *Posture Status (User {target_user_id}):* Level 2 detected\n"
                f"Posture issues at Level 2 are informational only.\n"
                f"Recommendations are generated for Level 3+ risks.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"💚 *Current Status (User {target_user_id}):* No interventions needed\n"
                f"No significant risks detected for this user.",
                parse_mode="Markdown"
            )
        return
    
    chat_id = update.message.chat_id
    
    # Check appropriate cooldowns
    if posture_recommendation_alerts and is_posture_cooldown_active(chat_id, target_user_id):
        await update.message.reply_text(
            f"⏳ *Posture system cooldown active for User {target_user_id}*\n"
            f"Please wait {POSTURE_COOLDOWN_SECONDS} seconds between posture interventions.\n"
            f"Use /posture_status for current status.",
            parse_mode="Markdown"
        )
        return
    
    if emotion_alerts and is_emotion_cooldown_active(chat_id, target_user_id):
        await update.message.reply_text(
            f"⏳ *Emotion system cooldown active for User {target_user_id}*\n"
            f"Please wait {EMOTION_COOLDOWN_SECONDS} seconds between emotion interventions.\n"
            f"Use /emotion_status for current status.",
            parse_mode="Markdown"
        )
        return
    
    # Generate recommendation based on most critical risk
    if posture_recommendation_alerts and emotion_alerts:
        # Prioritize critical posture over everything
        if "critical_posture" in posture_risk:
            recommendation, message = get_posture_recommendation(posture_recommendation_alerts, posture_risk, target_user_id)
        else:
            # If both present, use system with more alerts
            if len(posture_recommendation_alerts) >= len(emotion_alerts):
                recommendation, message = get_posture_recommendation(posture_recommendation_alerts, posture_risk, target_user_id)
            else:
                recommendation, message = get_emotion_recommendation(emotion_alerts, emotion_risk, target_user_id)
    elif posture_recommendation_alerts:
        recommendation, message = get_posture_recommendation(posture_recommendation_alerts, posture_risk, target_user_id)
    else:
        recommendation, message = get_emotion_recommendation(emotion_alerts, emotion_risk, target_user_id)
    
    if recommendation and message:
        keyboard = recommendation_system.create_recommendation_keyboard(recommendation['id'])
        await update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        # Update cooldowns based on type
        if posture_recommendation_alerts:
            update_posture_cooldown(chat_id, target_user_id)
        if emotion_alerts:
            update_emotion_cooldown(chat_id, target_user_id)
    else:
        msg = f"*Detected Issues for User {target_user_id}:*\n\n"
        for alert in all_alerts[:3]:
            clean_alert = escape_telegram_text(alert)
            msg += f"• {clean_alert}\n"
        msg += f"\n⚠️ *Unable to generate recommendation at this time.*"
        await update.message.reply_text(msg, parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /stats command - Show statistics for specific user or all users
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    if context.args:
        try:
            target_user_id = int(context.args[0])
            user_stats = get_user_response_stats(target_user_id, days=30)
            total_responses = sum(user_stats.values())
            
            if total_responses == 0:
                await update.message.reply_text(f"📊 No statistics available for User {target_user_id} yet.", parse_mode="Markdown")
                return
            
            acceptance_rate = (user_stats.get('accept', 0) / total_responses) * 100
            
            message = f"""
*User {target_user_id} Statistics (30 Days)*
✅ Accepted: {user_stats.get('accept', 0)}
⏸️ Postponed: {user_stats.get('postpone', 0)}
❌ Rejected: {user_stats.get('reject', 0)}
📈 Acceptance rate: {acceptance_rate:.1f}%
"""
            await update.message.reply_text(message, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text(
                "❌ *Usage:* /stats [user_id]\nExample: /stats 1",
                parse_mode="Markdown"
            )
    else:
        # Show summary for all users
        message = "📊 *Statistics Summary*\n\n"
        message += "*Usage:* /stats [user_id]\n"
        message += "Example: /stats 1\n\n"
        message += "To see specific user statistics."
        await update.message.reply_text(message, parse_mode="Markdown")

# ================================
# RESPONSE HANDLER - MODIFIED FOR MULTI-USER
# ================================

async def handle_recommendation_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle user responses to recommendations (accept/postpone/reject)
    
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    parts = callback_data.split('_')
    if len(parts) < 2: 
        return
        
    action = parts[0]
    recommendation_id = '_'.join(parts[1:])
    
    # Extract user_id (triggered_user_id) from recommendation_id
    # Format: rec_<user_id>_<timestamp>_<random>
    user_id = 1  # Default value
    try:
        rec_parts = recommendation_id.split('_')
        if len(rec_parts) >= 2:
            user_id = int(rec_parts[1])  # Second element is user_id
    except:
        user_id = 1  # Default to user 1
    
    if action in ['accept', 'postpone', 'reject']:
        db_result = insert_recommendation_response(
            recommendation_id=recommendation_id,
            user_id=user_id,  # ID of user who triggered the alert
            response=action
        )
        
        if db_result:
            response_texts = {
                'accept': '✅ Recommendation accepted',
                'postpone': '⏸️ Recommendation postponed', 
                'reject': '❌ Recommendation declined'
            }
            
            # Get original message text
            original_text = query.message.text
            
            # Add response confirmation
            response_text = f"\n\n👤 *User {user_id}*\n{response_texts[action]}"
            
            # Escape the original text
            escaped_text = escape_telegram_text(original_text)
            new_text = escaped_text + response_text
            
            await query.edit_message_text(
                text=new_text,
                parse_mode="Markdown",
                reply_markup=None
            )

    elif action == 'info':
        await query.edit_message_text("ℹ️ Information: These interventions help maintain physical and emotional well-being.")

# ================================
# PERIODIC TASKS - INDEPENDENT SYSTEMS FOR ALL USERS
# ================================

async def send_posture_alerts(context: ContextTypes.DEFAULT_TYPE):
    """
    Send posture alerts independently - Level 2 (info) and Level 3+ (with recommendation) for ALL users
    
    Args:
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    global running
    if not running:
        return
    
    print(f"\n[POSTURE] Cycle for ALL users - {datetime.now().strftime('%H:%M:%S')} - Checking all levels...")
    
    recipients = list(CHAT_IDS)
    
    if not recipients:
        return

    # 1. Check for posture alerts for ALL users
    user_alerts, user_recommendation_alerts, user_risk_types = check_posture_alerts_all_users()
    
    # If no alerts of any type, exit
    if not user_alerts:
        print(f"[POSTURE] No posture alerts for any user")
        return
    
    # 2. For each user, process their alerts
    for user_id_str, posture_alerts in user_alerts.items():
        user_id = int(user_id_str)
        posture_recommendation_alerts = user_recommendation_alerts.get(user_id_str, [])
        risk_type = user_risk_types.get(user_id_str, "general_posture")
        
        # If there are level 3+ alerts, send recommendation (high priority)
        if posture_recommendation_alerts:
            print(f"[POSTURE] Level 3+ alerts for User {user_id}: {len(posture_recommendation_alerts)} (type: {risk_type})")
            
            # Generate recommendation for this user
            recommendation, message = get_posture_recommendation(posture_recommendation_alerts, risk_type, user_id)
            
            if recommendation and message:
                keyboard = recommendation_system.create_recommendation_keyboard(recommendation['id'])
                
                for chat_id in recipients:
                    if is_posture_cooldown_active(chat_id, user_id):
                        print(f"[POSTURE] Skipping Level 3+ alert for User {user_id} due to cooldown (chat ID: {chat_id})")
                        continue
                    
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )
                        print(f"[POSTURE] Level 3+ alert with recommendation for User {user_id} sent to chat ID: {chat_id}")
                        update_posture_cooldown(chat_id, user_id)
                    except BadRequest as e:
                        print(f"[POSTURE] Parse error for Level 3+ alert (User {user_id}, chat ID {chat_id}): {e}")
                    except Exception as e:
                        print(f"[POSTURE] Error sending Level 3+ alert for User {user_id} to chat ID {chat_id}: {e}")
        
        # 3. If no level 3+ alerts, but level 2 alerts exist, send informational message
        elif posture_alerts:
            # Filter only level 2 alerts
            level2_alerts = [alert for alert in posture_alerts if "Medium" in alert or "Level 2" in alert]
            
            if level2_alerts:
                print(f"[POSTURE] Level 2 alerts for User {user_id}: {len(level2_alerts)}")
                
                # Create informational message for level 2
                message = create_level2_alert_message(posture_alerts, user_id)
                
                if message:
                    for chat_id in recipients:
                        if is_posture_level2_cooldown_active(chat_id, user_id):
                            print(f"[POSTURE] Skipping Level 2 alert for User {user_id} due to cooldown (chat ID: {chat_id})")
                            continue
                        
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode="Markdown"
                            )
                            print(f"[POSTURE] Level 2 informational alert for User {user_id} sent to chat ID: {chat_id}")
                            update_posture_level2_cooldown(chat_id, user_id)
                        except BadRequest as e:
                            print(f"[POSTURE] Parse error for Level 2 alert (User {user_id}, chat ID {chat_id}): {e}")
                        except Exception as e:
                            print(f"[POSTURE] Error sending Level 2 alert for User {user_id} to chat ID {chat_id}: {e}")

async def send_emotion_alerts(context: ContextTypes.DEFAULT_TYPE):
    """
    Send emotion alerts independently for ALL users
    
    Args:
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    global running
    if not running:
        return
    
    print(f"\n[EMOTION] Cycle for ALL users - {datetime.now().strftime('%H:%M:%S')}")
    
    recipients = list(CHAT_IDS)
    
    if not recipients:
        return

    # 1. Check for emotion alerts for ALL users
    user_alerts, user_risk_types = check_emotion_alerts_all_users()
    
    if not user_alerts:
        print(f"[EMOTION] No emotion alerts for any user")
        return
        
    # 2. For each user, process their alerts
    for user_id_str, emotion_alerts in user_alerts.items():
        user_id = int(user_id_str)
        risk_type = user_risk_types.get(user_id_str, "general_posture")
        
        print(f"[EMOTION] Alerts for User {user_id}: {len(emotion_alerts)} (type: {risk_type})")
        
        # Generate recommendation for this user
        recommendation, message = get_emotion_recommendation(emotion_alerts, risk_type, user_id)
        
        if not recommendation or not message:
            print(f"[EMOTION] Could not generate recommendation for User {user_id}")
            continue
        
        # Send to subscribers with independent cooldown
        keyboard = recommendation_system.create_recommendation_keyboard(recommendation['id'])
        
        for chat_id in recipients:
            if is_emotion_cooldown_active(chat_id, user_id):
                print(f"[EMOTION] Skipping alert for User {user_id} due to cooldown (chat ID: {chat_id})")
                continue
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                print(f"[EMOTION] Alert for User {user_id} sent to chat ID: {chat_id}")
                update_emotion_cooldown(chat_id, user_id)
                    
            except BadRequest as e:
                print(f"[EMOTION] Parse error for chat ID {chat_id}: {e}")
            except Exception as e:
                print(f"[EMOTION] Error sending to chat ID {chat_id}: {e}")

# ================================
# MAIN - INDEPENDENT SYSTEMS FOR ALL USERS
# ================================

def main():
    """
    Main function to start the Telegram bot with independent monitoring systems for all users
    """
    global running
    
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN environment variable is required")
        return
    
    print("=" * 70)
    print("PAWSture Health Monitor - Multi-User System (v4)")
    print("=" * 70)
    print(f"Monitoring: ALL USERS")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")
    print(f"Posture: {POSTURE_WINDOW_SECONDS}s window, {POSTURE_COOLDOWN_SECONDS}s cooldown")
    print(f"Emotions: {EMOTION_WINDOW_SECONDS}s window, {EMOTION_COOLDOWN_SECONDS}s cooldown")
    print("\nIMPORTANT: Monitoring ALL USERS")
    print("IMPORTANT: Automatic alerts for ALL USERS")
    print("  • Level 2: Informational alerts (no recommendation)")
    print("  • Level 3+: Alerts with recommendations")
    print("  • All messages include user ID")
    print("  • Responses saved with triggered user ID")
    print("\nIndependent monitoring systems for ALL users")
    print("  • Separate cooldowns per user")
    print("  • Individual alert channels per user")
    print("  • Custom messaging per user")
    print("\nAI Recommendation System")
    print(f"  • Trained: {recommendation_system.is_model_ready}")
    print("  • Learns from historical responses per user")
    print("  • Uses rules when insufficient data")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)
    
    try:
        from telegram.request import HTTPXRequest
        request = HTTPXRequest(
            connect_timeout=10.0,
            read_timeout=10.0,
            write_timeout=10.0,
        )
        
        app = ApplicationBuilder() \
            .token(BOT_TOKEN) \
            .request(request) \
            .build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("status", status))
        app.add_handler(CommandHandler("recommendation", recommendation))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("posture_status", posture_status))
        app.add_handler(CommandHandler("emotion_status", emotion_status))
        app.add_handler(CommandHandler("config", config_cmd))
        app.add_handler(CommandHandler("model_status", model_status))
        app.add_handler(CallbackQueryHandler(handle_recommendation_response))
        
        # Independent periodic checks
        app.job_queue.run_repeating(send_posture_alerts, interval=CHECK_INTERVAL_SECONDS, first=5)
        app.job_queue.run_repeating(send_emotion_alerts, interval=CHECK_INTERVAL_SECONDS, first=7)
        
        print("System configured. Starting polling...")
        print("Use /start in Telegram to subscribe")
        print("Use /model_status for AI system details")
        print("\nMonitoring ALL users systems active")
        print(f"  • Posture: every {CHECK_INTERVAL_SECONDS}s, {POSTURE_COOLDOWN_SECONDS}s cooldown per user")
        print(f"    - Level 2: Informational alerts")
        print(f"    - Level 3+: Alerts with recommendations")
        print(f"  • Emotions: every {CHECK_INTERVAL_SECONDS}s, {EMOTION_COOLDOWN_SECONDS}s cooldown per user")
        
        app.run_polling()
        
    except KeyboardInterrupt:
        print("\nKeyboard interrupt detected.")
        running = False
        print("Exiting program...")
        sys.exit(0)
    except Exception as e:
        print(f"Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()