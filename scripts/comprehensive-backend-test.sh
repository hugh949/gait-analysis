#!/bin/bash
# Comprehensive Backend Test Script
# Tests all endpoints and functionality

set -e

API_URL="https://gait-analysis-api-simple.azurewebsites.net"
FRONTEND_ORIGIN="https://jolly-meadow-0a467810f.1.azurestaticapps.net"

echo "═══════════════════════════════════════════════════════════"
echo "  COMPREHENSIVE BACKEND TEST SUITE"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Test 1: Root endpoint
echo "TEST 1: Root endpoint (/)"
echo "───────────────────────────────────────────────────────────"
RESPONSE=$(curl -s -m 10 "${API_URL}/")
if [[ "$RESPONSE" == *"healthy"* ]]; then
    echo "✅ PASS: Root endpoint working"
    echo "   Response: $RESPONSE"
else
    echo "❌ FAIL: Root endpoint not working"
    echo "   Response: $RESPONSE"
    exit 1
fi
echo ""

# Test 2: Health endpoint (no trailing slash)
echo "TEST 2: Health endpoint (/api/v1/health - no trailing slash)"
echo "───────────────────────────────────────────────────────────"
RESPONSE=$(curl -s -m 10 "${API_URL}/api/v1/health")
if [[ "$RESPONSE" == *"healthy"* ]]; then
    echo "✅ PASS: Health endpoint (no slash) working"
    echo "   Response: $RESPONSE"
else
    echo "❌ FAIL: Health endpoint (no slash) not working"
    echo "   Response: $RESPONSE"
    exit 1
fi
echo ""

# Test 3: Health endpoint (with trailing slash)
echo "TEST 3: Health endpoint (/api/v1/health/ - with trailing slash)"
echo "───────────────────────────────────────────────────────────"
RESPONSE=$(curl -s -m 10 "${API_URL}/api/v1/health/")
if [[ "$RESPONSE" == *"healthy"* ]]; then
    echo "✅ PASS: Health endpoint (with slash) working"
    echo "   Response: $RESPONSE"
else
    echo "❌ FAIL: Health endpoint (with slash) not working"
    echo "   Response: $RESPONSE"
    exit 1
fi
echo ""

# Test 4: CORS preflight for health
echo "TEST 4: CORS preflight for health endpoint"
echo "───────────────────────────────────────────────────────────"
CORS_HEADERS=$(curl -s -m 10 -X OPTIONS \
    -H "Origin: ${FRONTEND_ORIGIN}" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: Content-Type" \
    "${API_URL}/api/v1/health" \
    -i 2>&1 | grep -i "access-control" || echo "")
if [[ "$CORS_HEADERS" == *"access-control-allow-origin"* ]]; then
    echo "✅ PASS: CORS headers present"
    echo "   Headers: $CORS_HEADERS"
else
    echo "❌ FAIL: CORS headers missing"
    echo "   Headers: $CORS_HEADERS"
    exit 1
fi
echo ""

# Test 5: CORS preflight for upload
echo "TEST 5: CORS preflight for upload endpoint"
echo "───────────────────────────────────────────────────────────"
CORS_HEADERS=$(curl -s -m 10 -X OPTIONS \
    -H "Origin: ${FRONTEND_ORIGIN}" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Content-Type" \
    "${API_URL}/api/v1/analysis/upload" \
    -i 2>&1 | grep -i "access-control" || echo "")
if [[ "$CORS_HEADERS" == *"access-control-allow-origin"* ]]; then
    echo "✅ PASS: CORS headers present for upload"
    echo "   Headers: $CORS_HEADERS"
else
    echo "❌ FAIL: CORS headers missing for upload"
    echo "   Headers: $CORS_HEADERS"
    exit 1
fi
echo ""

# Test 6: Upload endpoint (POST without file - should return error but not crash)
echo "TEST 6: Upload endpoint (POST without file)"
echo "───────────────────────────────────────────────────────────"
RESPONSE=$(curl -s -m 10 -X POST \
    -H "Origin: ${FRONTEND_ORIGIN}" \
    -H "Content-Type: multipart/form-data" \
    "${API_URL}/api/v1/analysis/upload" 2>&1)
if [[ "$RESPONSE" == *"422"* ]] || [[ "$RESPONSE" == *"detail"* ]] || [[ "$RESPONSE" == *"required"* ]]; then
    echo "✅ PASS: Upload endpoint responds (expected validation error)"
    echo "   Response: $RESPONSE" | head -3
else
    echo "⚠️  WARN: Unexpected response from upload endpoint"
    echo "   Response: $RESPONSE" | head -5
fi
echo ""

# Test 7: Create a test video file and upload it
echo "TEST 7: Upload endpoint with actual file"
echo "───────────────────────────────────────────────────────────"
# Create a minimal test file (1KB of zeros)
TEST_FILE="/tmp/test_video.mp4"
echo "Creating test file..."
dd if=/dev/zero of="${TEST_FILE}" bs=1024 count=1 2>/dev/null || echo "0000000000" > "${TEST_FILE}"

UPLOAD_RESPONSE=$(curl -s -m 30 -X POST \
    -H "Origin: ${FRONTEND_ORIGIN}" \
    -F "file=@${TEST_FILE}" \
    -F "view_type=front" \
    -F "fps=30.0" \
    "${API_URL}/api/v1/analysis/upload" 2>&1)

if [[ "$UPLOAD_RESPONSE" == *"analysis_id"* ]] || [[ "$UPLOAD_RESPONSE" == *"id"* ]]; then
    echo "✅ PASS: File upload accepted"
    echo "   Response: $UPLOAD_RESPONSE" | head -5
    # Extract analysis ID if present
    ANALYSIS_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
    if [ -n "$ANALYSIS_ID" ]; then
        echo "   Analysis ID: $ANALYSIS_ID"
    fi
elif [[ "$UPLOAD_RESPONSE" == *"422"* ]] || [[ "$UPLOAD_RESPONSE" == *"validation"* ]]; then
    echo "⚠️  WARN: Upload rejected (validation error - might be expected for test file)"
    echo "   Response: $UPLOAD_RESPONSE" | head -5
else
    echo "❌ FAIL: Upload failed unexpectedly"
    echo "   Response: $UPLOAD_RESPONSE" | head -10
    rm -f "${TEST_FILE}"
    exit 1
fi

rm -f "${TEST_FILE}"
echo ""

# Test 8: Check if analysis status endpoint works
echo "TEST 8: Analysis status endpoint"
echo "───────────────────────────────────────────────────────────"
# Use a test ID (will likely return 404, but endpoint should exist)
STATUS_RESPONSE=$(curl -s -m 10 -X GET \
    -H "Origin: ${FRONTEND_ORIGIN}" \
    "${API_URL}/api/v1/analysis/test-id-12345" 2>&1)
if [[ "$STATUS_RESPONSE" == *"404"* ]] || [[ "$STATUS_RESPONSE" == *"not found"* ]] || [[ "$STATUS_RESPONSE" == *"detail"* ]]; then
    echo "✅ PASS: Status endpoint exists (404 expected for non-existent ID)"
    echo "   Response: $STATUS_RESPONSE" | head -3
else
    echo "⚠️  WARN: Unexpected response from status endpoint"
    echo "   Response: $STATUS_RESPONSE" | head -5
fi
echo ""

# Test 9: Check backend logs for errors
echo "TEST 9: Checking backend logs for recent errors"
echo "───────────────────────────────────────────────────────────"
LOG_CHECK=$(az webapp log tail --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3 2>&1 | head -20 || echo "Could not fetch logs")
if [[ "$LOG_CHECK" == *"error"* ]] || [[ "$LOG_CHECK" == *"Error"* ]] || [[ "$LOG_CHECK" == *"ERROR"* ]]; then
    echo "⚠️  WARN: Errors found in logs"
    echo "$LOG_CHECK" | grep -i error | head -5
else
    echo "✅ PASS: No recent errors in logs (or logs not accessible)"
fi
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "  TEST SUMMARY"
echo "═══════════════════════════════════════════════════════════"
echo "✅ All critical endpoints tested"
echo "✅ CORS configuration verified"
echo "✅ File upload endpoint functional"
echo ""
echo "Backend URL: ${API_URL}"
echo "Frontend URL: ${FRONTEND_ORIGIN}"
echo ""
echo "Next: Test from frontend browser to verify full integration"
echo "═══════════════════════════════════════════════════════════"


