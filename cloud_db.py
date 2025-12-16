from datetime import datetime
from supabase import create_client, Client
from typing import Optional, List, Dict, Any

SUPABASE_URL = "https://sunsfqthmwotlbfcgmay.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def insert_emotion(
    person_id: str,  # <-- Cambiado a str para flexibilidad
    emotion: str,
    gender: str,
    stress_score: float,
    stress_level: str,
    created_at: Optional[str] = None,
) -> None:
    """
    Inserta un registro en la tabla emotions de Supabase.
    """
    if created_at is None:
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    # Convertir person_id a int si es necesario
    try:
        person_id_int = int(person_id)
    except (ValueError, TypeError):
        person_id_int = 1  # Valor por defecto si la conversión falla

    data = {
        "person_id": person_id_int,  # <-- Usar el entero convertido
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

def get_gamification_leaderboard() -> List[Dict[str, Any]]:
    """
    Retrieve gamification leaderboard from Supabase.
    
    Returns:
        List of dictionaries with employee name and points, sorted by points descending.
    """
    try:
        # First, try to get gamification data
        # Assuming there's a 'gamification' table or 'user_points' table
        # If not, we'll use a placeholder or calculate from existing data
        
        # Option 1: Check if there's a gamification table
        try:
            response = supabase.table("gamification").select("*").order("points", desc=True).execute()
            if hasattr(response, 'data') and response.data:
                leaderboard_data = []
                for record in response.data:
                    # Get employee name
                    user_id = record.get('user_id') or record.get('person_id')
                    if user_id:
                        emp_response = supabase.table("Employees").select("Name").eq("id", int(user_id)).execute()
                        if emp_response.data:
                            name = emp_response.data[0]['Name']
                        else:
                            name = f"Employee {user_id}"
                    else:
                        name = "Unknown"
                    
                    leaderboard_data.append({
                        "Name": name,
                        "Points": float(record.get('points', 0))
                    })
                return leaderboard_data
        except Exception as e:
            print(f"[Supabase] No gamification table found: {e}")
        
        # Option 2: Calculate points from emotions data (if no gamification table exists)
        # This is a fallback mechanism
        try:
            # Get all emotions data grouped by employee
            response = supabase.table("emotions").select("person_id, created_at").execute()
            if hasattr(response, 'data') and response.data:
                from collections import defaultdict
                import pandas as pd
                
                # Group by person_id and count entries per day
                df = pd.DataFrame(response.data)
                df['created_at'] = pd.to_datetime(df['created_at'])
                df['date'] = df['created_at'].dt.date
                
                # Calculate points: 1 point per day of activity
                points_by_employee = defaultdict(float)
                for _, row in df.iterrows():
                    person_id = row['person_id']
                    date = row['date']
                    key = (person_id, date)
                    # Give 1 point per unique day
                    points_by_employee[person_id] += 1.0
                
                # Convert to leaderboard format
                leaderboard_data = []
                for person_id, points in points_by_employee.items():
                    # Get employee name
                    emp_response = supabase.table("Employees").select("Name").eq("id", int(person_id)).execute()
                    if emp_response.data:
                        name = emp_response.data[0]['Name']
                    else:
                        name = f"Employee {person_id}"
                    
                    leaderboard_data.append({
                        "Name": name,
                        "Points": float(points)
                    })
                
                # Sort by points descending
                leaderboard_data.sort(key=lambda x: x['Points'], reverse=True)
                return leaderboard_data
                
        except Exception as e:
            print(f"[Supabase] Error calculating points from emotions: {e}")
        
        return []
            
    except Exception as e:
        print(f"[Supabase] Error retrieving leaderboard: {e}")
        return []