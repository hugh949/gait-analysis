"""
Tests for metrics calculator
"""
import pytest
import numpy as np
from app.services.metrics_calculator import GaitMetricsCalculator, GaitMetrics


def test_gait_metrics_calculator_initialization():
    """Test calculator initialization"""
    calculator = GaitMetricsCalculator(fps=30.0)
    assert calculator.fps == 30.0
    assert calculator.dt == 1.0 / 30.0


def test_calculate_gait_speed():
    """Test gait speed calculation"""
    calculator = GaitMetricsCalculator(fps=30.0)
    
    # Create mock keypoints with forward progression
    num_frames = 60
    num_joints = 17
    keypoints_3d = np.zeros((num_frames, num_joints, 3))
    
    # Simulate forward movement
    for i in range(num_frames):
        keypoints_3d[i, 11, 0] = i * 10  # Left hip forward
        keypoints_3d[i, 12, 0] = i * 10  # Right hip forward
    
    # Mock gait events
    gait_events = {
        'left_heel_strike': [0, 30, 60],
        'right_heel_strike': [15, 45],
        'left_toe_off': [10, 40],
        'right_toe_off': [25, 55]
    }
    
    speed = calculator._calculate_gait_speed(keypoints_3d, gait_events)
    assert speed > 0
    assert isinstance(speed, float)


def test_calculate_stride_variability():
    """Test stride variability calculation"""
    calculator = GaitMetricsCalculator(fps=30.0)
    
    keypoints_3d = np.random.rand(60, 17, 3) * 1000
    gait_events = {
        'left_heel_strike': [0, 30, 60, 90],
        'right_heel_strike': [15, 45, 75],
        'left_toe_off': [],
        'right_toe_off': []
    }
    
    variability = calculator._calculate_stride_variability(keypoints_3d, gait_events)
    assert isinstance(variability, float)
    assert variability >= 0


@pytest.mark.skip(reason="Requires full pipeline")
def test_calculate_all_metrics():
    """Test complete metrics calculation"""
    calculator = GaitMetricsCalculator(fps=30.0)
    
    # Create realistic keypoint sequence
    num_frames = 90
    num_joints = 17
    keypoints_3d = np.random.rand(num_frames, num_joints, 3) * 1000
    confidence = np.ones((num_frames, num_joints)) * 0.9
    
    metrics = calculator.calculate_all_metrics(keypoints_3d, confidence)
    
    assert isinstance(metrics, GaitMetrics)
    assert metrics.gait_speed_mm_per_s >= 0
    assert metrics.overall_confidence > 0



