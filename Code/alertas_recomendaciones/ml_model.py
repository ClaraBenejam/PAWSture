# ml_model.py
"""
Machine Learning model for P3FitRec recommendation system
Uses tensor decomposition for initialization and neural network for predictions
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import tensorly as tl
from tensorly.decomposition import parafac

tl.set_backend('pytorch')

class P3FitRecModel(nn.Module):
    """
    P3FitRec model adapted for 3 classes per activity:
    0 = reject
    1 = postpone
    2 = accept

    forward(user_idx, context_idx) -> logits with shape (B, n_activities, 3)
    """
    
    def __init__(self, n_users, n_contexts, n_activities, embedding_dim=8):
        """
        Initialize the P3FitRec model
        
        Args:
            n_users: Number of unique users
            n_contexts: Number of contexts (morning, afternoon, evening)
            n_activities: Number of activities
            embedding_dim: Dimension of embedding vectors
        """
        super().__init__()

        self.n_activities = n_activities
        self.n_classes = 3

        # Embeddings (Latent representation of user and context)
        self.user_embedding = nn.Embedding(n_users, embedding_dim)
        self.context_embedding = nn.Embedding(n_contexts, embedding_dim)

        # MLP: (User + Context) -> logits per activity and class
        input_dim = embedding_dim * 2
        self.fc1 = nn.Linear(input_dim, 32)
        self.dropout = nn.Dropout(0.2)

        # 3 logits per activity
        self.fc2 = nn.Linear(32, n_activities * self.n_classes)

    def forward(self, user_idx, context_idx):
        """
        Forward pass of the model
        
        Args:
            user_idx: Tensor of user indices [batch_size]
            context_idx: Tensor of context indices [batch_size]
            
        Returns:
            Tensor: Logits with shape [batch_size, n_activities, 3]
        """
        # Get embeddings
        u = self.user_embedding(user_idx)  # [batch_size, embedding_dim]
        c = self.context_embedding(context_idx)  # [batch_size, embedding_dim]

        # Concatenate vectors
        x = torch.cat([u, c], dim=-1)  # [batch_size, embedding_dim * 2]

        # Pass through MLP
        x = F.relu(self.fc1(x))  # [batch_size, 32]
        x = self.dropout(x)

        logits = self.fc2(x)  # [batch_size, n_activities * 3]
        logits = logits.view(-1, self.n_activities, self.n_classes)  # [batch_size, n_activities, 3]

        # IMPORTANT: we return logits (without softmax).
        # In training you'll use CrossEntropyLoss.
        # In inference you'll use softmax(logits_act) to calculate score.
        return logits

    def initialize_with_tensor_decomposition(self, tensor):
        """
        Uses PARAFAC (CP decomposition) to initialize weights (SOTA P3FitRec)
        
        Args:
            tensor: Interaction tensor [n_users, n_contexts, n_activities]
        """
        try:
            # Low-rank CP decomposition
            # This finds low-dimensional factors that approximate the tensor
            weights, factors = parafac(tensor, rank=self.user_embedding.embedding_dim, init='random')
            
            # Factor[0] = Users, Factor[1] = Contexts
            with torch.no_grad():
                if factors[0].shape == self.user_embedding.weight.shape:
                    self.user_embedding.weight.data = factors[0]
                if factors[1].shape == self.context_embedding.weight.shape:
                    self.context_embedding.weight.data = factors[1]
            print("✨ Embeddings initialized with Tensor Decomposition")
        except Exception as e:
            # This can fail if tensor is too sparse or dimensions don't match
            print(f"⚠️ Skip tensor decomp (insufficient data/dim error): {e}")
