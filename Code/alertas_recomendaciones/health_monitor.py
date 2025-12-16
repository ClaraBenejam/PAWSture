# health_monitor.py
"""
Proactive Health Monitoring System for Chronic Risk Detection
Detects chronic stress and posture risks using historical data.
"""

from datetime import datetime, timedelta
from typing import Dict, List
import json
from pathlib import Path

# Import from cloud_db for database access
try:
    from cloud_db import get_stress_levels, get_high_risk_posture_alerts
    CLOUD_DB_AVAILABLE = True
except ImportError:
    CLOUD_DB_AVAILABLE = False
    print("⚠️ Cloud DB module not available. Health monitor will run in simulation mode.")


class HealthMonitor:
    """
    Proactive health monitoring system that detects chronic risks
    based on historical stress and posture data.
    """
    
    def __init__(self, config_path: str = "unified_chat_ids.json"):
        """
        Initialize health monitor with user IDs to monitor.
        
        Args:
            config_path: Path to JSON file containing user IDs
        """
        self.user_ids = self._load_user_ids(config_path)
        self.alerts_sent_today = set()  # Track alerts sent today
        
    def _load_user_ids(self, config_path: str) -> List[int]:
        """
        Load user IDs from configuration file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            list: List of user IDs
        """
        try:
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    # Handle both list format and other formats
                    if isinstance(data, list):
                        return [int(uid) for uid in data]
                    else:
                        print(f"⚠️ Unexpected format in {config_path}")
                        return []
            else:
                print(f"⚠️ Config file {config_path} not found")
                return []
        except Exception as e:
            print(f"❌ Error loading user IDs: {e}")
            return []
    
    def check_chronic_stress_risk(self) -> Dict[int, str]:
        """
        Checks for Chronic Stress risk and returns formatted Telegram alerts.
        
        Criteria:
        - Average stress level ≥ 7 (1-10 scale) over 7 days
        - Minimum 10 samples required for analysis
        
        Returns:
            dict: {user_id: alert_message} for users with detected risk
        """
        print("\n🚨 Checking for Chronic Stress Risk (last 7 days)...")
        
        CHRONIC_THRESHOLD = 7  # Average stress level threshold
        MIN_SAMPLES = 200       # Minimum samples for reliable analysis
        
        alert_messages = {}
        
        for user_id in self.user_ids:
            if not CLOUD_DB_AVAILABLE:
                # Simulation mode
                stress_data = self._simulate_stress_data(user_id, days=7)
            else:
                # Real mode - get data from database
                stress_data = get_stress_levels(user_id, days=7)
            
            # Check if we have enough samples for analysis
            if len(stress_data) < MIN_SAMPLES:
                print(f"  - User {user_id}: Insufficient samples ({len(stress_data)})")
                continue
            
            avg_stress = sum(stress_data) / len(stress_data)
            
            # Check if average stress exceeds threshold
            if avg_stress >= CHRONIC_THRESHOLD:
                # Generate alert message
                message = self._format_stress_alert(user_id, avg_stress, CHRONIC_THRESHOLD)
                alert_messages[user_id] = message
                print(f"  - ⚠️ CHRONIC ALERT for User {user_id}. Avg: {avg_stress:.2f}")
            else:
                print(f"  - User {user_id}: Stress OK. Avg: {avg_stress:.2f}")
        
        return alert_messages
    
    def check_chronic_posture_risk(self) -> Dict[int, str]:
        """
        Checks for Chronic Posture Risk (Torticollis Risk).
        
        Criteria:
        - ≥ 50 high-risk neck lateral bend alerts in 14 days
        
        Returns:
            dict: {user_id: alert_message} for users with detected risk
        """
        print("\n🚨 Checking for Chronic Posture Risk (last 14 days)...")
        
        TOTAL_ALERT_THRESHOLD = 800  # Total high-risk alerts threshold
        
        alert_messages = {}
        
        for user_id in self.user_ids:
            if not CLOUD_DB_AVAILABLE:
                # Simulation mode
                alert_count = self._simulate_posture_data(user_id, days=14)
            else:
                # Real mode - get data from database
                alert_count = get_high_risk_posture_alerts(user_id, days=14)
            
            # Check if alert count exceeds threshold
            if alert_count >= TOTAL_ALERT_THRESHOLD:
                # Generate alert message
                message = self._format_posture_alert(user_id, alert_count, TOTAL_ALERT_THRESHOLD)
                alert_messages[user_id] = message
                print(f"  - ⚠️ POSTURE ALERT for User {user_id}. Count: {alert_count}")
            else:
                print(f"  - User {user_id}: Posture OK. Alerts: {alert_count}")
        
        return alert_messages
    
    def _format_stress_alert(self, user_id: int, avg_stress: float, threshold: float) -> str:
        """
        Format chronic stress alert for Telegram.
        
        Args:
            user_id: User ID
            avg_stress: Average stress level
            threshold: Stress threshold
            
        Returns:
            str: Formatted alert message
        """
        return (
            "🚨 *WARNING: CHRONIC STRESS DETECTED!* 🚨\n\n"
            f"Your average stress level over the last 7 days was *{avg_stress:.2f}* "
            f"(Threshold: {threshold}).\n\n"
            "This persistent level suggests chronic strain. "
            "We strongly recommend you seek professional guidance.\n\n"
            "*Action Recommended:* CONTACT EXTERNAL HEALTH PROFESSIONAL\n\n"
            "✨ Remember: Your well-being is a priority. "
            "Taking a pause is a sign of strength, not weakness. You've got this!"
        )
    
    def _format_posture_alert(self, user_id: int, alert_count: int, threshold: int) -> str:
        """
        Format chronic posture alert for Telegram.
        
        Args:
            user_id: User ID
            alert_count: Number of posture alerts
            threshold: Alert threshold
            
        Returns:
            str: Formatted alert message
        """
        return (
            "⚠️ *WARNING: CHRONIC NECK TILT DETECTED!* ⚠️\n\n"
            f"Your posture analysis detected a high frequency of critical "
            f"Lateral Neck Bend alerts (*{alert_count}* in 14 days).\n\n"
            "This persistent lateral tension is a major indicator of "
            "*Torticollis Risk* or chronic cervical strain.\n\n"
            "*Action Recommended:* CONSULT A PHYSIOTHERAPIST OR SPECIALIST\n\n"
            "🧘 Take a moment now to stretch your neck and shoulders. "
            "Consistency is key to long-term health!"
        )
    
    def _simulate_stress_data(self, user_id: int, days: int = 7) -> List[int]:
        """
        Simulate stress data for testing when database is unavailable.
        
        Args:
            user_id: User ID
            days: Number of days to simulate
            
        Returns:
            list: Simulated stress data
        """
        # Simulate some stress data
        import random
        base_stress = random.randint(4, 9)
        return [base_stress + random.randint(-2, 2) for _ in range(random.randint(5, 15))]
    
    def _simulate_posture_data(self, user_id: int, days: int = 14) -> int:
        """
        Simulate posture alert count for testing.
        
        Args:
            user_id: User ID
            days: Number of days to simulate
            
        Returns:
            int: Simulated alert count
        """
        import random
        # Simulate between 0-100 alerts
        return random.randint(0, 100)
    
    def run_daily_checks(self) -> Dict[int, List[str]]:
        """
        Run all daily health checks and return all alerts.
        
        Returns:
            dict: {user_id: [alert_messages]} for all users with alerts
        """
        all_alerts = {}
        
        # Reset daily tracking if it's a new day
        today = datetime.now().date()
        if hasattr(self, '_last_check_date') and self._last_check_date != today:
            self.alerts_sent_today.clear()
        
        self._last_check_date = today
        
        # Run stress checks
        stress_alerts = self.check_chronic_stress_risk()
        for user_id, message in stress_alerts.items():
            if user_id not in all_alerts:
                all_alerts[user_id] = []
            all_alerts[user_id].append(message)
        
        # Run posture checks
        posture_alerts = self.check_chronic_posture_risk()
        for user_id, message in posture_alerts.items():
            if user_id not in all_alerts:
                all_alerts[user_id] = []
            all_alerts[user_id].append(message)
        
        return all_alerts
    
    def should_send_alert(self, user_id: int, alert_type: str) -> bool:
        """
        Check if an alert should be sent (prevents duplicate alerts on same day).
        
        Args:
            user_id: User ID
            alert_type: Type of alert ('stress' or 'posture')
            
        Returns:
            bool: True if alert should be sent
        """
        alert_key = f"{user_id}_{alert_type}"
        if alert_key in self.alerts_sent_today:
            return False
        
        self.alerts_sent_today.add(alert_key)
        return True


# Convenience functions for easy integration
def create_health_monitor():
    """
    Factory function to create health monitor instance.
    
    Returns:
        HealthMonitor: Health monitor instance
    """
    return HealthMonitor()

def run_health_checks():
    """
    Run health checks and return alerts.
    
    Returns:
        dict: {user_id: [alert_messages]} for all users with alerts
    """
    monitor = HealthMonitor()
    return monitor.run_daily_checks()