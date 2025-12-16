# data_loader.py
"""
Data loader for recommendation system training
Handles data fetching from Supabase and preprocessing for ML model
"""
import pandas as pd
import torch
import numpy as np

class DataLoader:
    def __init__(self, supabase_client, valid_activities):
        """
        Initialize data loader
        
        Args:
            supabase_client: Supabase client instance
            valid_activities: List of valid activity names
        """
        self.supabase = supabase_client
        self.valid_activities = valid_activities

        # Mappings for converting categorical data to indices
        self.user_map = {}
        self.user_map_inv = {}
        self.activity_map = {name: i for i, name in enumerate(valid_activities)}
        self.activity_map_inv = {i: name for name, i in self.activity_map.items()}

        # Context and response mappings
        self.context_map = {'morning': 0, 'afternoon': 1, 'evening': 2}
        self.response_to_label = {'reject': 0, 'postpone': 1, 'accept': 2}
        self.response_to_reward = {'accept': 1.0, 'postpone': 0.1, 'reject': -1.0}

    def fetch_data(self):
        """
        Downloads response history for training from Supabase
        
        Returns:
            DataFrame: Processed training data or None if error
        """
        try:
            print("📥 Downloading data from Supabase...")
            
            # 1) Responses (feedback)
            resp = self.supabase.table("recommendation_responses").select("*").execute()
            df_resp = pd.DataFrame(resp.data)
            print(f"📊 Responses obtained: {len(df_resp)}")
            
            if df_resp.empty:
                print("⚠️ No responses in database")
                return None

            # 2) Recommendations (metadata)
            rec_resp = self.supabase.table("recommendations").select("id, recommendation_type, name, created_at").execute()
            df_recs = pd.DataFrame(rec_resp.data)
            print(f"📊 Recommendations obtained: {len(df_recs)}")
            
            if df_recs.empty:
                print("⚠️ No recommendations in database")
                return None

            # 3) Join tables - CORRECTED: use actual column name
            # Check available columns
            print(f"📋 Columns in df_resp: {df_resp.columns.tolist()}")
            print(f"📋 Columns in df_recs: {df_recs.columns.tolist()}")
            
            # Assume join column is 'recommendation_id' in df_resp and 'id' in df_recs
            df = pd.merge(df_resp, df_recs, left_on="recommendation_id", right_on="id")
            print(f"📊 Data after join: {len(df)} rows")

            if df.empty:
                print("⚠️ No data after joining tables")
                return None

            # 4) Verify 'created_at' column exists
            if 'created_at' not in df.columns:
                print("❌ ERROR: 'created_at' column doesn't exist after join")
                # Try with another column
                if 'created_at_x' in df.columns:
                    df.rename(columns={'created_at_x': 'created_at'}, inplace=True)
                    print("✅ Using 'created_at_x' as 'created_at'")
                elif 'created_at_y' in df.columns:
                    df.rename(columns={'created_at_y': 'created_at'}, inplace=True)
                    print("✅ Using 'created_at_y' as 'created_at'")
                else:
                    print("❌ No date column found")
                    return None

            # 5) Process dates
            df['created_at'] = pd.to_datetime(df['created_at'], errors="coerce")
            df = df.dropna(subset=['created_at'])
            print(f"📊 Data after processing dates: {len(df)} rows")
            
            if df.empty:
                return None

            # 6) Context based on hour
            df['hour'] = df['created_at'].dt.hour
            conditions = [
                (df['hour'] < 12),
                (df['hour'] >= 12) & (df['hour'] < 18),
                (df['hour'] >= 18)
            ]
            choices = ['morning', 'afternoon', 'evening']
            df['context'] = np.select(conditions, choices, default='afternoon')

            # 7) reward and label
            df['reward'] = df['response'].map(self.response_to_reward)
            df['label'] = df['response'].map(self.response_to_label)
            
            # Remove rows without reward/label
            df = df.dropna(subset=['reward', 'label'])
            print(f"📊 Final training data: {len(df)} rows")

            # 8) Ensure types - IMPORTANT: user_id is now the triggered_user_id
            df['user_id'] = df['user_id'].astype(str)  # Convert to string for consistency
            df['name'] = df['name'].astype(str)
            df['label'] = df['label'].astype(int)

            # 9) Debug: show user distribution
            print("📊 User distribution in data:")
            print(df['user_id'].value_counts())

            return df

        except Exception as e:
            print(f"❌ Error in DataLoader.fetch_data: {e}")
            import traceback
            traceback.print_exc()
            return None

    def build_tensor(self, df):
        """
        Builds interaction tensor from DataFrame
        
        Args:
            df: DataFrame with user, context, activity, and reward data
            
        Returns:
            Tensor: 3D tensor [users, contexts, activities] with reward values
        """
        try:
            # Create user mapping
            unique_users = df['user_id'].unique()
            self.user_map = {str(uid): i for i, uid in enumerate(unique_users)}
            self.user_map_inv = {i: str(uid) for uid, i in self.user_map.items()}

            n_users = len(self.user_map)
            n_contexts = len(self.context_map)
            n_activities = len(self.activity_map)

            print(f"🧮 Tensor dimensions: {n_users} users, {n_contexts} contexts, {n_activities} activities")
            
            # Initialize tensor with zeros
            tensor = torch.zeros((n_users, n_contexts, n_activities))

            # Fill tensor with reward values
            for _, row in df.iterrows():
                u_str = str(row['user_id'])
                if u_str not in self.user_map:
                    continue

                u_idx = self.user_map[u_str]
                c_idx = self.context_map.get(row['context'], 1)

                act_name = row.get('name')
                if act_name not in self.activity_map:
                    continue

                a_idx = self.activity_map[act_name]
                tensor[u_idx, c_idx, a_idx] = float(row['reward'])

            print(f"✅ Tensor built with {tensor.numel()} elements")
            return tensor
            
        except Exception as e:
            print(f"❌ Error in DataLoader.build_tensor: {e}")
            import traceback
            traceback.print_exc()
            return torch.zeros((1, 3, len(self.activity_map)))  # Empty tensor

    def build_training_samples(self, df, return_reward=False):
        """
        Returns a list of training samples for 3-class classification
        
        Args:
            df: DataFrame with training data
            return_reward: Whether to include reward in samples
            
        Returns:
            list: Training samples [(user_idx, context_idx, activity_idx, label, (optional) reward)]
        """
        try:
            samples = []

            for _, row in df.iterrows():
                u_str = str(row['user_id'])
                if u_str not in self.user_map:
                    continue

                u_idx = self.user_map[u_str]
                c_idx = self.context_map.get(row['context'], 1)

                act_name = row.get('name')
                if act_name not in self.activity_map:
                    continue

                a_idx = self.activity_map[act_name]
                label = int(row['label'])
                reward = float(row['reward'])

                if return_reward:
                    samples.append((u_idx, c_idx, a_idx, label, reward))
                else:
                    samples.append((u_idx, c_idx, a_idx, label))

            print(f"✅ Training samples: {len(samples)}")
            return samples
            
        except Exception as e:
            print(f"❌ Error in DataLoader.build_training_samples: {e}")
            return []