"""
Tests for quality gate service
"""
import pytest
import numpy as np
from app.services.quality_gate import QualityGateService, QualityLevel


def test_quality_gate_initialization():
    """Test quality gate initialization"""
    gate = QualityGateService()
    assert gate.min_joint_confidence == 0.8
    assert gate.min_frame_count == 30


def test_check_frame_count():
    """Test frame count check"""
    gate = QualityGateService()
    
    # Too few frames
    result = gate._check_frame_count(20)
    assert result['status'] == QualityLevel.FAIL
    
    # Low but acceptable
    result = gate._check_frame_count(40)
    assert result['status'] == QualityLevel.WARNING
    
    # Sufficient frames
    result = gate._check_frame_count(100)
    assert result['status'] == QualityLevel.PASS


def test_check_joint_confidence():
    """Test joint confidence check"""
    gate = QualityGateService()
    
    num_frames = 60
    num_joints = 17
    
    # Low confidence
    low_confidence = np.ones((num_frames, num_joints)) * 0.5
    result = gate._check_joint_confidence(low_confidence, num_frames, num_joints)
    assert result['status'] == QualityLevel.FAIL
    
    # Good confidence
    good_confidence = np.ones((num_frames, num_joints)) * 0.9
    result = gate._check_joint_confidence(good_confidence, num_frames, num_joints)
    assert result['status'] == QualityLevel.PASS


def test_gate_analysis():
    """Test quick gate check"""
    gate = QualityGateService()
    
    # Good quality data
    keypoints_3d = np.random.rand(60, 17, 3) * 1000
    confidence = np.ones((60, 17)) * 0.9
    
    can_proceed, error_msg = gate.gate_analysis(keypoints_3d, confidence)
    assert can_proceed is True
    assert error_msg is None
    
    # Poor quality data
    bad_keypoints = np.random.rand(20, 17, 3) * 1000
    bad_confidence = np.ones((20, 17)) * 0.5
    
    can_proceed, error_msg = gate.gate_analysis(bad_keypoints, bad_confidence)
    assert can_proceed is False
    assert error_msg is not None



