"""
Leaderboard module for gamification display.
Shows employee rankings based on intervention points.
"""

import streamlit as st
import pandas as pd
import plotly.express as px

def show_leaderboard():
    """
    Display gamification leaderboard with rankings and visualizations.
    
    Shows:
    - Current rankings table
    - Summary statistics
    - Top 10 visualization
    - Refresh functionality
    """
    st.title("🏆 Gamification Leaderboard")
    st.markdown("---")
    
    try:
        # Try to import from cloud_db
        try:
            from cloud_db import get_gamification_leaderboard
        except ImportError as e:
            st.error(f"Cannot import leaderboard function: {e}")
            st.info("Please check if cloud_db.py exists and contains get_gamification_leaderboard() function.")
            return
        
        # Get leaderboard data
        leaderboard_data = get_gamification_leaderboard()
        
        if not leaderboard_data:
            st.warning("No leaderboard data available yet.")
            return
        
        # Convert to DataFrame
        try:
            df = pd.DataFrame(leaderboard_data)
            if df.empty:
                st.warning("Leaderboard data is empty.")
                return
                
            df.insert(0, "Rank", range(1, len(df) + 1))
            
            # Ensure Points is numeric
            if 'Points' in df.columns:
                df['Points'] = pd.to_numeric(df['Points'], errors='coerce').fillna(0)
                df['Points'] = df['Points'].round(1)
            else:
                st.error("Leaderboard data missing 'Points' column.")
                return
                
        except Exception as e:
            st.error(f"Error processing leaderboard data: {e}")
            return
        
        # Display current rankings
        st.subheader("🏅 Current Rankings")
        
        # Summary statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Players", len(df))
        with col2:
            if not df.empty:
                max_points = df['Points'].max()
                st.metric("Top Score", f"{max_points:.1f}")
            else:
                st.metric("Top Score", "0.0")
        with col3:
            if not df.empty:
                avg_points = df['Points'].mean()
                st.metric("Average Score", f"{avg_points:.1f}")
            else:
                st.metric("Average Score", "0.0")
        
        # Display table with styling
        try:
            st.dataframe(
                df,
                column_config={
                    "Rank": st.column_config.NumberColumn("Rank", width="small"),
                    "Name": st.column_config.TextColumn("Employee", width="medium"),
                    "Points": st.column_config.ProgressColumn(
                        "Points",
                        format="%.1f",
                        min_value=0,
                        max_value=float(df['Points'].max()) * 1.1 if not df.empty else 100,
                    ),
                },
                hide_index=True,
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error displaying leaderboard table: {e}")
            # Fallback to simple table
            st.dataframe(df, use_container_width=True)
        
        # Top 10 visualization
        if len(df) >= 3:  # Only show visualization if we have at least 3 players
            st.subheader("📊 Top Players Visualization")
            
            # Show top 10 or all if less than 10
            display_count = min(10, len(df))
            top_players = df.head(display_count)
            
            try:
                fig = px.bar(
                    top_players,
                    y="Name",
                    x="Points",
                    orientation="h",
                    title=f"Top {display_count} Employees",
                    color="Points",
                    color_continuous_scale="Viridis",
                    text="Points"
                )
                fig.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                fig.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    height=400 if display_count <= 10 else 600,
                    showlegend=False
                )
                
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Could not create visualization: {e}")
        
        # Refresh button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔄 Refresh Leaderboard", use_container_width=True):
                st.rerun()
                
    except Exception as e:
        st.error(f"Error loading leaderboard: {str(e)}")
        st.info("""
        **Troubleshooting:**
        1. Check if cloud_db.py exists and contains get_gamification_leaderboard() function
        2. Verify database connection is working
        3. Ensure the gamification table exists in Supabase
        """)
