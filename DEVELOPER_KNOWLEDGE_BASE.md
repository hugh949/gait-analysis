# Developer Knowledge Base
## Proactive Bug Prevention Guide

After 300+ builds, we've learned patterns that cause bugs. This guide helps prevent them proactively.

## App Overview

### Purpose
**Geriatric Gait Analysis Platform** - Transform basic RGB video into clinical-grade biomechanical metrics for:
- Fall risk assessment
- Functional mobility monitoring
- Professional gait lab-level parameters
- Multi-directional gait analysis

### Architecture
- **Backend**: FastAPI (Python) on Azure App Service
- **Frontend**: React (TypeScript) served from same App Service
- **Database**: Azure SQL (with file-based mock fallback)
- **Storage**: Azure Blob Storage (with file-based mock fallback)
- **AI**: MediaPipe 0.10.x for pose estimation

### Processing Pipeline
1. **Step 1: Pose Estimation** - Extract 2D keypoints from video (✅ WORKING)
2. **Step 2: 3D Lifting** - Convert 2D to 3D poses (✅ WORKING)
3. **Step 3: Metrics Calculation** - Calculate gait parameters (⚠️ HISTORICALLY PROBLEMATIC)
4. **Step 4: Report Generation** - Save results and mark complete (⚠️ HISTORICALLY PROBLEMATIC)

## Critical Code Integrity Rules

### ⚠️ NEVER MODIFY (These Work!)
- **Step 1 functions**: `_process_video_sync` (pose estimation)
- **Step 2 functions**: `_lift_to_3d` (3D lifting)
- **Upload endpoint**: Basic upload flow in `upload_video`
- **Service initialization**: `initialize_services()` pattern

### ✅ Safe to Modify
- Step 3: `_calculate_gait_metrics` and related validation
- Step 4: Completion logic, database updates
- Error handling and logging
- Frontend UI (but not core upload flow)

## Common Bug Patterns (Learn These!)

### 1. Import Errors ⚠️ HIGH FREQUENCY
**Pattern**: Importing functions from wrong modules
**Example**: `from app.services.gait_analysis import get_gait_analysis_service` ❌
**Correct**: `get_gait_analysis_service()` is defined in `analysis_azure.py`, not `gait_analysis.py`

**Prevention Checklist**:
- [ ] Verify function exists in target module before importing
- [ ] Check if function is in same file (no import needed)
- [ ] Use grep to find where function is actually defined
- [ ] Run syntax check: `python3 -m py_compile <file>`

**Where Functions Actually Live**:
- `get_gait_analysis_service()` → `backend/app/api/v1/analysis_azure.py` (line 92)
- `GaitAnalysisService` class → `backend/app/services/gait_analysis.py`
- `VideoQualityValidator` → `backend/app/services/video_quality_validator.py`
- `AzureSQLService` → `backend/app/core/database_azure_sql.py`

### 2. Service Initialization Issues
**Pattern**: Services not initialized or accessed incorrectly
**Example**: Calling `GaitAnalysisService()` directly instead of using singleton

**Prevention Checklist**:
- [ ] Always use `get_gait_analysis_service()` for gait service
- [ ] Check `db_service`, `storage_service` are initialized before use
- [ ] Services may be `None` - always check before use
- [ ] Services initialize at module load, but may fail gracefully

**Service Access Pattern**:
```python
# ✅ CORRECT
gait_service = get_gait_analysis_service()
if gait_service:
    # use it

# ❌ WRONG
from app.services.gait_analysis import GaitAnalysisService
service = GaitAnalysisService()  # Creates new instance, not singleton
```

### 3. Database Sync Issues
**Pattern**: Analysis created but immediately unreadable
**Example**: "Analysis not found" errors after creation

**Prevention Checklist**:
- [ ] Always verify analysis exists after `create_analysis()`
- [ ] In mock mode, check both in-memory AND file storage
- [ ] Use `_save_mock_storage(force_sync=True)` for critical saves
- [ ] Add retry logic with delays for file system sync
- [ ] Return `False` from `create_analysis()` if verification fails

**Database Pattern**:
```python
# ✅ CORRECT
creation_success = await db_service.create_analysis(data)
if not creation_success:
    raise DatabaseError("Failed to create analysis")

# Verify it's readable
verification_passed = False
for attempt in range(max_attempts):
    check = await db_service.get_analysis(analysis_id)
    if check and check.get('id') == analysis_id:
        verification_passed = True
        break
    await asyncio.sleep(0.1)

if not verification_passed:
    raise DatabaseError("Analysis created but not verifiable")
```

### 4. Metrics Overwriting (FIXED, but pattern important)
**Pattern**: Valid metrics replaced with fallback
**Example**: Step 3 generates good metrics, then code re-extracts and overwrites

**Prevention Checklist**:
- [ ] Never re-extract metrics after Step 3 completes
- [ ] Use metrics directly from `analysis_result`
- [ ] Validate metrics once, then use them
- [ ] Don't have fallback logic that overwrites valid data

### 5. Silent Failures
**Pattern**: Functions return empty/None instead of raising exceptions
**Example**: `_calculate_gait_metrics` returns `_empty_metrics()` on error

**Prevention Checklist**:
- [ ] Always raise exceptions for failures, never return empty data
- [ ] Use specific exception types: `GaitMetricsError`, `PoseEstimationError`
- [ ] Log errors before raising
- [ ] Let exceptions propagate to caller

### 6. Missing Validation
**Pattern**: Steps don't validate inputs from previous steps
**Example**: Step 3 processes without checking Step 2 data exists

**Prevention Checklist**:
- [ ] Step 3: Validate `frames_3d_keypoints` exists and is non-empty
- [ ] Step 4: Validate `metrics` exists and is not fallback
- [ ] Check data types and structure before processing
- [ ] Log validation results clearly

## File Structure & Dependencies

### Backend Structure
```
backend/
├── main_integrated.py          # FastAPI app entry point
├── app/
│   ├── api/v1/
│   │   └── analysis_azure.py   # Main API endpoints, service getters
│   ├── services/
│   │   ├── gait_analysis.py     # GaitAnalysisService class
│   │   ├── video_quality_validator.py  # VideoQualityValidator class
│   │   └── checkpoint_manager.py
│   └── core/
│       ├── database_azure_sql.py  # AzureSQLService class
│       ├── schemas.py              # Pydantic models
│       └── exceptions.py           # Custom exceptions
```

### Service Access Map
| Service | Class Location | Getter Function | Where Defined |
|---------|---------------|-----------------|---------------|
| Gait Analysis | `app/services/gait_analysis.py` | `get_gait_analysis_service()` | `app/api/v1/analysis_azure.py` |
| Database | `app/core/database_azure_sql.py` | `db_service` (global) | `app/api/v1/analysis_azure.py` |
| Storage | `app/services/azure_storage.py` | `storage_service` (global) | `app/api/v1/analysis_azure.py` |
| Vision | `app/services/azure_vision.py` | `vision_service` (global) | `app/api/v1/analysis_azure.py` |

## Pre-Deployment Checklist

Before committing any change:

1. **Import Validation**
   - [ ] Run `./scripts/proactive_validation.sh`
   - [ ] Check all imports resolve correctly
   - [ ] Verify functions exist in target modules

2. **Syntax Check**
   - [ ] `python3 -m py_compile backend/app/**/*.py`
   - [ ] No syntax errors

3. **Code Integrity**
   - [ ] Did I modify Step 1-2? If yes, STOP and reconsider
   - [ ] Did I modify upload endpoint core? If yes, verify it still works
   - [ ] Are changes minimal and targeted?

4. **Error Handling**
   - [ ] All database operations have try/except
   - [ ] Services checked for None before use
   - [ ] Exceptions are specific and informative

5. **Logging**
   - [ ] Added logging for new code paths
   - [ ] Logs include context (analysis_id, step, etc.)
   - [ ] Error logs include stack traces

6. **Testing**
   - [ ] Checked Azure logs before making change
   - [ ] Understand current behavior
   - [ ] Change addresses root cause, not symptom

## Common Import Patterns

### ✅ CORRECT Patterns
```python
# Service classes - import the class
from app.services.gait_analysis import GaitAnalysisService
from app.core.database_azure_sql import AzureSQLService

# Service getters - use function in same file or import from correct location
gait_service = get_gait_analysis_service()  # Defined in analysis_azure.py

# Exceptions - import from core
from app.core.exceptions import GaitMetricsError, DatabaseError

# Schemas - import from core
from app.core.schemas import AnalysisDetailResponse
```

### ❌ WRONG Patterns
```python
# Don't import getter functions from service modules
from app.services.gait_analysis import get_gait_analysis_service  # ❌ Doesn't exist

# Don't create new service instances directly
service = GaitAnalysisService()  # ❌ Breaks singleton pattern

# Don't import from wrong locations
from app.api.v1.analysis_azure import GaitAnalysisService  # ❌ Wrong module
```

## Deployment Workflow

1. **Check Logs First** (STANDARD_PRACTICES.md)
   ```bash
   ./scripts/fetch_azure_logs_filtered.sh "ERROR|Exception"
   ```

2. **Run Proactive Validation**
   ```bash
   ./scripts/proactive_validation.sh
   ```

3. **Make Minimal Change**
   - Fix only the specific issue
   - Don't refactor working code
   - Add targeted logging

4. **Test Locally** (if possible)
   ```bash
   python3 -m py_compile backend/app/**/*.py
   ```

5. **Commit with Clear Message**
   - What was changed
   - Why it was changed
   - What issue it fixes

6. **Monitor After Deployment**
   - Check Azure logs
   - Verify fix worked
   - Look for new issues

## Learning from History

### What We've Learned (300+ Builds)

1. **Import errors are #1 cause of 500 errors**
   - Always verify imports before committing
   - Use grep to find where functions actually are

2. **Database sync is fragile**
   - Always verify after create
   - Use retries with delays
   - Check both memory and file

3. **Metrics overwriting breaks everything**
   - Never re-extract after Step 3
   - Use metrics directly from result

4. **Silent failures hide problems**
   - Always raise exceptions
   - Don't return empty data

5. **Missing validation causes cascading failures**
   - Validate at every step transition
   - Check data exists and is valid

6. **Code integrity matters**
   - Don't break working Steps 1-2
   - Minimal, targeted changes only

## Quick Reference

### Where Things Are
- **API Endpoints**: `backend/app/api/v1/analysis_azure.py`
- **Gait Analysis Logic**: `backend/app/services/gait_analysis.py`
- **Database Layer**: `backend/app/core/database_azure_sql.py`
- **Video Validation**: `backend/app/services/video_quality_validator.py`
- **Main App**: `backend/main_integrated.py`

### Common Commands
```bash
# Check syntax
python3 -m py_compile backend/app/**/*.py

# Run validation
./scripts/proactive_validation.sh

# Check logs
./scripts/fetch_azure_logs_filtered.sh "ERROR"

# Test imports
python3 -c "from app.api.v1.analysis_azure import get_gait_analysis_service; print('OK')"
```

## Remember

**After 300+ builds, we know:**
- Import errors are the #1 bug
- Always verify before importing
- Check logs before changing code
- Minimal changes prevent breaking things
- Code integrity is critical
- Validation prevents cascading failures

**Use this knowledge proactively, not reactively.**
