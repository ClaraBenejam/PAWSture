"""
Streamlit dashboard for Employee Wellness Monitoring System.
Provides interfaces for employees, managers, and NHS doctors.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import subprocess
import sys
import time
import socket
import threading

# Import leaderboard module
from leaderboard_module import show_leaderboard

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://sunsfqthmwotlbfcgmay.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1bnNmcXRobXdvdGxiZmNnbWF5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM0MDQwNjcsImV4cCI6MjA3ODk4MDA2N30.dLSgRjiiK4dDrYcwenp2RHBkMdQxYglficyyRripRN8")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase credentials. Please check your .env file.")
    st.stop()

# Initialize Supabase client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Failed to connect to Supabase: {e}")
    st.stop()

# Initialize session state for authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'current_user' not in st.session_state:
    st.session_state.current_user = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if 'video_server_process' not in st.session_state:
    st.session_state.video_server_process = None
if 'emotion_client_process' not in st.session_state:
    st.session_state.emotion_client_process = None
if 'posture_client_process' not in st.session_state:
    st.session_state.posture_client_process = None
if 'all_apps_running' not in st.session_state:
    st.session_state.all_apps_running = False
if 'employee_name' not in st.session_state:
    st.session_state.employee_name = None
if 'manager_name' not in st.session_state:
    st.session_state.manager_name = None
if 'nhs_doctor_name' not in st.session_state:
    st.session_state.nhs_doctor_name = None
if 'unified_bot_process' not in st.session_state:
    st.session_state.unified_bot_process = None
if 'unified_bot_running' not in st.session_state:
    st.session_state.unified_bot_running = False
if 'unified_bot_port' not in st.session_state:
    st.session_state.unified_bot_port = 8443  # Puerto por defecto para el bot


def get_employees():
    """
    Retrieve list of employees from Supabase.
    
    Returns:
        List of employee dictionaries or empty list on error
    """
    try:
        response = supabase.table("Employees").select("*").execute()
        if hasattr(response, 'data') and response.data:
            return response.data
        return []
    except Exception as e:
        st.error(f"Error fetching employees: {e}")
        return []


def get_managers():
    """
    Retrieve list of managers from Supabase.
    
    Returns:
        List of manager dictionaries or empty list on error
    """
    try:
        response = supabase.table("Managers").select("*").execute()
        if hasattr(response, 'data') and response.data:
            return response.data
        return []
    except Exception as e:
        st.error(f"Error fetching managers: {e}")
        return []


def get_nhs_doctors():
    """
    Retrieve list of NHS doctors from Supabase.
    
    Returns:
        List of NHS doctor dictionaries or empty list on error
    """
    try:
        response = supabase.table("NHS").select("*").execute()
        if hasattr(response, 'data') and response.data:
            return response.data
        return []
    except Exception as e:
        st.error(f"Error fetching NHS doctors: {e}")
        return []


def verify_employee_credentials(employee_id, password):
    """
    Verify employee login credentials.
    
    Parameters:
        employee_id: Employee ID to verify
        password: Password to check
        
    Returns:
        Employee data if credentials valid, None otherwise
    """
    employees = get_employees()
    for employee in employees:
        if str(employee['id']) == str(employee_id) and employee['Password'] == password:
            return employee
    return None


def verify_manager_credentials(manager_id, password):
    """
    Verify manager login credentials.
    
    Parameters:
        manager_id: Manager ID to verify
        password: Password to check
        
    Returns:
        Manager data if credentials valid, None otherwise
    """
    managers = get_managers()
    for manager in managers:
        if str(manager['id']) == str(manager_id) and manager['Password'] == password:
            return manager
    return None


def verify_nhs_doctor_credentials(doctor_id, password):
    """
    Verify NHS doctor login credentials.
    
    Parameters:
        doctor_id: Doctor ID to verify
        password: Password to check
        
    Returns:
        Doctor data if credentials valid, None otherwise
    """
    doctors = get_nhs_doctors()
    for doctor in doctors:
        if str(doctor['id']) == str(doctor_id) and doctor['password'] == password:
            return doctor
    return None


def get_emotions_data(person_id=None):
    """
    Fetch emotions data from Supabase.
    
    Parameters:
        person_id: Optional filter for specific employee
        
    Returns:
        DataFrame with emotions data or empty DataFrame on error
    """
    try:
        query = supabase.table("emotions").select("*").order("created_at", desc=True)
        if person_id and person_id != "manager" and person_id != "nhs_doctor":
            query = query.eq("person_id", int(person_id))
        response = query.execute()
        
        if hasattr(response, 'data') and response.data:
            df = pd.DataFrame(response.data)
            if not df.empty:
                df['created_at'] = pd.to_datetime(df['created_at'])
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching emotions data: {e}")
        return pd.DataFrame()


def get_posture_data(user_id=None):
    """
    Fetch posture data from Supabase.
    
    Parameters:
        user_id: Optional filter for specific user
        
    Returns:
        DataFrame with posture data or empty DataFrame on error
    """
    try:
        query = supabase.table("posture").select("*").order("timestamp", desc=True)
        if user_id and user_id != "manager" and user_id != "nhs_doctor":
            query = query.eq("id_usuario", int(user_id))
        response = query.execute()
        
        if hasattr(response, 'data') and response.data:
            df = pd.DataFrame(response.data)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching posture data: {e}")
        return pd.DataFrame()


def get_available_users():
    """
    Get list of available user IDs from database.
    
    Returns:
        List of user ID strings or empty list on error
    """
    try:
        employees = get_employees()
        if employees:
            return [str(emp['id']) for emp in employees]
        return []
    except Exception as e:
        st.error(f"Error fetching users: {e}")
        return []


def get_user_display_name(user_id):
    """
    Convert user ID to display name.
    
    Parameters:
        user_id: User ID string
        
    Returns:
        Formatted display name string
    """
    if user_id == "manager":
        return "Manager"
    elif user_id == "nhs_doctor":
        return "NHS Doctor"
    
    employees = get_employees()
    for employee in employees:
        if str(employee['id']) == str(user_id):
            return f"{employee['Name']} (ID: {employee['id']})"
    
    return f"Employee {user_id}"


def remove_duplicate_seconds(df, time_column, value_column):
    """
    Remove duplicate measurements within the same second.
    
    Parameters:
        df: DataFrame with time series data
        time_column: Name of time column
        value_column: Name of value column
        
    Returns:
        DataFrame with only first measurement per second
    """
    if df.empty:
        return df
    
    df_local = df.copy()
    df_local[time_column] = df_local[time_column].dt.tz_localize(None)
    
    # Create second-level timestamp
    df_local['time_second'] = df_local[time_column].dt.floor('1s')
    
    # Keep only first measurement per second
    df_unique = df_local.drop_duplicates(subset=['time_second'], keep='first')
    
    # Remove helper column
    df_unique = df_unique.drop('time_second', axis=1)
    
    return df_unique


def smooth_timeline_data(df, time_column, value_column, max_points=50):
    """
    Smooth timeline data by removing duplicates per second and limiting to last N points.
    
    Parameters:
        df: DataFrame with time series data
        time_column: Name of time column
        value_column: Name of value column
        max_points: Maximum number of points to return
        
    Returns:
        Smoothed DataFrame
    """
    if df.empty:
        return df
    
    # Remove duplicates per second
    df_smoothed = remove_duplicate_seconds(df, time_column, value_column)
    
    # Sort by time and limit to max_points
    df_smoothed = df_smoothed.sort_values(time_column, ascending=True)
    
    if len(df_smoothed) > max_points:
        df_smoothed = df_smoothed.tail(max_points)
    
    return df_smoothed


def check_port_in_use(port=9999):
    """
    Check if a port is already in use.
    
    Parameters:
        port: Port number to check
        
    Returns:
        True if port is in use, False otherwise
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return False
    except socket.error:
        return True


def check_bot_port_in_use(port=8443):
    """
    Check if the bot port is already in use.
    
    Parameters:
        port: Port number to check
        
    Returns:
        True if port is in use, False otherwise
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return False
    except socket.error:
        return True


def start_unified_analysis(employee_id=None):
    """
    Start unified analysis: video server + emotion and posture clients.
    
    Parameters:
        employee_id: Optional employee ID for client processes
        
    Returns:
        True if all applications started successfully, False otherwise
    """
    try:
        # Stop any existing processes
        stop_unified_analysis()
        
        # Check if port is available
        if check_port_in_use(9999):
            st.error("Port 9999 is already in use. Close other applications using this port.")
            return False
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Conda environment paths
        conda_python_yolov11 = r"C:\Users\marco\miniconda3\envs\yolov11\python.exe"
        conda_python_emotions = r"C:\Users\marco\miniconda3\envs\emotions\python.exe"
        
        # Verify conda environments exist
        if not all(os.path.exists(path) for path in [conda_python_yolov11, conda_python_emotions]):
            st.error("Conda environments not found. Check installation.")
            return False
        
        # Platform-specific flags
        creation_flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        
        # Start video server
        server_path = os.path.join(current_dir, "video_server.py")
        with st.spinner("Starting video server (yolov11 environment)..."):
            server_process = subprocess.Popen(
                [conda_python_yolov11, server_path],
                creationflags=creation_flags,
                cwd=current_dir
            )
            st.session_state.video_server_process = server_process
            time.sleep(3)
        
        # Start emotion client
        emotion_client_path = os.path.join(current_dir, "emotion_client.py")
        emotion_args = [conda_python_emotions, emotion_client_path]
        if employee_id:
            emotion_args.append(str(employee_id))
        
        with st.spinner("Starting emotion analysis window (emotions environment)..."):
            emotion_process = subprocess.Popen(
                emotion_args,
                creationflags=creation_flags,
                cwd=current_dir
            )
            st.session_state.emotion_client_process = emotion_process
            time.sleep(2)
        
        # Start posture client
        posture_client_path = os.path.join(current_dir, "posture_client.py")
        posture_args = [conda_python_yolov11, posture_client_path]
        if employee_id:
            posture_args.append(str(employee_id))
        
        with st.spinner("Starting posture analysis window (yolov11 environment)..."):
            posture_process = subprocess.Popen(
                posture_args,
                creationflags=creation_flags,
                cwd=current_dir
            )
            st.session_state.posture_client_process = posture_process
        
        time.sleep(2)
        
        # Verify all processes started
        all_running = all([
            st.session_state.video_server_process,
            st.session_state.emotion_client_process,
            st.session_state.posture_client_process
        ])
        
        if all_running:
            st.session_state.all_apps_running = True
            return True
        else:
            st.error("Some applications failed to start")
            return False
        
    except Exception as e:
        st.error(f"Error starting unified analysis: {str(e)}")
        return False


def stop_unified_analysis():
    """
    Stop all unified analysis processes.
    
    Returns:
        True if processes were stopped, False otherwise
    """
    try:
        processes_stopped = 0
        
        # Stop posture client
        if st.session_state.posture_client_process:
            try:
                st.session_state.posture_client_process.terminate()
                time.sleep(0.5)
                processes_stopped += 1
            except:
                pass
            st.session_state.posture_client_process = None
        
        # Stop emotion client
        if st.session_state.emotion_client_process:
            try:
                st.session_state.emotion_client_process.terminate()
                time.sleep(0.5)
                processes_stopped += 1
            except:
                pass
            st.session_state.emotion_client_process = None
        
        # Stop video server
        if st.session_state.video_server_process:
            try:
                st.session_state.video_server_process.terminate()
                time.sleep(0.5)
                processes_stopped += 1
            except:
                pass
            st.session_state.video_server_process = None
        
        st.session_state.all_apps_running = False
        
        if processes_stopped > 0:
            return True
        else:
            st.warning("No processes were running")
            return False
            
    except Exception as e:
        st.error(f"Error stopping unified analysis: {str(e)}")
        return False


def start_unified_bot():
    """
    Start the unified Telegram bot for alerts and recommendations.
    The bot runs in the 'pawsture' conda environment.
    
    Returns:
        True if bot started successfully, False otherwise
    """
    try:
        # Stop existing bot if running
        stop_unified_bot()
        
        # Check if port is available
        if check_bot_port_in_use(st.session_state.unified_bot_port):
            st.error(f"Port {st.session_state.unified_bot_port} is already in use. Unified bot may already be running.")
            return False
        
        # Get current directory and bot path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        alertas_dir = os.path.join(current_dir, "alertas_recomendaciones")
        
        # Check if alertas_recomendaciones directory exists
        if not os.path.exists(alertas_dir):
            st.error(f"Directory 'alertas_recomendaciones' not found at: {alertas_dir}")
            return False
        
        bot_script_path = os.path.join(alertas_dir, "unified_bot.py")
        
        # Check if bot script exists
        if not os.path.exists(bot_script_path):
            st.error(f"Unified bot script not found at: {bot_script_path}")
            return False
        
        # Conda environment path for pawsture
        conda_python_pawsture = r"C:\Users\marco\miniconda3\envs\pawsture\python.exe"
        
        # Verify conda environment exists
        if not os.path.exists(conda_python_pawsture):
            st.error("Conda environment 'pawsture' not found. Please install the required environment.")
            return False
        
        # Platform-specific flags
        creation_flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        
        # Start the bot process
        with st.spinner("Starting unified Telegram bot (pawsture environment)..."):
            bot_process = subprocess.Popen(
                [conda_python_pawsture, bot_script_path],
                creationflags=creation_flags,
                cwd=alertas_dir  # Important: run from alertas_recomendaciones directory
            )
            st.session_state.unified_bot_process = bot_process
            st.session_state.unified_bot_running = True
            
            # Wait for bot to initialize
            time.sleep(3)
            
            # Check if process is still running
            if bot_process.poll() is not None:
                st.error("Unified bot failed to start. Check the console for errors.")
                st.session_state.unified_bot_running = False
                return False
            
            return True
            
    except Exception as e:
        st.error(f"Error starting unified bot: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return False


def stop_unified_bot():
    """
    Stop the unified Telegram bot.
    
    Returns:
        True if bot stopped successfully, False otherwise
    """
    try:
        if st.session_state.unified_bot_process is not None:
            with st.spinner("Stopping unified Telegram bot..."):
                # Terminate the process
                st.session_state.unified_bot_process.terminate()
                
                # Wait for process to terminate
                time.sleep(2)
                
                # Force kill if still running
                if st.session_state.unified_bot_process.poll() is None:
                    st.session_state.unified_bot_process.kill()
                    time.sleep(1)
                
                st.session_state.unified_bot_process = None
                st.session_state.unified_bot_running = False
            
            return True
        else:
            st.warning("Unified bot is not running.")
            st.session_state.unified_bot_running = False
            return False
            
    except Exception as e:
        st.error(f"Error stopping unified bot: {str(e)}")
        return False


def get_bot_instructions():
    """
    Get instructions for using the Telegram bot.
    
    Returns:
        String with instructions
    """
    return """
    **🤖 Telegram Bot Instructions:**
    
    1. **Find the bot:** Search for @PAWStureHealthBot on Telegram
    2. **Start the bot:** Send `/start` to begin monitoring
    3. **Available commands:**
       - `/status` - Current health status
       - `/recommendation [user_id]` - Request manual intervention
       - `/stats [user_id]` - Response statistics
       - `/posture_status` - Posture only status
       - `/emotion_status` - Emotion only status
       - `/config` - Current settings
       - `/model_status` - AI system status
    
    **📱 Features:**
    - Real-time posture and emotion monitoring
    - Automatic alerts when issues are detected
    - Personalized recommendations
    - Response tracking for AI learning
    - Multi-user support
    
    **⚠️ Note:** The bot monitors ALL users automatically. Make sure your employee ID is correct.
    """


def calculate_posture_statistics(posture_data):
    """
    Calculate statistics from posture data.
    
    Parameters:
        posture_data: DataFrame with posture measurements
        
    Returns:
        Dictionary with calculated statistics
    """
    stats = {}
    
    if posture_data.empty:
        return stats
    
    # Areas to analyze
    areas = [
        'neck_lateral_bend_zone',
        'neck_flexion_zone', 
        'shoulder_alignment_zone',
        'arm_abduction_zone',
        'overall_zone'
    ]
    
    # Calculate statistics for each area
    for area in areas:
        if area in posture_data.columns:
            valid_data = posture_data[posture_data[area] >= 0]
            if not valid_data.empty:
                stats[area] = {
                    'mean': valid_data[area].mean(),
                    'median': valid_data[area].median(),
                    'max': valid_data[area].max(),
                    'min': valid_data[area].min(),
                    'std': valid_data[area].std(),
                    'count': len(valid_data)
                }
    
    return stats


def calculate_emotion_statistics(emotions_data):
    """
    Calculate statistics from emotions data.
    
    Parameters:
        emotions_data: DataFrame with emotion measurements
        
    Returns:
        Dictionary with calculated statistics
    """
    stats = {}
    
    if emotions_data.empty:
        return stats
    
    # Calculate emotion distribution
    emotion_counts = emotions_data['emotion'].value_counts()
    emotion_percentages = (emotion_counts / len(emotions_data) * 100).round(2)
    
    stats['emotion_distribution'] = {
        'counts': emotion_counts.to_dict(),
        'percentages': emotion_percentages.to_dict()
    }
    
    # Calculate stress statistics
    if 'stress_score' in emotions_data.columns:
        stats['stress'] = {
            'mean': emotions_data['stress_score'].mean(),
            'median': emotions_data['stress_score'].median(),
            'max': emotions_data['stress_score'].max(),
            'min': emotions_data['stress_score'].min(),
            'std': emotions_data['stress_score'].std()
        }
    
    # Calculate stress level distribution
    if 'stress_level' in emotions_data.columns:
        stress_level_counts = emotions_data['stress_level'].value_counts()
        stats['stress_level_distribution'] = stress_level_counts.to_dict()
    
    return stats


def detect_critical_periods(posture_data, stress_data, posture_threshold=2, 
                           stress_threshold=50, window_minutes=5):
    """
    Detect critical periods where thresholds are exceeded continuously.
    
    Parameters:
        posture_data: DataFrame with posture measurements
        stress_data: DataFrame with stress measurements
        posture_threshold: Critical posture zone threshold
        stress_threshold: Critical stress score threshold
        window_minutes: Minimum duration for critical period
        
    Returns:
        List of critical period dictionaries
    """
    critical_periods = []
    
    if posture_data.empty or stress_data.empty:
        return critical_periods
    
    # Prepare data with minute-level timestamps
    posture_df = posture_data.copy()
    stress_df = stress_data.copy()
    
    posture_df['time_key'] = posture_df['timestamp'].dt.floor('min')
    stress_df['time_key'] = stress_df['created_at'].dt.floor('min')
    
    # Merge posture and stress data
    merged_df = pd.merge(
        posture_df[['time_key', 'overall_zone']].rename(columns={'overall_zone': 'posture_zone'}),
        stress_df[['time_key', 'stress_score']],
        on='time_key',
        how='inner'
    )
    
    if merged_df.empty:
        return critical_periods
    
    # Identify critical thresholds
    merged_df['posture_critical'] = merged_df['posture_zone'] >= posture_threshold
    merged_df['stress_critical'] = merged_df['stress_score'] >= stress_threshold
    merged_df['both_critical'] = merged_df['posture_critical'] & merged_df['stress_critical']
    
    # Group consecutive critical periods
    for col in ['posture_critical', 'stress_critical', 'both_critical']:
        merged_df[f'{col}_group'] = (merged_df[col] != merged_df[col].shift()).cumsum()
    
    # Detect posture critical periods
    for group_id, group in merged_df[merged_df['posture_critical']].groupby('posture_critical_group'):
        if len(group) >= window_minutes:
            start_time = group['time_key'].min()
            end_time = group['time_key'].max()
            duration = (end_time - start_time).total_seconds() / 60
            
            critical_periods.append({
                'type': 'posture',
                'start': start_time,
                'end': end_time,
                'duration_minutes': duration,
                'avg_posture_zone': group['posture_zone'].mean(),
                'avg_stress': group['stress_score'].mean() if 'stress_score' in group.columns else None,
                'details': f"Posture ≥ zone {posture_threshold} for {duration:.1f} minutes"
            })
    
    # Detect stress critical periods
    for group_id, group in merged_df[merged_df['stress_critical']].groupby('stress_critical_group'):
        if len(group) >= window_minutes:
            start_time = group['time_key'].min()
            end_time = group['time_key'].max()
            duration = (end_time - start_time).total_seconds() / 60
            
            critical_periods.append({
                'type': 'stress',
                'start': start_time,
                'end': end_time,
                'duration_minutes': duration,
                'avg_posture_zone': group['posture_zone'].mean() if 'posture_zone' in group.columns else None,
                'avg_stress': group['stress_score'].mean(),
                'details': f"Stress ≥ {stress_threshold}% for {duration:.1f} minutes"
            })
    
    # Detect combined critical periods
    for group_id, group in merged_df[merged_df['both_critical']].groupby('both_critical_group'):
        if len(group) >= window_minutes:
            start_time = group['time_key'].min()
            end_time = group['time_key'].max()
            duration = (end_time - start_time).total_seconds() / 60
            
            critical_periods.append({
                'type': 'both',
                'start': start_time,
                'end': end_time,
                'duration_minutes': duration,
                'avg_posture_zone': group['posture_zone'].mean(),
                'avg_stress': group['stress_score'].mean(),
                'details': f"Posture ≥ zone {posture_threshold} and stress ≥ {stress_threshold}% for {duration:.1f} minutes"
            })
    
    # Sort by start time
    critical_periods.sort(key=lambda x: x['start'])
    
    return critical_periods


def identify_worst_posture_areas(posture_stats):
    """
    Identify worst posture areas based on statistics.
    
    Parameters:
        posture_stats: Dictionary with posture statistics
        
    Returns:
        List of worst areas sorted by severity
    """
    if not posture_stats:
        return []
    
    worst_areas = []
    
    # Area display names mapping
    area_names = {
        'neck_lateral_bend_zone': 'Neck lateral bend',
        'neck_flexion_zone': 'Neck flexion',
        'shoulder_alignment_zone': 'Shoulder alignment',
        'arm_abduction_zone': 'Arm abduction',
        'overall_zone': 'Overall posture'
    }
    
    # Process each area
    for area, stats in posture_stats.items():
        if area in area_names and stats['count'] > 0:
            worst_areas.append({
                'area': area_names[area],
                'mean_zone': stats['mean'],
                'max_zone': stats['max'],
                'risk_level': determine_risk_level(stats['mean'])
            })
    
    # Sort by mean zone (descending)
    worst_areas.sort(key=lambda x: x['mean_zone'], reverse=True)
    
    return worst_areas


def determine_risk_level(zone_value):
    """
    Determine risk level based on zone value.
    
    Parameters:
        zone_value: Posture zone value (0-4)
        
    Returns:
        Risk level string
    """
    if zone_value < 1:
        return "Very Low"
    elif zone_value < 2:
        return "Low"
    elif zone_value < 3:
        return "Moderate"
    elif zone_value < 4:
        return "High"
    else:
        return "Very High"


def get_emotions_data_range(person_id, start_date=None, end_date=None):
    """
    Get emotion data for an employee within a date range.
    
    Parameters:
        person_id: Employee ID
        start_date: Start date for filtering
        end_date: End date for filtering
        
    Returns:
        DataFrame with filtered emotion data
    """
    try:
        query = supabase.table("emotions").select("*").eq("person_id", int(person_id))
        
        # Apply date filters if provided
        if start_date and end_date:
            query = query.gte("created_at", start_date.isoformat()).lte("created_at", end_date.isoformat())
        
        query = query.order("created_at", desc=True)
        response = query.execute()
        
        if hasattr(response, 'data') and response.data:
            df = pd.DataFrame(response.data)
            if not df.empty:
                df['created_at'] = pd.to_datetime(df['created_at'])
                df = df.sort_values('created_at')
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error getting emotion data: {e}")
        return pd.DataFrame()


def get_posture_data_range(user_id, start_date=None, end_date=None):
    """
    Get posture data for an employee within a date range.
    
    Parameters:
        user_id: User ID
        start_date: Start date for filtering
        end_date: End date for filtering
        
    Returns:
        DataFrame with filtered posture data
    """
    try:
        query = supabase.table("posture").select("*").eq("id_usuario", int(user_id))
        
        # Apply date filters if provided
        if start_date and end_date:
            query = query.gte("timestamp", start_date.isoformat()).lte("timestamp", end_date.isoformat())
        
        query = query.order("timestamp", desc=True)
        response = query.execute()
        
        if hasattr(response, 'data') and response.data:
            df = pd.DataFrame(response.data)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp')
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error getting posture data: {e}")
        return pd.DataFrame()


def show_report_generator():
    """
    Display report generator interface for creating wellness reports.
    
    This function now excludes personalized recommendations.
    """
    st.title("Wellness Report Generator")
    
    employees = get_employees()
    
    # Employee selection
    if st.session_state.user_role in ["manager", "nhs_doctor"]:
        st.subheader("Employee Selection")
        if employees:
            employee_options = {f"{emp['Name']} (ID: {emp['id']})": emp['id'] for emp in employees}
            selected_employee_name = st.selectbox("Select Employee", list(employee_options.keys()))
            employee_id = employee_options[selected_employee_name]
            employee_name = selected_employee_name.split(" (ID:")[0]
        else:
            st.warning("No employees found in database.")
            return
    else:
        employee_id = int(st.session_state.current_user)
        employee_name = st.session_state.employee_name
        st.info(f"Generating report for: {employee_name}")
    
    # Date range selection
    st.subheader("Analysis Period")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
        start_time = st.time_input("Start Time", value=datetime.strptime("09:00", "%H:%M").time())
    with col2:
        end_date = st.date_input("End Date", value=datetime.now())
        end_time = st.time_input("End Time", value=datetime.strptime("17:00", "%H:%M").time())
    
    start_datetime = datetime.combine(start_date, start_time)
    end_datetime = datetime.combine(end_date, end_time)
    
    if start_datetime >= end_datetime:
        st.error("Start date must be earlier than end date.")
        return
    
    # Threshold configuration in sidebar
    st.sidebar.header("Threshold Configuration")
    posture_threshold = st.sidebar.slider("Critical Posture Threshold (zone)", 0, 4, 2)
    stress_threshold = st.sidebar.slider("Critical Stress Threshold (%)", 0, 100, 50)
    min_event_duration = st.sidebar.slider("Minimum event duration (minutes)", 1, 60, 5)
    
    # Generate report button
    if st.button("Generate Report", type="primary"):
        with st.spinner("Generating report..."):
            # Fetch data
            emotions_data = get_emotions_data_range(employee_id, start_datetime, end_datetime)
            posture_data = get_posture_data_range(employee_id, start_datetime, end_datetime)
            
            if emotions_data.empty and posture_data.empty:
                st.error("No data available for the selected period.")
                return
            
            # Calculate statistics
            posture_stats = calculate_posture_statistics(posture_data)
            emotion_stats = calculate_emotion_statistics(emotions_data)
            critical_periods = detect_critical_periods(
                posture_data, emotions_data, posture_threshold, stress_threshold, min_event_duration
            )
            worst_areas = identify_worst_posture_areas(posture_stats)
            
            # Display report summary
            st.subheader("Report Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                if posture_stats and 'overall_zone' in posture_stats:
                    st.metric("Average Posture Zone", f"{posture_stats['overall_zone']['mean']:.2f}")
            with col2:
                if emotion_stats and 'stress' in emotion_stats:
                    st.metric("Average Stress", f"{emotion_stats['stress']['mean']:.1f}%")
            with col3:
                st.metric("Critical Periods", len(critical_periods))
            
            # Display employee information for NHS doctors
            if st.session_state.user_role == "nhs_doctor":
                st.subheader("Employee Information")
                for emp in employees:
                    if emp['id'] == employee_id:
                        st.write(f"**Name:** {emp['Name']}")
                        st.write(f"**Employee ID:** {emp['id']}")
                        st.write(f"**Analysis Period:** {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%Y-%m-%d %H:%M')}")
                        break
            
            # Display worst posture areas
            st.subheader("Posture Analysis")
            if worst_areas:
                worst_df = pd.DataFrame(worst_areas)
                st.dataframe(worst_df, use_container_width=True)
                
                fig = px.bar(worst_df, x='area', y='mean_zone', title='Average Zone by Body Area',
                            color='mean_zone', color_continuous_scale='RdYlGn_r')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Insufficient posture data to analyze areas.")
            
            # Display emotion distribution
            st.subheader("Emotional State Analysis")
            if emotion_stats and 'emotion_distribution' in emotion_stats:
                emotion_df = pd.DataFrame({
                    'Emotion': list(emotion_stats['emotion_distribution']['percentages'].keys()),
                    'Percentage': list(emotion_stats['emotion_distribution']['percentages'].values())
                })
                
                fig2 = px.pie(emotion_df, values='Percentage', names='Emotion', title='Emotion Distribution')
                st.plotly_chart(fig2, use_container_width=True)
                
                st.dataframe(emotion_df.sort_values('Percentage', ascending=False), use_container_width=True)
            else:
                st.info("No emotion data to analyze.")
            
            # Display critical periods
            st.subheader("Critical Periods Analysis")
            if critical_periods:
                critical_df = pd.DataFrame(critical_periods)
                
                critical_display = critical_df.copy()
                critical_display['start'] = critical_display['start'].dt.strftime('%Y-%m-%d %H:%M')
                critical_display['end'] = critical_display['end'].dt.strftime('%Y-%m-%d %H:%M')
                critical_display['duration_minutes'] = critical_display['duration_minutes'].round(1)
                
                st.dataframe(critical_display, use_container_width=True)
                
                # Create combined visualization if data available
                if not posture_data.empty and not emotions_data.empty:
                    # Suavizar datos
                    posture_smoothed = smooth_timeline_data(
                        posture_data[['timestamp', 'overall_zone']].copy(), 
                        'timestamp', 
                        'overall_zone',
                        max_points=100
                    )
                    posture_smoothed['type'] = 'posture'
                    
                    emotions_smoothed = smooth_timeline_data(
                        emotions_data[['created_at', 'stress_score']].copy(), 
                        'created_at', 
                        'stress_score',
                        max_points=100
                    )
                    emotions_smoothed = emotions_smoothed.rename(columns={'created_at': 'timestamp', 'stress_score': 'value'})
                    emotions_smoothed['type'] = 'stress'
                    emotions_smoothed['value'] = emotions_smoothed['value'] / 25
                    
                    posture_plot = posture_smoothed.rename(columns={'overall_zone': 'value'})
                    combined_plot = pd.concat([posture_plot, emotions_smoothed])
                    
                    fig3 = px.line(combined_plot, x='timestamp', y='value', color='type',
                                  title='Posture and Stress Evolution (scaled & smoothed)',
                                  labels={'value': 'Value (Posture: 0-4, Stress: 0-4)', 'timestamp': 'Time'})
                    
                    fig3.add_hline(y=posture_threshold, line_dash="dash", line_color="red", 
                                  annotation_text=f"Posture Threshold: {posture_threshold}")
                    fig3.add_hline(y=stress_threshold/25, line_dash="dash", line_color="orange", 
                                  annotation_text=f"Stress Threshold: {stress_threshold}%")
                    
                    st.plotly_chart(fig3, use_container_width=True)
            else:
                st.success(f"No critical periods detected during the analyzed time.")


def show_nhs_dashboard():
    """
    Display dashboard for NHS doctors with aggregated health data.
    """
    st.header(f"NHS Doctor Dashboard - {st.session_state.nhs_doctor_name}")
    
    employees = get_employees()
    
    if not employees:
        st.warning("No employees found in the database.")
        return
    
    # Overview statistics
    st.subheader("Population Health Overview")
    
    # Get data for all employees
    all_emotions = get_emotions_data()
    all_posture = get_posture_data()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Employees", len(employees))
    with col2:
        if not all_emotions.empty:
            avg_stress = all_emotions['stress_score'].mean()
            st.metric("Average Stress", f"{avg_stress:.1f}%")
    with col3:
        if not all_posture.empty:
            avg_posture = all_posture['overall_zone'].mean()
            st.metric("Average Posture Zone", f"{avg_posture:.2f}")
    with col4:
        active_employees = len([emp for emp in employees if get_emotions_data(emp['id']).shape[0] > 0])
        st.metric("Active Employees", active_employees)
    
    # Employee health status overview
    st.subheader("Employee Health Status")
    
    health_data = []
    for emp in employees:
        emp_emotions = get_emotions_data(emp['id'])
        emp_posture = get_posture_data(emp['id'])
        
        if not emp_emotions.empty or not emp_posture.empty:
            avg_stress = emp_emotions['stress_score'].mean() if not emp_emotions.empty else 0
            avg_posture = emp_posture['overall_zone'].mean() if not emp_posture.empty else 0
            
            # Determine health status
            if avg_stress > 70 or avg_posture > 3:
                status = "High Risk"
                color = "red"
            elif avg_stress > 50 or avg_posture > 2:
                status = "Moderate Risk"
                color = "orange"
            else:
                status = "Low Risk"
                color = "green"
            
            health_data.append({
                'Employee': emp['Name'],
                'ID': emp['id'],
                'Avg Stress': round(avg_stress, 1),
                'Avg Posture': round(avg_posture, 2),
                'Status': status,
                'Data Points': len(emp_emotions) + len(emp_posture),
                '_color': color
            })
    
    if health_data:
        health_df = pd.DataFrame(health_data)
        
        # Create health status visualization
        fig = px.scatter(health_df, 
                        x='Avg Stress', 
                        y='Avg Posture',
                        color='Status',
                        size='Data Points',
                        hover_data=['Employee', 'ID'],
                        title='Employee Health Distribution',
                        color_discrete_map={
                            'High Risk': 'red',
                            'Moderate Risk': 'orange',
                            'Low Risk': 'green'
                        })
        
        # Add risk zones
        fig.add_hrect(y0=3, y1=5, line_width=0, fillcolor="red", opacity=0.1)
        fig.add_hrect(y0=2, y1=3, line_width=0, fillcolor="orange", opacity=0.1)
        fig.add_vrect(x0=70, x1=100, line_width=0, fillcolor="red", opacity=0.1)
        fig.add_vrect(x0=50, x1=70, line_width=0, fillcolor="orange", opacity=0.1)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display table
        st.dataframe(health_df[['Employee', 'ID', 'Avg Stress', 'Avg Posture', 'Status', 'Data Points']], 
                    use_container_width=True)
    
    # Información adicional útil para doctores
    st.subheader("Health Indicators Summary")
    
    if health_data:
        # Calcular estadísticas de riesgo
        high_risk = len([h for h in health_data if h['Status'] == 'High Risk'])
        moderate_risk = len([h for h in health_data if h['Status'] == 'Moderate Risk'])
        low_risk = len([h for h in health_data if h['Status'] == 'Low Risk'])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("High Risk Employees", high_risk)
        with col2:
            st.metric("Moderate Risk Employees", moderate_risk)
        with col3:
            st.metric("Low Risk Employees", low_risk)


def login():
    """Display login interface in sidebar."""
    st.sidebar.header("Login")
    
    role = st.sidebar.selectbox("Select Role", ["Employee", "Manager", "NHS Doctor"])
    
    if role == "Employee":
        employees = get_employees()
        if employees:
            employee_options = {f"{emp['Name']} (ID: {emp['id']})": emp['id'] for emp in employees}
            selected_employee = st.sidebar.selectbox("Select Employee", list(employee_options.keys()))
            employee_id = employee_options[selected_employee]
            
            password = st.sidebar.text_input("Password", type="password")
            
            if st.sidebar.button("Login as Employee"):
                employee = verify_employee_credentials(employee_id, password)
                if employee:
                    st.session_state.authenticated = True
                    st.session_state.current_user = str(employee['id'])
                    st.session_state.user_role = "employee"
                    st.session_state.employee_name = employee['Name']
                    st.rerun()
                elif password:
                    st.sidebar.error("Incorrect password")
        else:
            st.sidebar.warning("No employees found in database")
    
    elif role == "Manager":
        managers = get_managers()
        if managers:
            manager_options = {f"{manager['Name']} (ID: {manager['id']})": manager['id'] for manager in managers}
            selected_manager = st.sidebar.selectbox("Select Manager", list(manager_options.keys()))
            manager_id = manager_options[selected_manager]
            
            password = st.sidebar.text_input("Password", type="password")
            
            if st.sidebar.button("Login as Manager"):
                manager = verify_manager_credentials(manager_id, password)
                if manager:
                    st.session_state.authenticated = True
                    st.session_state.current_user = "manager"
                    st.session_state.user_role = "manager"
                    st.session_state.manager_name = manager['Name']
                    st.rerun()
                elif password:
                    st.sidebar.error("Incorrect password")
        else:
            st.sidebar.warning("No managers found in database")
    
    elif role == "NHS Doctor":
        doctors = get_nhs_doctors()
        if doctors:
            doctor_options = {f"{doctor['name']} (ID: {doctor['id']})": doctor['id'] for doctor in doctors}
            selected_doctor = st.sidebar.selectbox("Select Doctor", list(doctor_options.keys()))
            doctor_id = doctor_options[selected_doctor]
            
            password = st.sidebar.text_input("Password", type="password")
            
            if st.sidebar.button("Login as NHS Doctor"):
                doctor = verify_nhs_doctor_credentials(doctor_id, password)
                if doctor:
                    st.session_state.authenticated = True
                    st.session_state.current_user = "nhs_doctor"
                    st.session_state.user_role = "nhs_doctor"
                    st.session_state.nhs_doctor_name = doctor['name']
                    st.rerun()
                elif password:
                    st.sidebar.error("Incorrect password")
        else:
            st.sidebar.warning("No NHS doctors found in database")


def logout():
    """Logout current user and cleanup resources."""
    # Stop unified analysis if running
    if st.session_state.get('all_apps_running', False):
        stop_unified_analysis()
    
    # Stop unified bot if running
    if st.session_state.get('unified_bot_running', False):
        stop_unified_bot()
    
    # Clear session state
    for key in ['authenticated', 'current_user', 'user_role', 'employee_name', 
                'manager_name', 'nhs_doctor_name', 'report_employee_id',
                'report_start_date', 'report_end_date', 'show_report_generator',
                'unified_bot_process', 'unified_bot_running']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def show_employee_dashboard():
    """Display dashboard for employee users with simplified graphs."""
    employee_id = st.session_state.current_user
    
    st.header(f"Welcome, {st.session_state.employee_name}")
    
    # Unified analysis controls
    st.subheader("Unified Real-time Analysis")
    
    # Telegram Bot Controls
    st.markdown("---")
    st.subheader("🤖 Telegram Bot for Alerts & Recommendations")
    
    # Display bot status
    status_col1, status_col2 = st.columns([1, 3])
    with status_col1:
        if st.session_state.unified_bot_running:
            st.success("✅ Bot Status: RUNNING")
        else:
            st.warning("⏹️ Bot Status: STOPPED")
    
    with status_col2:
        if st.session_state.unified_bot_running:
            st.info("Bot is monitoring posture and emotions in real-time")
        else:
            st.info("Start the bot to receive Telegram alerts")
    
    # Bot control buttons (SOLO PARA EMPLEADOS)
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 Start Bot", type="primary", use_container_width=True):
            if start_unified_bot():
                st.success("Telegram bot started successfully!")
                st.rerun()
    
    with col2:
        if st.button("🛑 Stop Bot", type="secondary", use_container_width=True):
            if stop_unified_bot():
                st.success("Telegram bot stopped successfully!")
                st.rerun()
    
    with col3:
        if st.button("📖 Instructions", use_container_width=True):
            # Show instructions in an expander
            with st.expander("Bot Instructions", expanded=True):
                st.markdown(get_bot_instructions())
    
    # Unified analysis controls (existing code)
    st.markdown("---")
    st.subheader("🖥️ Real-time Analysis Windows")
    st.write("Start both emotion and posture analysis windows:")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Unified Analysis", type="primary", key="start_unified"):
            if start_unified_analysis(employee_id):
                st.success("All applications started successfully!")
                st.info("Two windows will open: one for emotion analysis and one for posture analysis.")
                st.rerun()
    
    with col2:
        if st.button("Stop Unified Analysis", type="secondary", key="stop_unified"):
            if stop_unified_analysis():
                st.success("All applications stopped successfully!")
                st.rerun()
    
    st.info("""
    **Note:** This will start:
    1. Video Server (runs in background)
    2. Emotion Analysis Window (new console)
    3. Posture Analysis Window (new console)
    
    Press 'q' in each analysis window to close them.
    """)

    # Get current data
    emotions_data = get_emotions_data(employee_id)
    posture_data = get_posture_data(employee_id)
    
    if emotions_data.empty and posture_data.empty:
        st.warning("No data available for this employee yet.")
        return
    
    # Current metrics
    col1, col2 = st.columns(2)
    with col1:
        if not emotions_data.empty:
            latest_stress = emotions_data.iloc[0]
            st.metric("Current Stress Score", f"{latest_stress['stress_score']:.1f}", latest_stress.get('stress_level', 'N/A'))
    with col2:
        if not posture_data.empty:
            latest_posture = posture_data.iloc[0]
            st.metric("Current Posture Zone", int(latest_posture['overall_zone']), latest_posture.get('overall_risk', 'N/A'))
        else:
            st.info("No posture data available")
    
    # Trend visualizations (últimos 15 minutos, suavizadas)
    col1, col2 = st.columns(2)
    with col1:
        if not emotions_data.empty:
            st.subheader("Stress Level Trend (Last 15 Minutes)")
            
            # Filtrar últimos 15 minutos
            fifteen_minutes_ago = datetime.now() - timedelta(minutes=15)
            emotions_plot = emotions_data.copy()
            emotions_plot['created_at'] = emotions_plot['created_at'].dt.tz_localize(None)
            emotions_plot = emotions_plot[emotions_plot['created_at'] >= fifteen_minutes_ago]
            
            if not emotions_plot.empty:
                # Suavizar: eliminar duplicados por segundo
                emotions_plot = smooth_timeline_data(emotions_plot, 'created_at', 'stress_score', max_points=50)
                
                if len(emotions_plot) > 1:
                    # Crear gráfica simple con Plotly
                    fig_stress = px.line(
                        emotions_plot, 
                        x='created_at', 
                        y='stress_score',
                        title='Stress Score Over Time (Last 15 min)',
                        labels={'created_at': 'Time', 'stress_score': 'Stress Score'}
                    )
                    
                    # Configuración simple
                    fig_stress.update_layout(
                        height=300,
                        showlegend=False,
                        xaxis_title="Time",
                        yaxis_title="Stress Score"
                    )
                    
                    st.plotly_chart(fig_stress, use_container_width=True)
                else:
                    st.info("Insufficient data for stress timeline (after smoothing)")
            else:
                st.info("No data in the last 15 minutes")
    
    with col2:
        if not posture_data.empty:
            st.subheader("Posture Quality Trend (Last 15 Minutes)")
            
            # Filtrar últimos 15 minutos
            fifteen_minutes_ago = datetime.now() - timedelta(minutes=15)
            posture_plot = posture_data.copy()
            posture_plot['timestamp'] = posture_plot['timestamp'].dt.tz_localize(None)
            posture_plot = posture_plot[posture_plot['timestamp'] >= fifteen_minutes_ago]
            
            if not posture_plot.empty:
                # Suavizar: eliminar duplicados por segundo
                posture_plot = smooth_timeline_data(posture_plot, 'timestamp', 'overall_zone', max_points=50)
                
                if len(posture_plot) > 1:
                    # Crear gráfica simple con Plotly
                    fig_posture = px.line(
                        posture_plot, 
                        x='timestamp', 
                        y='overall_zone',
                        title='Posture Zone Over Time (Last 15 min)',
                        labels={'timestamp': 'Time', 'overall_zone': 'Posture Zone'}
                    )
                    
                    # Configuración simple
                    fig_posture.update_layout(
                        height=300,
                        showlegend=False,
                        xaxis_title="Time",
                        yaxis_title="Posture Zone"
                    )
                    
                    st.plotly_chart(fig_posture, use_container_width=True)
                else:
                    st.info("Insufficient data for posture timeline (after smoothing)")
            else:
                st.info("No data in the last 15 minutes")
    
    # Recent Data Table
    st.subheader("Recent Measurements")
    
    tabs = st.tabs(["Emotions", "Posture"])
    
    with tabs[0]:
        if not emotions_data.empty:
            # Mostrar últimos 10 registros de emociones
            recent_emotions = emotions_data.head(10).copy()
            recent_emotions['created_at'] = recent_emotions['created_at'].dt.strftime('%H:%M:%S')
            
            # Seleccionar columnas relevantes
            display_cols = ['created_at', 'emotion', 'stress_score', 'stress_level']
            display_df = recent_emotions[display_cols]
            
            st.dataframe(
                display_df,
                column_config={
                    "created_at": st.column_config.TextColumn("Time"),
                    "emotion": st.column_config.TextColumn("Emotion"),
                    "stress_score": st.column_config.NumberColumn("Stress Score", format="%.1f"),
                    "stress_level": st.column_config.TextColumn("Stress Level")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No emotion data available")
    
    with tabs[1]:
        if not posture_data.empty:
            # Mostrar últimos 10 registros de postura
            recent_posture = posture_data.head(10).copy()
            recent_posture['timestamp'] = recent_posture['timestamp'].dt.strftime('%H:%M:%S')
            
            # Seleccionar columnas relevantes
            display_cols = ['timestamp', 'overall_zone', 'overall_risk']
            display_df = recent_posture[display_cols]
            
            st.dataframe(
                display_df,
                column_config={
                    "timestamp": st.column_config.TextColumn("Time"),
                    "overall_zone": st.column_config.NumberColumn("Posture Zone", format="%d"),
                    "overall_risk": st.column_config.TextColumn("Risk Level")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No posture data available")
    
    # Auto-refresh indicator
    refresh_interval = 10  # Segundos
    current_time = datetime.now()
    time_since_refresh = (current_time - st.session_state.last_refresh).seconds
    time_until_refresh = max(0, refresh_interval - time_since_refresh)
    
    st.write(f"Next auto-refresh in: {time_until_refresh} seconds")
    
    # Auto-refresh logic
    if time_since_refresh >= refresh_interval:
        st.session_state.last_refresh = current_time
        st.rerun()


def show_manager_dashboard():
    """Display dashboard for manager users."""
    st.header(f"Manager Dashboard - {st.session_state.manager_name}")
    
    # Información sobre el bot para managers (SOLO INFORMACIÓN, SIN CONTROLES)
    st.subheader("🤖 Telegram Bot Information")
    
    # Mostrar estado del bot
    if st.session_state.unified_bot_running:
        st.success("✅ Telegram Bot Status: RUNNING")
        st.info("The Telegram bot is currently monitoring employees' posture and emotions.")
    else:
        st.warning("⏹️ Telegram Bot Status: STOPPED")
        st.info("The Telegram bot is not running. Employees can start it from their dashboard to receive alerts.")
    
    # Nota sobre restricciones de acceso
    with st.expander("📋 Bot Access Information"):
        st.write("""
        **Access Restrictions:**
        - ✅ **Employees:** Can start/stop the bot and receive alerts
        - ℹ️ **Managers:** Can view bot status but cannot control it
        - ℹ️ **NHS Doctors:** Can view bot status but cannot control it
        
        **Why?**
        The bot is designed for individual employee wellness monitoring. Each employee controls their own monitoring preferences.
        """)
    
    # Get all data
    all_emotions = get_emotions_data()
    all_posture = get_posture_data()
    
    if all_emotions.empty and all_posture.empty:
        st.warning("No data available in the database yet.")
        return
    
    # Employee selection for detailed view
    available_users = get_available_users()
    if available_users:
        selected_employee = st.selectbox(
            "Select Employee to View Detailed Data",
            available_users,
            format_func=get_user_display_name
        )
        
        if selected_employee:
            st.subheader(f"Detailed View: {get_user_display_name(selected_employee)}")
            
            employee_emotions = get_emotions_data(selected_employee)
            employee_posture = get_posture_data(selected_employee)
            
            if not employee_emotions.empty or not employee_posture.empty:
                # Current metrics for selected employee
                col1, col2 = st.columns(2)
                with col1:
                    if not employee_emotions.empty:
                        latest_stress = employee_emotions.iloc[0]
                        st.metric("Current Stress Score", f"{latest_stress['stress_score']:.1f}")
                with col2:
                    if not employee_posture.empty:
                        latest_posture = employee_posture.iloc[0]
                        st.metric("Current Posture Zone", int(latest_posture['overall_zone']))
    
    # Overview statistics
    st.subheader("Employee Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        unique_employees = len(available_users) if available_users else 0
        st.metric("Total Employees", unique_employees)
    with col2:
        if not all_emotions.empty:
            avg_stress = all_emotions['stress_score'].mean()
            st.metric("Average Stress Score", f"{avg_stress:.2f}")
    with col3:
        if not all_posture.empty:
            avg_posture = all_posture['overall_zone'].mean()
            st.metric("Average Posture Zone", f"{avg_posture:.2f}")
    
    # Comparative analysis
    st.subheader("Team Performance")
    col1, col2 = st.columns(2)
    
    with col1:
        if not all_emotions.empty:
            # Obtener datos suavizados para la tendencia general
            recent_emotions = all_emotions.copy()
            recent_emotions['created_at'] = recent_emotions['created_at'].dt.tz_localize(None)
            
            # Filtrar últimos 30 minutos para tendencia
            thirty_minutes_ago = datetime.now() - timedelta(minutes=30)
            recent_emotions = recent_emotions[recent_emotions['created_at'] >= thirty_minutes_ago]
            
            if not recent_emotions.empty:
                recent_emotions = smooth_timeline_data(recent_emotions, 'created_at', 'stress_score', max_points=30)
                
                if len(recent_emotions) > 1:
                    # Gráfica de tendencia general de estrés
                    fig_stress_trend = px.line(
                        recent_emotions, 
                        x='created_at', 
                        y='stress_score',
                        title='Overall Stress Trend (Last 30 min, smoothed)',
                        labels={'created_at': 'Time', 'stress_score': 'Avg Stress Score'}
                    )
                    
                    fig_stress_trend.update_layout(
                        height=300,
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_stress_trend, use_container_width=True)
    
    with col2:
        if not all_posture.empty:
            # Obtener datos suavizados para la tendencia general
            recent_posture = all_posture.copy()
            recent_posture['timestamp'] = recent_posture['timestamp'].dt.tz_localize(None)
            
            # Filtrar últimos 30 minutos para tendencia
            thirty_minutes_ago = datetime.now() - timedelta(minutes=30)
            recent_posture = recent_posture[recent_posture['timestamp'] >= thirty_minutes_ago]
            
            if not recent_posture.empty:
                recent_posture = smooth_timeline_data(recent_posture, 'timestamp', 'overall_zone', max_points=30)
                
                if len(recent_posture) > 1:
                    # Gráfica de tendencia general de postura
                    fig_posture_trend = px.line(
                        recent_posture, 
                        x='timestamp', 
                        y='overall_zone',
                        title='Overall Posture Trend (Last 30 min, smoothed)',
                        labels={'timestamp': 'Time', 'overall_zone': 'Avg Posture Zone'}
                    )
                    
                    fig_posture_trend.update_layout(
                        height=300,
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_posture_trend, use_container_width=True)
    
    # Auto-refresh indicator
    refresh_interval = 5
    current_time = datetime.now()
    time_since_refresh = (current_time - st.session_state.last_refresh).seconds
    time_until_refresh = max(0, refresh_interval - time_since_refresh)
    
    st.write(f"Next auto-refresh in: {time_until_refresh} seconds")
    
    if time_since_refresh >= refresh_interval:
        st.session_state.last_refresh = current_time
        st.rerun()


def main():
    """Main application entry point."""
    st.set_page_config(page_title="Employee Wellness Dashboard", layout="wide")
    
    # Show login if not authenticated
    if not st.session_state.authenticated:
        login()
        return
    
    # Display user info in sidebar
    if st.session_state.user_role == "employee" and st.session_state.employee_name:
        st.sidebar.success(f"Logged in as: {st.session_state.employee_name}")
    elif st.session_state.user_role == "manager" and st.session_state.manager_name:
        st.sidebar.success(f"Logged in as: {st.session_state.manager_name}")
    elif st.session_state.user_role == "nhs_doctor" and st.session_state.nhs_doctor_name:
        st.sidebar.success(f"Logged in as: Dr. {st.session_state.nhs_doctor_name}")
    
    # Navigation based on user role
    st.sidebar.header("Navigation")
    
    if st.session_state.user_role == "employee":
        page_options = ["Main Dashboard", "Report Generator", "Leaderboard"]
        page = st.sidebar.selectbox("Select Page", page_options)
    elif st.session_state.user_role == "manager":
        page_options = ["Main Dashboard", "Report Generator", "Leaderboard"]
        page = st.sidebar.selectbox("Select Page", page_options)
    elif st.session_state.user_role == "nhs_doctor":
        page_options = ["NHS Dashboard", "Report Generator"]
        page = st.sidebar.selectbox("Select Page", page_options)
    
    # Analysis Status in Sidebar (SOLO PARA EMPLEADOS)
    if st.session_state.user_role == "employee":
        # Unified analysis status
        st.sidebar.subheader("Analysis Status")
        
        # Bot status
        if st.session_state.unified_bot_running:
            st.sidebar.success("🤖 Telegram Bot: RUNNING")
        else:
            st.sidebar.warning("🤖 Telegram Bot: STOPPED")
        
        # Analysis windows status
        if st.session_state.all_apps_running:
            st.sidebar.success("🖥️ Analysis Windows: RUNNING")
            st.sidebar.info("• Video Server: Active")
            st.sidebar.info("• Emotion Analysis: Active")
            st.sidebar.info("• Posture Analysis: Active")
        else:
            st.sidebar.warning("🖥️ Analysis Windows: STOPPED")
    
    elif st.session_state.user_role == "manager":
        # Bot status for managers (solo información)
        st.sidebar.subheader("Telegram Bot Status")
        if st.session_state.unified_bot_running:
            st.sidebar.info("🤖 Bot: RUNNING")
        else:
            st.sidebar.info("🤖 Bot: STOPPED")
    
    elif st.session_state.user_role == "nhs_doctor":
        # Bot status for NHS doctors (solo información)
        st.sidebar.subheader("Telegram Bot Status")
        if st.session_state.unified_bot_running:
            st.sidebar.info("🤖 Bot: RUNNING")
        else:
            st.sidebar.info("🤖 Bot: STOPPED")
    
    # Logout button
    st.sidebar.button("Logout", on_click=logout)
    
    # Refresh data button
    if st.sidebar.button("Refresh Data"):
        st.rerun()
    
    # Route to selected page
    if page == "Main Dashboard":
        if st.session_state.user_role == "employee":
            show_employee_dashboard()
        elif st.session_state.user_role == "manager":
            show_manager_dashboard()
    elif page == "NHS Dashboard":
        show_nhs_dashboard()
    elif page == "Report Generator":
        show_report_generator()
    elif page == "Leaderboard":
        show_leaderboard()


if __name__ == "__main__":
    main()
