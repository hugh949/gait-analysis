# Focused Plan: Complete Steps 3 & 4 Successfully

## Current Status
- **Build Count**: 350+ builds without a single successful completion
- **Working**: Steps 1 (Pose Estimation) and Step 2 (3D Lifting) ✅
- **Broken**: Steps 3 (Metrics Calculation) and Step 4 (Report Generation) ❌

## Code Integrity Principle
**DO NOT modify Steps 1-2 or upload endpoint. Only fix Steps 3-4.**

## Root Causes Already Fixed (Verified)
1. ✅ Metrics re-extraction block removed (line 1759: "DO NOT re-extract")
2. ✅ Checkpoint early return removed (line 294-310: logs but doesn't skip)
3. ✅ Silent failures → exceptions (lines 1398-1411: raises GaitMetricsError)
4. ✅ Input validation added (lines 825-852: Step 3 validates Step 2 data)
5. ✅ Database retry logic enhanced (lines 1900-1999: 15 retries with verification)

## Focused Verification Plan

### Step 3 Verification Points
1. **Data Flow Check**: Verify `frames_3d_keypoints` from Step 2 reaches Step 3
   - Location: `gait_analysis.py` line 825-852
   - Log: `✅ Step 3 validation passed: X 3D keypoint frames`
   - Action: If missing, Step 2 is failing silently

2. **Metrics Calculation Call**: Verify `_calculate_gait_metrics` is actually called
   - Location: `gait_analysis.py` line 855+
   - Log: `🔍 Calling _calculate_gait_metrics with X frames...`
   - Action: If not called, check why Step 3 is skipping

3. **Metrics Return**: Verify metrics are returned (not empty)
   - Location: `gait_analysis.py` line 1026-1064
   - Log: `✅ Gait metrics calculated in X.XXs: X metrics`
   - Action: If empty, `_calculate_gait_metrics` is failing

4. **Result Validation**: Verify metrics are in `analysis_result`
   - Location: `gait_analysis.py` line 1026-1064
   - Log: `✅ Metrics in result: X metrics, has_core=True`
   - Action: If missing, result construction is broken

### Step 4 Verification Points
1. **Metrics Reception**: Verify Step 4 receives metrics from Step 3
   - Location: `analysis_azure.py` line 1662
   - Log: `🔍 Metrics validation: has_metrics=True, count=X, is_fallback=False`
   - Action: If missing/fallback, Step 3 didn't complete properly

2. **Database Update**: Verify status update to 'completed' succeeds
   - Location: `analysis_azure.py` line 1924-1955
   - Log: `✅ Verification passed - analysis marked as completed with metrics`
   - Action: If fails, database connection/update is broken

3. **Report Availability**: Verify report is viewable after completion
   - Location: Frontend `Report.tsx`
   - Action: If 404, database query or route is broken

## Targeted Fixes (Minimal Changes Only)

### Fix 1: Add Step Transition Logging
**Purpose**: Track exact data flow between steps
**Location**: `gait_analysis.py` `_process_video_sync`
**Change**: Add logging at each step transition showing data counts

### Fix 2: Verify Metrics Structure
**Purpose**: Ensure metrics dict structure is correct
**Location**: `gait_analysis.py` `_calculate_gait_metrics` return
**Change**: Validate metrics dict has required keys before returning

### Fix 3: Add Completion Verification Endpoint
**Purpose**: Allow manual verification of completion status
**Location**: `analysis_azure.py` (new endpoint)
**Change**: Add `/api/v1/analysis/{id}/verify-completion` to check status

### Fix 4: Enhanced Error Messages
**Purpose**: Make failures obvious in logs
**Location**: All Step 3/4 error points
**Change**: Add clear error messages with step context

## Testing Strategy

### Test 1: Step 3 Data Flow
1. Upload video
2. Wait for Step 2 to complete
3. Check logs for: `✅ Step 3 validation passed`
4. Check logs for: `🔍 Calling _calculate_gait_metrics`
5. Check logs for: `✅ Gait metrics calculated`

### Test 2: Step 4 Completion
1. After Step 3 completes
2. Check logs for: `🔍 Metrics validation: has_metrics=True`
3. Check logs for: `✅ Verification passed - analysis marked as completed`
4. Check database: `status='completed'` and `metrics` exists
5. Try to view report

### Test 3: End-to-End
1. Upload video
2. Monitor logs for each step transition
3. Verify report is viewable
4. If fails, logs show exact failure point

## Success Criteria
- ✅ Step 3 processes data (takes real time, not instant)
- ✅ Step 3 returns metrics (not empty, not fallback)
- ✅ Step 4 receives metrics from Step 3
- ✅ Step 4 updates database to 'completed'
- ✅ Report is viewable in frontend
- ✅ All 4 steps complete in single run

## Next Steps
1. Add minimal targeted logging (Fix 1)
2. Verify metrics structure (Fix 2)
3. Deploy and test
4. Check logs for exact failure point
5. Apply targeted fix based on logs
6. Repeat until all 4 steps complete

## Code Integrity Checklist
Before any change:
- [ ] Does this change affect Steps 1-2? If yes, DON'T DO IT
- [ ] Does this change affect upload endpoint? If yes, DON'T DO IT
- [ ] Is this change minimal and targeted? If no, simplify
- [ ] Does this add value for Steps 3-4? If no, skip it
- [ ] Can I verify this works without breaking existing? If no, reconsider
