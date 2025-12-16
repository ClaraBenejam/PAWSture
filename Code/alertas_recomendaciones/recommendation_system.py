# recommendation_system.py
"""
Main recommendation system that combines medical filtering with AI personalization
Integrates with health monitoring for proactive alerts
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import random
import requests
import re
import torch
import numpy as np
import torch.nn.functional as F

# New imports
from cloud_db import insert_recommendation
from supabase import create_client, Client
from data_loader import DataLoader
from ml_model import P3FitRecModel
from health_monitor import HealthMonitor  # NEW IMPORT


class RecommendationSystem:
    def __init__(self, db_path: Path):
        """
        Initialize the recommendation system
        
        Args:
            db_path: Path to database directory
        """
        self.db_path = db_path
        self.min_interval_minutes = 1

        # Load credentials
        self.supabase_url, self.supabase_key = self._load_supabase_credentials()
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

        # === MASTER ACTIVITY CATALOG (MEDICAL FILTER) ===
        self.ACTIVITY_CATALOG = {
            # --- EMOTIONAL HEALTH ---
            "stress_high": [
                {"name": "4-7-8 Breathing", "type": "breathing", "duration": "2 min",
                 "description": "Relaxation technique", "steps": ["Inhale 4s", "Hold 7s", "Exhale 8s"]},
                {"name": "Diaphragmatic Breathing", "type": "breathing", "duration": "3 min",
                 "description": "Deep calm", "steps": ["Hand on abdomen", "Deep inhale", "Feel expansion"]},
                {"name": "Guided Visualization", "type": "breathing", "duration": "3 min",
                 "description": "Mental escape", "steps": ["Close eyes", "Imagine safe place", "Breathe slowly"]}
            ],
            "negative_emotion": [
                {"name": "Mindful Coffee Break", "type": "active_break", "duration": "5 min",
                 "description": "Change of scenery", "steps": ["Go to kitchen", "Enjoy aroma", "Breathe"]},
                {"name": "Brisk Walk", "type": "active_break", "duration": "5 min",
                 "description": "Activate endorphins", "steps": ["Stand up", "Walk briskly", "Look out window"]},
                {"name": "Power Stretching", "type": "active_break", "duration": "2 min",
                 "description": "Confidence posture", "steps": ["Arms in V above", "Deep breath", "Force smile"]}
            ],

            # --- POSTURAL HEALTH ---
            "neck_flexion": [
                {"name": "Cervical Retraction", "type": "posture_correction", "duration": "2 min",
                 "description": "Corrects forward neck", "steps": ["Chin back (double chin)", "Align ears with shoulders", "Hold 5s"]},
                {"name": "Lateral Stretch", "type": "posture_correction", "duration": "2 min",
                 "description": "Trapezius relief", "steps": ["Ear to shoulder", "Hand gently assists", "30s each side"]}
            ],
            "shoulder_alignment": [
                {"name": "Shoulder Rotation", "type": "posture_correction", "duration": "1 min",
                 "description": "Release tension", "steps": ["Shoulders up", "Back and down", "Repeat 10 times"]},
                {"name": "Chest Opening", "type": "posture_correction", "duration": "2 min",
                 "description": "Counteract hunching", "steps": ["Hands behind back", "Interlace fingers", "Stretch arms"]}
            ],
            "critical_posture": [
                {"name": "FULL RESET", "type": "urgent_break", "duration": "5 min",
                 "description": "Urgent Intervention", "steps": ["Stand up NOW", "Walk", "Drink water", "Readjust chair"]},
                {"name": "Spinal Stretch", "type": "urgent_break", "duration": "3 min",
                 "description": "Decompression", "steps": ["Standing", "Touch toes", "Roll up vertebra by vertebra"]}
            ],
            "general_posture": [
                {"name": "Ergonomic Check", "type": "posture_correction", "duration": "1 min",
                 "description": "Quick check", "steps": ["Feet flat", "Knees 90º", "Screen at eye level"]},
                {"name": "Torso Rotation", "type": "active_break", "duration": "2 min",
                 "description": "Lumbar mobility", "steps": ["Rotate torso right", "Grab chair back", "Switch sides"]}
            ]
        }

        # Flatten list for ML mapping
        self.all_activities = [act for sublist in self.ACTIVITY_CATALOG.values() for act in sublist]
        self.activity_names = list(set(a['name'] for a in self.all_activities))

        # === AI BRAIN ===
        self.model = None
        self.data_loader = DataLoader(self.supabase, self.activity_names)
        self.is_model_ready = False

        # === HEALTH MONITOR === (NEW COMPONENT)
        self.health_monitor = HealthMonitor()
        
        # Train at startup
        self.train_brain()

    def _load_supabase_credentials(self):
        """
        Load Supabase credentials from environment or file
        
        Returns:
            tuple: (url, key) or (None, None) if not found
        """
        # 1) Prefer .env / environment
        import os
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if url and key:
            return url.strip(), key.strip()

        # 2) Fallback: try to read from file
        try:
            cloud_db_path = Path(__file__).parent / "cloud_db.py"
            txt = cloud_db_path.read_text(encoding="utf-8")
            m_url = re.search(r"SUPABASE_URL\s*=\s*[\"'](.+?)[\"']", txt)
            m_key = re.search(r"SUPABASE_KEY\s*=\s*[\"'](.+?)[\"']", txt)
            if m_url and m_key:
                return m_url.group(1).strip(), m_key.group(1).strip()
        except Exception:
            pass

        return None, None

    def train_brain(self):
        """
        Downloads data and trains the model (3 classes: reject/postpone/accept).
        """
        print("Starting brain training...")
        df = self.data_loader.fetch_data()

        if df is None or len(df) < 5:
            print("Insufficient data for AI. Rules Mode (Cold Start).")
            self.is_model_ready = False
            return

        try:
            # 1) Build tensor + maps
            tensor = self.data_loader.build_tensor(df)
            n_users = len(self.data_loader.user_map)
            n_ctx = len(self.data_loader.context_map)
            n_act = len(self.data_loader.activity_map)

            print(f"Tensor dimensions: {n_users} users, {n_ctx} contexts, {n_act} activities")
            
            # 2) Initialize model + embeddings with tensor decomposition
            self.model = P3FitRecModel(n_users, n_ctx, n_act)
            self.model.initialize_with_tensor_decomposition(tensor)

            # 3) Prepare training samples
            samples = self.data_loader.build_training_samples(df)
            if not samples:
                print("No valid samples to train AI (activities without name).")
                self.is_model_ready = True
                return

            # 4) 3-class training with CrossEntropy
            optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
            epochs = 6
            batch_size = 32

            self.model.train()

            for epoch in range(epochs):
                random.shuffle(samples)
                total_loss = 0.0

                for i in range(0, len(samples), batch_size):
                    batch = samples[i:i + batch_size]

                    user_idx = torch.tensor([s[0] for s in batch], dtype=torch.long)
                    ctx_idx  = torch.tensor([s[1] for s in batch], dtype=torch.long)
                    act_idx  = torch.tensor([s[2] for s in batch], dtype=torch.long)
                    labels   = torch.tensor([s[3] for s in batch], dtype=torch.long)

                    logits = self.model(user_idx, ctx_idx)

                    batch_range = torch.arange(len(batch))
                    picked_logits = logits[batch_range, act_idx, :]

                    loss = F.cross_entropy(picked_logits, labels)

                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                    total_loss += loss.item() * len(batch)

                avg_loss = total_loss / len(samples)
                print(f"   Epoch {epoch + 1}: loss={avg_loss:.4f}")

            self.model.eval()
            self.is_model_ready = True
            print(f"Brain trained ({n_users} users, {len(df)} interactions).")

        except Exception as e:
            print(f"Error training model: {e}")
            self.is_model_ready = False

    def get_context_idx(self):
        """
        Get current context index based on time of day
        
        Returns:
            int: 0 for morning, 1 for afternoon, 2 for evening
        """
        h = datetime.now().hour
        if h < 12:
            return 0  # morning
        elif h < 18:
            return 1  # afternoon
        return 2  # evening

    def check_chronic_health_risks(self):
        """
        Run proactive health checks for chronic risks.
        Returns alerts for Telegram delivery.
        
        Returns:
            dict: {user_id: [alert_messages]}
        """
        print("🔍 Running proactive health checks...")
        return self.health_monitor.run_daily_checks()

    def generate_recommendation(self, user_id=None, risk_type="general_posture"):
        """
        Generates recommendation using Medical Filter + Personalized AI.
        
        Args:
            user_id: User ID (optional)
            risk_type: Type of risk detected
            
        Returns:
            dict: Recommendation data
        """
        # 1. FILTER: Get valid candidates for the risk
        candidates = self.ACTIVITY_CATALOG.get(risk_type)
        if not candidates:
            candidates = self.ACTIVITY_CATALOG.get("general_posture")

        selected_activity = None
        source = "RULES"
        user_str = str(user_id) if user_id else "1"

        # 2. AI P3FitRec: Personalized ranking (3 classes)
        if self.is_model_ready and user_str in self.data_loader.user_map:
            try:
                source = "AI-P3FitRec"
                u_idx = self.data_loader.user_map[user_str]
                c_idx = self.get_context_idx()

                with torch.no_grad():
                    u_tensor = torch.tensor([u_idx], dtype=torch.long)
                    c_tensor = torch.tensor([c_idx], dtype=torch.long)
                    logits_all = self.model(u_tensor, c_tensor)[0]

                # Reward values for each class: reject=-1, postpone=0.1, accept=1
                R = torch.tensor([-1.0, 0.1, 1.0], dtype=torch.float32)

                best_score = -1e9

                for activity in candidates:
                    act_name = activity['name']
                    if act_name in self.data_loader.activity_map:
                        global_idx = self.data_loader.activity_map[act_name]

                        probs = torch.softmax(logits_all[global_idx], dim=-1)
                        score = float((probs * R).sum().item())

                        if score > best_score:
                            best_score = score
                            selected_activity = activity

            except Exception as e:
                print(f"AI inference error: {e}")

        # 3. FALLBACK: Random selection (Cold Start)
        if not selected_activity:
            source = "COLD-START"
            selected_activity = random.choice(candidates)

        # 4. Build final object
        emoji = "🧘" if selected_activity['type'] == "breathing" else "🤸"
        if risk_type == "critical_posture":
            emoji = "🚨"

        rec_id = f"rec_{user_str}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}"

        recommendation = {
            "id": rec_id,
            "recommendation_type": selected_activity['type'],
            "name": selected_activity['name'],
            "description": selected_activity['description'],
            "duration": selected_activity['duration'],
            "steps": selected_activity['steps'],
            "reason": f"Suggested by {source} (Risk: {risk_type})",
            "urgency": "high" if "critical" in risk_type else "medium",
            "emoji": emoji,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Save to database to close the learning loop
        try:
            insert_recommendation(recommendation)
        except Exception:
            pass

        print(f"Recommendation for User {user_str}: {selected_activity['name']} ({source})")
        return recommendation

    def format_telegram_message(self, recommendation):
        """
        Format recommendation for Telegram display
        
        Args:
            recommendation: Recommendation dictionary
            
        Returns:
            str: Formatted Telegram message
        """
        emoji = recommendation.get('emoji', '💡')
        title = recommendation['name'].upper()

        msg = f"{emoji} *{title}*\n"
        msg += f"_{recommendation['description']}_\n\n"
        msg += f"⏱️ *Duration:* {recommendation['duration']}\n\n"
        msg += "*📝 Steps to follow:*\n"

        steps = recommendation['steps']
        for i, s in enumerate(steps, 1):
            msg += f"{i}. {s}\n"

        return msg

    def create_recommendation_keyboard(self, recommendation_id):
        """
        Create inline keyboard for recommendation responses
        
        Args:
            recommendation_id: Unique recommendation ID
            
        Returns:
            InlineKeyboardMarkup: Telegram inline keyboard
        """
        # 3-class keyboard: accept/postpone/reject
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        k = [[
            InlineKeyboardButton("✅ Accept", callback_data=f"accept_{recommendation_id}"),
            InlineKeyboardButton("⏸️ Postpone", callback_data=f"postpone_{recommendation_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"reject_{recommendation_id}")
        ]]
        return InlineKeyboardMarkup(k)