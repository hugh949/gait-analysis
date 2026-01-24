# Root Cause Analysis: Persistent "Upload failed: 500" Error

## Executive Summary
After deep code review comparing the **working simple upload endpoint** vs the **failing main upload endpoint**, I've identified **5 critical issues** causing the persistent 500 error.

## Key Finding: Simple Upload Works, Main Upload Fails

### Working Pattern (Simple Upload)
```python
@router.post("/upload-simple")
async def upload_video_simple(file: UploadFile = File(...)) -> JSONResponse:
    request_id = str(uuid.uuid4())[:8]
    try:
        # Simple logic
        return JSONResponse({"status": "success"})
    except HTTPException:
        raise  # Let FastAPI handle it
    except Exception as e:
        logger.error(f"[{request_id}] Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
```

### Failing Pattern (Main Upload)
```python
@router.post("/upload")
async def upload_video(...) -> JSONResponse:
    try:  # Outer try wraps everything
        request_id = str(uuid.uuid4())[:8]  # Defined INSIDE try
        # 900+ lines of complex logic
        return JSONResponse({...})
    except Exception as e:
        # request_id might not exist if error occurs before line 169!
        logger.error(f"[{request_id}] ...")  # ❌ CRASHES if request_id undefined
    finally:
        # tmp_path, video_url might not exist
        if tmp_path and os.path.exists(tmp_path):  # ❌ CRASHES if tmp_path undefined
```

## Root Causes Identified

### 1. **CRITICAL: Variable Scope Issue** ⚠️ HIGHEST PRIORITY
**Problem**: `request_id`, `tmp_path`, `video_url` are defined INSIDE the try block but used in exception handlers and finally block.

**Impact**: If an error occurs before these variables are defined, the exception handler itself crashes, causing a 500 error.

**Location**: Lines 167-972 in `analysis_azure.py`

**Fix Required**:
```python
# ✅ CORRECT - Define variables BEFORE try block
request_id = str(uuid.uuid4())[:8]
tmp_path = None
video_url = None
try:
    # Use variables
except Exception as e:
    # Variables always defined
    logger.error(f"[{request_id}] Error: {e}")
finally:
    # Variables always defined
    if tmp_path:
        cleanup()
```

### 2. **Exception Handler Conflict** ⚠️ HIGH PRIORITY
**Problem**: There's a global exception handler (`@app.exception_handler(Exception)`) that catches ALL exceptions, but the endpoint also has local exception handlers that return `JSONResponse`. This creates a conflict.

**Impact**: The global handler might intercept exceptions before the local handler can return a proper JSONResponse, causing serialization issues.

**Location**: 
- Global handler: `main_integrated.py` lines 215-249
- Local handlers: `analysis_azure.py` lines 874-970

**Fix Required**: Either:
- Remove local exception handlers and let global handler work, OR
- Make sure local handlers raise HTTPException (not return JSONResponse) so global handler can process them

### 3. **Duplicate Exception Handlers** ⚠️ MEDIUM PRIORITY
**Problem**: There are TWO `except Exception` blocks in the same function (lines 896 and 939).

**Impact**: The second handler will never be reached, but its existence suggests confusion about error handling flow.

**Location**: Lines 896-938 and 939-970

**Fix Required**: Remove duplicate handler.

### 4. **Finally Block Variable Access** ⚠️ MEDIUM PRIORITY
**Problem**: The `finally` block (lines 972-980) accesses `tmp_path` and `video_url` which might not be defined if an error occurs early.

**Impact**: Causes AttributeError/NameError in finally block, masking the original error.

**Location**: Lines 972-980

**Fix Required**: Initialize variables before try block, or check if they exist before using.

### 5. **Complex Nested Try/Except** ⚠️ LOW PRIORITY
**Problem**: The function has deeply nested try/except blocks (outer try at line 167, inner tries at lines 237, 243, 265, 384, 440, 486, 674).

**Impact**: Makes error handling unpredictable and hard to debug.

**Fix Required**: Simplify to match simple upload pattern - one main try/except, with specific handlers for known exceptions.

## Recommended Fix Strategy

### Phase 1: Critical Fixes (Do First)
1. **Move variable initialization BEFORE try block**
   ```python
   request_id = str(uuid.uuid4())[:8]
   tmp_path = None
   video_url = None
   file_size = 0
   analysis_id = None
   try:
       # All logic here
   ```

2. **Fix exception handler pattern to match simple upload**
   ```python
   except HTTPException:
       raise  # Let FastAPI handle it
   except Exception as e:
       logger.error(f"[{request_id}] Error: {e}", exc_info=True)
       raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
   ```

3. **Remove duplicate exception handlers**

### Phase 2: Simplify Error Handling
4. **Remove local JSONResponse returns in exception handlers**
   - Let exceptions propagate to global handler
   - Or raise HTTPException instead of returning JSONResponse

5. **Simplify finally block**
   ```python
   finally:
       if 'tmp_path' in locals() and tmp_path and os.path.exists(tmp_path):
           try:
               os.unlink(tmp_path)
           except:
               pass
   ```

## Best Practices from Simple Upload

1. ✅ **Define variables before try block**
2. ✅ **Use `raise HTTPException` instead of `return JSONResponse` in error handlers**
3. ✅ **Let FastAPI's global exception handler do its job**
4. ✅ **Keep exception handling simple - one try/except per logical block**
5. ✅ **Always log with request_id (ensure it's defined)**

## Implementation Plan

1. **Immediate Fix**: Move variable initialization outside try block
2. **Error Handling Fix**: Change to raise HTTPException pattern
3. **Remove Duplicates**: Clean up duplicate exception handlers
4. **Test**: Verify with simple file upload
5. **Monitor**: Check Azure logs for any remaining issues

## Expected Outcome

After these fixes:
- Variables always defined before use
- Exception handlers don't conflict
- Errors properly logged with request_id
- FastAPI global handler processes errors correctly
- No more 500 errors from exception handler crashes
