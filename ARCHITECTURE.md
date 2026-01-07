# Architecture Overview

## System Architecture

The Gait Analysis Platform is a multi-stage modular pipeline that transforms RGB video into clinical-grade biomechanical metrics.

### Pipeline Stages

1. **Perception Stack** (`app/services/perception_stack.py`)
   - High-fidelity pose estimation using HRNet or ViTPose
   - Fine-tuned for older adult populations
   - Supports assistive devices (canes/walkers)
   - Output: 2D keypoints with confidence scores

2. **3D Uplifting** (`app/services/lifting_3d.py`)
   - Temporal Transformer or T-GCN for 2D→3D conversion
   - Captures temporal dependencies
   - Output: 3D keypoint sequences

3. **Multi-View Fusion** (`app/services/multi_view_fusion.py`)
   - View-invariant feature extraction
   - Combines front, side, diagonal views
   - SMPL-X integration for anatomical consistency
   - Output: Unified biomechanical model

4. **Environmental Robustness** (`app/services/environmental_robustness.py`)
   - Scale calibration (reference objects or anthropometry)
   - Kalman filtering for denoising
   - Foot-ground contact constraints
   - Output: Metric-scaled, denoised keypoints

5. **Metrics Calculation** (`app/services/metrics_calculator.py`)
   - Clinical priority biomarkers
   - Spatiotemporal parameters
   - Joint kinematics
   - Output: Comprehensive gait metrics

6. **Quality Gating** (`app/services/quality_gate.py`)
   - Confidence threshold checks
   - Anatomical constraint validation
   - Temporal consistency verification
   - Output: Quality assessment and pass/fail decision

7. **Multi-Audience Reporting** (`app/services/reporting.py`)
   - Medical professionals: Technical dossier
   - Caregivers: Monitoring dashboard
   - Older adults: Intuitive summary
   - Output: Audience-specific reports

## Data Flow

```
Video Upload
    ↓
Pose Estimation (2D keypoints)
    ↓
3D Lifting (3D keypoints)
    ↓
Quality Gate Check
    ↓
Environmental Robustness
    ↓
Metrics Calculation
    ↓
Report Generation
    ↓
Storage & Delivery
```

## Key Components

### Backend (FastAPI)

- **API Layer** (`app/api/v1/`)
  - Analysis endpoints
  - Report endpoints
  - Health checks

- **Services Layer** (`app/services/`)
  - Core processing services
  - Business logic
  - External integrations

- **Core Layer** (`app/core/`)
  - Configuration
  - Database connections
  - Shared utilities

### Frontend (React + TypeScript)

- **Pages**
  - Home
  - Analysis Upload
  - Medical Dashboard
  - Caregiver Dashboard
  - Older Adult Dashboard

- **Components**
  - Layout
  - Shared UI components

### Azure Infrastructure

- **Storage Account**: Video files
- **Cosmos DB**: Analysis results and metadata
- **App Services**: Backend API and frontend
- **Key Vault**: Secrets management

## Clinical Metrics Priority

| Metric | Priority | Clinical Significance |
|--------|----------|----------------------|
| Gait Speed | High | 6th Vital Sign; predictor of hospitalization |
| Stride Variability | High | Motor control deterioration; fall-risk signal |
| Double Support Time | Medium | Fear of falling; postural instability |
| Step Asymmetry | Medium | Unilateral pain/weakness indicator |
| Knee/Toe Clearance | High | Trip risk identification |

## Quality Assurance

### Quality Gate Criteria

- Minimum joint confidence: 80%
- Minimum frame count: 30 frames
- Maximum missing joints per frame: 5
- Anatomical constraint validation
- Temporal consistency checks

### Fail-Safe Mechanisms

- Refuses analysis if quality thresholds not met
- Explicit error messages for failures
- Confidence bounds on all metrics
- Data quality flags in reports

## Validation Roadmap

1. **Phase 1**: Synchronized trials vs. IR-marker systems (ICC ≥ 0.85)
2. **Phase 2**: In-the-wild robustness testing
3. **Phase 3**: Prospective clinical validation (6-12 months)

## Scalability Considerations

- Horizontal scaling via Azure App Service
- Async processing for video analysis
- Blob storage for large video files
- Cosmos DB for scalable data storage
- Caching for frequently accessed reports

## Security

- HTTPS only
- CORS configuration
- Key Vault for secrets
- Input validation
- File size limits
- Supported format restrictions

## Performance Optimization

- Background task processing
- Model caching
- Efficient video processing
- Batch operations where possible
- Connection pooling



