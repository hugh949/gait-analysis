"""
3D Uplifting Module: Convert 2D keypoints to 3D space
Uses temporal transformer or T-GCN for temporal consistency
"""
import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional
from loguru import logger
import math

from app.core.config_simple import settings


class TemporalTransformer(nn.Module):
    """
    Temporal Transformer for 3D pose lifting
    Captures temporal dependencies across frames
    """
    
    def __init__(
        self,
        input_dim: int = 34,  # 17 joints * 2 (x, y)
        hidden_dim: int = 512,
        num_layers: int = 4,
        num_heads: int = 8,
        output_dim: int = 51  # 17 joints * 3 (x, y, z)
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        
        # Input projection
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        
        # Positional encoding
        self.pos_encoding = PositionalEncoding(hidden_dim)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=0.1,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output projection
        self.output_projection = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim) - 2D keypoints sequence
        Returns:
            (batch, seq_len, output_dim) - 3D keypoints sequence
        """
        # Project input
        x = self.input_projection(x)
        
        # Add positional encoding
        x = self.pos_encoding(x)
        
        # Apply transformer
        x = self.transformer(x)
        
        # Project to output
        x = self.output_projection(x)
        
        return x


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for temporal sequences"""
    
    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, :x.size(1)]


class TGCN(nn.Module):
    """
    Temporal Graph Convolutional Network for 3D pose lifting
    Alternative to transformer, uses graph structure of human skeleton
    """
    
    def __init__(
        self,
        input_dim: int = 2,
        hidden_dim: int = 256,
        num_layers: int = 3,
        output_dim: int = 3
    ):
        super().__init__()
        self.num_layers = num_layers
        
        # Build adjacency matrix for human skeleton
        self.adjacency = self._build_skeleton_graph()
        
        # Graph convolution layers
        self.gcn_layers = nn.ModuleList([
            GraphConvolution(input_dim if i == 0 else hidden_dim, hidden_dim)
            for i in range(num_layers)
        ])
        
        # Temporal convolution
        self.temporal_conv = nn.Conv1d(hidden_dim, hidden_dim, kernel_size=3, padding=1)
        
        # Output projection
        self.output_proj = nn.Linear(hidden_dim, output_dim)
    
    def _build_skeleton_graph(self) -> torch.Tensor:
        """Build adjacency matrix for human skeleton (COCO format)"""
        # Define skeleton connections
        connections = [
            (0, 1), (0, 2), (1, 3), (2, 4),  # Head
            (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # Arms
            (5, 11), (6, 12), (11, 12),  # Torso
            (11, 13), (13, 15), (12, 14), (14, 16)  # Legs
        ]
        
        num_joints = 17
        adj = torch.zeros(num_joints, num_joints)
        for i, j in connections:
            adj[i, j] = 1
            adj[j, i] = 1  # Undirected graph
        adj += torch.eye(num_joints)  # Self-connections
        
        return adj
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, num_joints, input_dim) - 2D keypoints
        Returns:
            (batch, seq_len, num_joints, output_dim) - 3D keypoints
        """
        batch, seq_len, num_joints, input_dim = x.shape
        adj = self.adjacency.to(x.device)
        
        # Reshape for processing
        x = x.view(batch * seq_len, num_joints, input_dim)
        
        # Apply graph convolutions
        for gcn in self.gcn_layers:
            x = gcn(x, adj)
            x = torch.relu(x)
        
        # Reshape back
        x = x.view(batch, seq_len, num_joints, -1)
        
        # Temporal convolution
        x = x.permute(0, 3, 1, 2)  # (batch, hidden, seq, joints)
        x = x.contiguous().view(batch * num_joints, -1, seq_len)
        x = self.temporal_conv(x)
        x = x.view(batch, num_joints, -1, seq_len)
        x = x.permute(0, 2, 3, 1)  # (batch, seq, hidden, joints)
        
        # Output projection
        x = self.output_proj(x)
        
        return x


class GraphConvolution(nn.Module):
    """Graph Convolutional Layer"""
    
    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)
    
    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        # Normalize adjacency matrix
        adj_normalized = self._normalize_adj(adj)
        # Graph convolution: A * X * W
        x = torch.matmul(adj_normalized, x)
        x = self.linear(x)
        return x
    
    def _normalize_adj(self, adj: torch.Tensor) -> torch.Tensor:
        """Normalize adjacency matrix"""
        rowsum = adj.sum(dim=1)
        d_inv_sqrt = torch.pow(rowsum, -0.5).flatten()
        d_inv_sqrt[torch.isinf(d_inv_sqrt)] = 0.0
        d_mat_inv_sqrt = torch.diag(d_inv_sqrt)
        return torch.matmul(torch.matmul(d_mat_inv_sqrt, adj), d_mat_inv_sqrt)


class Pose3DLifter:
    """
    Main service for 3D pose lifting
    Converts 2D keypoint sequences to 3D
    """
    
    def __init__(self, model_type: str = "transformer", device: str = "cuda"):
        self.model_type = model_type
        self.device = device if torch.cuda.is_available() else "cpu"
        self.model = self._load_model()
        self.model.eval()
        logger.info(f"3D lifter initialized with {model_type} on {self.device}")
    
    def _load_model(self) -> nn.Module:
        """Load 3D lifting model"""
        if self.model_type == "transformer":
            model = TemporalTransformer()
        elif self.model_type == "tgcn":
            model = TGCN()
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
        
        # Load pretrained weights if available
        if hasattr(settings, 'LIFTING_MODEL_PATH') and Path(settings.LIFTING_MODEL_PATH).exists():
            try:
                state_dict = torch.load(settings.LIFTING_MODEL_PATH, map_location=self.device)
                model.load_state_dict(state_dict)
                logger.info(f"Loaded pretrained weights from {settings.LIFTING_MODEL_PATH}")
            except Exception as e:
                logger.warning(f"Could not load pretrained weights: {e}")
        
        return model.to(self.device)
    
    def lift_to_3d(
        self,
        keypoints_2d: List[Dict[str, np.ndarray]],
        window_size: int = 30
    ) -> List[Dict[str, np.ndarray]]:
        """
        Lift 2D keypoints to 3D using temporal context
        
        Args:
            keypoints_2d: List of 2D keypoint dictionaries
            window_size: Temporal window size for processing
        
        Returns:
            List of 3D keypoint dictionaries
        """
        if len(keypoints_2d) < window_size:
            # Pad sequence if too short
            keypoints_2d = self._pad_sequence(keypoints_2d, window_size)
        
        results = []
        
        # Process in sliding windows
        for i in range(0, len(keypoints_2d), window_size // 2):
            window = keypoints_2d[i:i + window_size]
            if len(window) < window_size:
                window = self._pad_sequence(window, window_size)
            
            # Convert to tensor
            kp_array = np.array([kp['keypoints'] for kp in window])
            kp_tensor = torch.from_numpy(kp_array).float().unsqueeze(0).to(self.device)
            
            # Flatten for transformer input
            if self.model_type == "transformer":
                kp_tensor = kp_tensor.view(1, window_size, -1)
            
            # Predict 3D
            with torch.no_grad():
                kp_3d = self.model(kp_tensor)
            
            # Convert back to numpy
            if self.model_type == "transformer":
                kp_3d = kp_3d.view(window_size, 17, 3)
            else:
                kp_3d = kp_3d.squeeze(0)
            
            kp_3d_np = kp_3d.cpu().numpy()
            
            # Store results
            for j, kp_dict in enumerate(window):
                if i + j < len(keypoints_2d):
                    results.append({
                        'keypoints_3d': kp_3d_np[j],
                        'keypoints_2d': kp_dict['keypoints'],
                        'confidence': kp_dict['confidence'],
                        'frame_id': kp_dict.get('frame_id', i + j)
                    })
        
        return results
    
    def _pad_sequence(self, sequence: List, target_length: int) -> List:
        """Pad sequence to target length by repeating last frame"""
        if len(sequence) >= target_length:
            return sequence[:target_length]
        
        padded = sequence.copy()
        last_frame = sequence[-1] if sequence else None
        while len(padded) < target_length:
            if last_frame:
                padded.append(last_frame.copy())
            else:
                break
        
        return padded


# Import Path for model loading
from pathlib import Path



