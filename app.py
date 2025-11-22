import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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

def get_emotions_data(user_id=None):
    """Fetch emotions data from Supabase"""
    try:
        query = supabase.table("emotions").select("*").order("created_at", desc=True)
        if user_id and user_id != "manager":
            query = query.eq("id_usuario", user_id)
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
    """Fetch posture data from Supabase"""
    try:
        query = supabase.table("posture").select("*").order("timestamp", desc=True)
        if user_id and user_id != "manager":
            query = query.eq("id_usuario", user_id)
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
    """Get list of available users from the database"""
    try:
        # Get unique users from emotions table
        emotions_response = supabase.table("emotions").select("id_usuario").execute()
        posture_response = supabase.table("posture").select("id_usuario").execute()
        
        users = set()
        if hasattr(emotions_response, 'data') and emotions_response.data:
            users.update([user['id_usuario'] for user in emotions_response.data if user['id_usuario'] is not None])
        if hasattr(posture_response, 'data') and posture_response.data:
            users.update([user['id_usuario'] for user in posture_response.data if user['id_usuario'] is not None])
        
        return sorted(list(users))
    except Exception as e:
        st.error(f"Error fetching users: {e}")
        return []

def get_user_display_name(user_id):
    """Convert user ID to display name"""
    return f"Employee {user_id}"

# Authentication system
def login():
    st.sidebar.header("Login")
    
    role = st.sidebar.selectbox("Select Role", ["Employee", "Manager"])
    
    if role == "Employee":
        available_users = get_available_users()
        if available_users:
            user_options = {get_user_display_name(user_id): user_id 
                          for user_id in available_users}
            selected_employee = st.sidebar.selectbox("Select Employee", 
                                                   list(user_options.keys()))
            employee_id = user_options[selected_employee]
            
            # Employee password
            password = st.sidebar.text_input("Employee Password", type="password")
            
            if st.sidebar.button("Login as Employee"):
                if password == "employee123":
                    st.session_state.authenticated = True
                    st.session_state.current_user = employee_id
                    st.session_state.user_role = "employee"
                    st.rerun()
                elif password:
                    st.sidebar.error("Incorrect password")
        else:
            st.sidebar.warning("No employee data found in database")
    
    elif role == "Manager":
        password = st.sidebar.text_input("Manager Password", type="password")
        if st.sidebar.button("Login as Manager"):
            if password == "manager123":
                st.session_state.authenticated = True
                st.session_state.current_user = "manager"
                st.session_state.user_role = "manager"
                st.rerun()
            elif password:
                st.sidebar.error("Incorrect password")

def logout():
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.session_state.user_role = None
    st.rerun()

# Main application
def main():
    st.set_page_config(page_title="Employee Wellness Dashboard", layout="wide")
    
    st.title("Employee Wellness Dashboard")
    
    if not st.session_state.authenticated:
        login()
        return
    
    # Logout button
    st.sidebar.button("Logout", on_click=logout)
    
    if st.session_state.user_role == "employee":
        show_employee_dashboard()
    elif st.session_state.user_role == "manager":
        show_manager_dashboard()

def show_employee_dashboard():
    employee_id = st.session_state.current_user
    employee_name = get_user_display_name(employee_id)
    
    st.header(f"Welcome, {employee_name}")
    
    # Fetch data for this employee
    with st.spinner("Loading your data..."):
        emotions_data = get_emotions_data(employee_id)
        posture_data = get_posture_data(employee_id)
    
    if emotions_data.empty and posture_data.empty:
        st.warning("No data available for this employee yet.")
        return
    
    # Display metrics
    col1, col2 = st.columns(2)
    
    with col1:
        if not emotions_data.empty:
            latest_stress = emotions_data.iloc[0]  # Most recent record
            st.metric(
                "Current Stress Score", 
                f"{latest_stress['stress_score']:.1f}",
                latest_stress.get('stress_level', 'N/A')
            )
    
    with col2:
        if not posture_data.empty:
            latest_posture = posture_data.iloc[0]  # Most recent record
            st.metric(
                "Current Posture Zone", 
                latest_posture['overall_zone'],
                latest_posture.get('overall_risk', 'N/A')
            )
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        if not emotions_data.empty:
            st.subheader("Stress Level Trend")
            # Get last 30 records or all if less
            chart_data = emotions_data.head(30).sort_values('created_at')
            if len(chart_data) > 1:
                fig_stress = px.line(
                    chart_data, 
                    x='created_at', 
                    y='stress_score',
                    title='Stress Score Over Time',
                    labels={'stress_score': 'Stress Score', 'created_at': 'Date'}
                )
                st.plotly_chart(fig_stress, use_container_width=True)
            else:
                st.info("Not enough data points for trend analysis")
    
    with col2:
        if not posture_data.empty:
            st.subheader("Posture Quality Trend")
            # Get last 30 records or all if less
            chart_data = posture_data.head(30).sort_values('timestamp')
            if len(chart_data) > 1:
                fig_posture = px.line(
                    chart_data, 
                    x='timestamp', 
                    y='overall_zone',
                    title='Posture Zone Over Time',
                    labels={'overall_zone': 'Posture Zone', 'timestamp': 'Date'}
                )
                st.plotly_chart(fig_posture, use_container_width=True)
            else:
                st.info("Not enough data points for trend analysis")

def show_manager_dashboard():
    st.header("Manager Dashboard - All Employee Data")
    
    # Fetch all data
    with st.spinner("Loading all employee data..."):
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
            
            # Get data for selected employee
            employee_emotions = all_emotions[all_emotions['id_usuario'] == selected_employee]
            employee_posture = all_posture[all_posture['id_usuario'] == selected_employee]
            
            if not employee_emotions.empty or not employee_posture.empty:
                # Display metrics for selected employee
                col1, col2 = st.columns(2)
                
                with col1:
                    if not employee_emotions.empty:
                        latest_stress = employee_emotions.iloc[0]
                        st.metric(
                            "Current Stress Score", 
                            f"{latest_stress['stress_score']:.1f}",
                            latest_stress.get('stress_level', 'N/A')
                        )
                
                with col2:
                    if not employee_posture.empty:
                        latest_posture = employee_posture.iloc[0]
                        st.metric(
                            "Current Posture Zone", 
                            latest_posture['overall_zone'],
                            latest_posture.get('overall_risk', 'N/A')
                        )
                
                # Charts for selected employee
                col1, col2 = st.columns(2)
                
                with col1:
                    if not employee_emotions.empty:
                        st.subheader("Stress Level Trend")
                        chart_data = employee_emotions.head(30).sort_values('created_at')
                        if len(chart_data) > 1:
                            fig_stress = px.line(
                                chart_data, 
                                x='created_at', 
                                y='stress_score',
                                title='Stress Score Over Time',
                                labels={'stress_score': 'Stress Score', 'created_at': 'Date'}
                            )
                            st.plotly_chart(fig_stress, use_container_width=True)
                        else:
                            st.info("Not enough data points for trend analysis")
                
                with col2:
                    if not employee_posture.empty:
                        st.subheader("Posture Quality Trend")
                        chart_data = employee_posture.head(30).sort_values('timestamp')
                        if len(chart_data) > 1:
                            fig_posture = px.line(
                                chart_data, 
                                x='timestamp', 
                                y='overall_zone',
                                title='Posture Zone Over Time',
                                labels={'overall_zone': 'Posture Zone', 'timestamp': 'Date'}
                            )
                            st.plotly_chart(fig_posture, use_container_width=True)
                        else:
                            st.info("Not enough data points for trend analysis")
            else:
                st.info("No data available for selected employee")
    
    # Overview section with all employees
    st.subheader("Employee Overview")
    
    # Display overview metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        unique_employees = len(available_users)
        st.metric("Total Employees", unique_employees)
    
    with col2:
        if not all_emotions.empty:
            avg_stress = all_emotions['stress_score'].mean()
            st.metric("Average Stress Score", f"{avg_stress:.2f}")
    
    with col3:
        if not all_posture.empty:
            avg_posture = all_posture['overall_zone'].mean()
            st.metric("Average Posture Zone", f"{avg_posture:.2f}")
    
    # Comparative charts for all employees
    st.subheader("Comparative Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if not all_emotions.empty:
            st.subheader("Stress Levels - All Employees")
            # Get recent data for all employees (last 7 days per employee)
            recent_emotions = all_emotions.groupby('id_usuario').head(7)
            
            fig_stress_comparative = px.line(
                recent_emotions,
                x='created_at',
                y='stress_score',
                color='id_usuario',
                title='Stress Scores - All Employees',
                labels={'stress_score': 'Stress Score', 'created_at': 'Date', 'id_usuario': 'Employee'}
            )
            st.plotly_chart(fig_stress_comparative, use_container_width=True)
    
    with col2:
        if not all_posture.empty:
            st.subheader("Posture Quality - All Employees")
            # Get recent data for all employees (last 7 days per employee)
            recent_posture = all_posture.groupby('id_usuario').head(7)
            
            fig_posture_comparative = px.line(
                recent_posture,
                x='timestamp',
                y='overall_zone',
                color='id_usuario',
                title='Posture Zones - All Employees',
                labels={'overall_zone': 'Posture Zone', 'timestamp': 'Date', 'id_usuario': 'Employee'}
            )
            st.plotly_chart(fig_posture_comparative, use_container_width=True)
    
    # Raw data tables
    st.subheader("Raw Data")
    tab1, tab2 = st.tabs(["Stress Data", "Posture Data"])
    
    with tab1:
        if not all_emotions.empty:
            display_emotions = all_emotions[['id_usuario', 'stress_score', 'stress_level', 'emotion', 'created_at']].copy()
            display_emotions['employee'] = display_emotions['id_usuario'].apply(get_user_display_name)
            st.dataframe(display_emotions.drop('id_usuario', axis=1), use_container_width=True)
        else:
            st.info("No stress data available")
    
    with tab2:
        if not all_posture.empty:
            display_posture = all_posture[['id_usuario', 'overall_zone', 'overall_risk', 'timestamp']].copy()
            display_posture['employee'] = display_posture['id_usuario'].apply(get_user_display_name)
            st.dataframe(display_posture.drop('id_usuario', axis=1), use_container_width=True)
        else:
            st.info("No posture data available")

if __name__ == "__main__":
    main()