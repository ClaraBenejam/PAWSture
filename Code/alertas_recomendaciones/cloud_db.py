# cloud_db.py
"""
Cloud database operations for Supabase integration
Handles health data queries, response management, and gamification
"""
import os
import time
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv


# ==========================================
# SUPABASE CONFIGURATION
# ==========================================
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def get_supabase_client() -> Client:
    """
    Singleton to get Supabase client
    
    Returns:
        Client: Supabase client instance or None if error
    """
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Error connecting to Supabase: {e}")
        return None

supabase = get_supabase_client()

# ==========================================
# HEALTH DATA QUERIES (NEW FUNCTIONS)
# ==========================================

def get_stress_levels(person_id, days=7):
    """
    Retrieves stress levels for a specific user over the last 'days'.
    
    Args:
        person_id: User ID
        days: Number of days to look back
        
    Returns:
        list: List of integers (stress levels)
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    try:
        response = supabase.table("emotions")\
            .select("stress_level")\
            .eq("person_id", person_id)\
            .gte("created_at", cutoff_date)\
            .execute()
        
        data = response.data
        stress_levels = []
        for item in data:
            stress = item.get('stress_level')
            if stress is not None:
                try:
                    if isinstance(stress, str):
                        if stress.isdigit():
                            stress_levels.append(int(stress))
                    elif isinstance(stress, (int, float)):
                        stress_levels.append(int(stress))
                except Exception:
                    pass
        
        return stress_levels
        
    except Exception as e:
        print(f"❌ Error getting stress levels: {e}")
        return []

def get_high_risk_posture_alerts(person_id, days=14):
    """
    Retrieves the count of high-risk posture alerts (neck_lateral_bend_zone >= 3) over the last 'days'.
    
    Args:
        person_id: User ID
        days: Number of days to look back
        
    Returns:
        int: Count of high-risk posture alerts
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    try:
        response = supabase.table("posture")\
            .select("neck_lateral_bend_zone")\
            .eq("id_usuario", person_id)\
            .gte("timestamp", cutoff_date)\
            .gte("neck_lateral_bend_zone", 3)\
            .execute()
        
        return len(response.data)
        
    except Exception as e:
        print(f"❌ Error getting high-risk posture alerts: {e}")
        return 0

# ==========================================
# RESPONSE MANAGEMENT (FEEDBACK)
# ==========================================

def insert_recommendation_response(recommendation_id, user_id, response):
    """
    Records user action (accept/postpone/reject) towards a recommendation.
    
    Args:
        recommendation_id: Unique recommendation ID
        user_id: ID of the user whose measurements triggered the alert (triggered_user_id)
        response: User response ('accept', 'postpone', or 'reject')
        
    Returns:
        dict: Inserted data or None if error
    """
    try:
        username = f"user_{user_id}"
        
        data = {
            "recommendation_id": recommendation_id,
            "user_id": user_id,
            "username": username,
            "response": response,
            "created_at": datetime.now().isoformat()
        }
        
        result = supabase.table("recommendation_responses").insert(data).execute()

        # Update gamification points based on response
        try:
            _map = {"accept": 0.2, "postpone": 0.0, "reject": -0.2}
            delta = float(_map.get(response, 0.0))
            if delta != 0.0:
                add_points(user_id, delta, reason=f"response:{response}")
        except Exception as ee:
            print(f"⚠️ Error updating gamification points: {ee}")

        return result.data
        
    except Exception as e:
        print(f"⚠️ Error inserting response: {e}")
        return None

def get_recommendation_responses(recommendation_id):
    """
    Gets all responses associated with a specific recommendation.
    
    Args:
        recommendation_id: Recommendation ID
        
    Returns:
        list: List of response data
    """
    try:
        response = supabase.table("recommendation_responses")\
            .select("*")\
            .eq("recommendation_id", recommendation_id)\
            .execute()
        return response.data
    except Exception as e:
        print(f"⚠️ Error getting responses: {e}")
        return []

def get_user_response_stats(user_id, days=30):
    """
    Calculates acceptance statistics for a user in the last X days.
    Used by /stats and /posture_stats commands.
    
    Args:
        user_id: User ID
        days: Number of days to analyze
        
    Returns:
        dict: Statistics {'accept': count, 'postpone': count, 'reject': count}
    """
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        response = supabase.table("recommendation_responses")\
            .select("response")\
            .eq("user_id", user_id)\
            .gte("created_at", cutoff_date)\
            .execute()
            
        data = response.data
        
        stats = {
            'accept': 0,
            'postpone': 0,
            'reject': 0
        }
        
        for entry in data:
            resp_type = entry.get('response')
            if resp_type in stats:
                stats[resp_type] += 1
                
        return stats
        
    except Exception as e:
        print(f"⚠️ Error calculating statistics: {e}")
        return {'accept': 0, 'postpone': 0, 'reject': 0}

# ==========================================
# RECOMMENDATION MANAGEMENT (DATA LOADER)
# ==========================================

def insert_recommendation(recommendation_data):
    """
    Saves the recommendation generated by the system/AI to the database.
    Necessary so the Data Loader can later train with it.
    
    Args:
        recommendation_data: Recommendation data dictionary
        
    Returns:
        dict: Inserted data or None if error
    """
    try:
        payload = {
            "id": recommendation_data["id"],
            "recommendation_type": recommendation_data["recommendation_type"],
            "name": recommendation_data["name"],
            "description": recommendation_data["description"],
            "duration": recommendation_data["duration"],
            "reason": recommendation_data.get("reason", "Algorithm"),
            "urgency": recommendation_data.get("urgency", "medium"),
            "steps": recommendation_data["steps"],
            "emoji": recommendation_data.get("emoji", "💡"),
            "created_at": datetime.now().isoformat()
        }
        
        result = supabase.table("recommendations").insert(payload).execute()
        return result.data
        
    except Exception as e:
        print(f"⚠️ Error saving recommendation: {e}")
        return None

def get_recommendation_analytics():
    """
    Helper function for global analysis (optional)
    
    Returns:
        list: All recommendation responses
    """
    try:
        response = supabase.table("recommendation_responses").select("*").execute()
        return response.data
    except Exception:
        return []


# ==========================================
# GAMIFICATION (SIMPLE)
# ==========================================

def add_points(user_id, delta, reason=None):
    """
    Adds/subtracts points to the user in the `gamification` table.
    
    Args:
        user_id: User ID
        delta: Points to add (negative to subtract)
        reason: Reason for point change (optional)
        
    Returns:
        float: New point total or None if error
    """
    if supabase is None:
        print("⚠️ Supabase client not initialized. Cannot update points.")
        return None

    try:
        # Get current points
        res = supabase.table("gamification").select("*").eq("user_id", user_id).execute()
        rows = res.data if res and hasattr(res, 'data') else []

        if rows:
            current = rows[0]
            try:
                current_points = float(current.get("points", 0.0))
            except Exception:
                current_points = 0.0

            # Calculate new points (clamped between 0 and 10)
            new_points = current_points + float(delta)
            new_points = max(0.0, min(10.0, new_points))

            upd = {
                "points": new_points,
                "last_updated": datetime.now().isoformat()
            }
            supabase.table("gamification").update(upd).eq("user_id", user_id).execute()
            print(f"🔹 Gamification: user {user_id} points {current_points} -> {new_points} ({delta})")
            return new_points
        else:
            # Create new entry with starting points
            starting = 10.0
            payload = {
                "user_id": int(user_id),
                "points": float(starting),
                "last_updated": datetime.now().isoformat()
            }
            supabase.table("gamification").insert(payload).execute()
            print(f"🔹 Gamification: created user {user_id} with {starting} points (initial max).")
            
            # Apply delta if non-zero
            if float(delta) != 0.0:
                new_points = max(0.0, min(10.0, starting + float(delta)))
                supabase.table("gamification").update({"points": new_points, "last_updated": datetime.now().isoformat()}).eq("user_id", user_id).execute()
                print(f"🔹 Gamification: user {user_id} adjusted {starting} -> {new_points} ({delta})")
                return new_points
            return float(starting)

    except Exception as e:
        print(f"⚠️ Error accessing gamification table: {e}")
        print("If the table does not exist, create the 'gamification' table manually in Supabase SQL Editor.")
        return None


def get_gamification_leaderboard():
    """
    Gets the gamification leaderboard (Employee name + points).
    
    Returns:
        list: Sorted list of leaderboard entries
    """
    if supabase is None:
        print("⚠️ Supabase client not initialized.")
        return []

    try:
        # Get gamification data
        res_gamif = supabase.table("gamification").select("*").execute()
        gamif_rows = res_gamif.data if res_gamif and hasattr(res_gamif, 'data') else []

        if not gamif_rows:
            return []

        # Get employee names
        res_emp = supabase.table("Employees").select("id, Name").execute()
        emp_rows = res_emp.data if res_emp and hasattr(res_emp, 'data') else []

        # Create mapping of user_id to employee name
        emp_map = {emp.get("id"): emp.get("Name", "Unknown") for emp in emp_rows}

        # Build leaderboard
        leaderboard = []
        for gamif in gamif_rows:
            user_id = gamif.get("user_id")
            emp_name = emp_map.get(user_id, f"User {user_id}")
            points = float(gamif.get("points", 0.0))
            leaderboard.append({
                "Name": emp_name,
                "Points": points
            })

        # Sort by points descending
        leaderboard.sort(key=lambda x: x["Points"], reverse=True)
        return leaderboard

    except Exception as e:
        print(f"⚠️ Error getting leaderboard: {e}")
        return []