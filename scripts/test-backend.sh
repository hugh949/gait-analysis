#!/bin/bash
# Comprehensive Backend Testing Script
# Tests all critical backend functionality before deployment

set -e

BACKEND_URL="${BACKEND_URL:-https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io}"
FRONTEND_URL="${FRONTEND_URL:-https://jolly-meadow-0a467810f.1.azurestaticapps.net}"

echo "🧪 Backend Quality Assurance Tests"
echo "=================================="
echo "Backend URL: $BACKEND_URL"
echo "Frontend URL: $FRONTEND_URL"
echo ""

PASSED=0
FAILED=0

test_result() {
    if [ $1 -eq 0 ]; then
        echo "✅ PASS: $2"
        ((PASSED++))
    else
        echo "❌ FAIL: $2"
        ((FAILED++))
    fi
}

# Test 1: Health Check
echo "Test 1: Health Check Endpoint"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "$BACKEND_URL/" 2>&1)
if [ "$HTTP_CODE" = "200" ]; then
    test_result 0 "Health endpoint returns 200"
else
    test_result 1 "Health endpoint returned $HTTP_CODE (expected 200)"
fi
echo ""

# Test 2: API Health Check
echo "Test 2: API Health Check Endpoint"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "$BACKEND_URL/api/v1/health" 2>&1)
if [ "$HTTP_CODE" = "200" ]; then
    test_result 0 "API health endpoint returns 200"
else
    test_result 1 "API health endpoint returned $HTTP_CODE (expected 200)"
fi
echo ""

# Test 3: CORS Preflight Check
echo "Test 3: CORS Preflight (OPTIONS) Request"
CORS_RESPONSE=$(curl -s -X OPTIONS "$BACKEND_URL/api/v1/analysis/upload" \
    -H "Origin: $FRONTEND_URL" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type" \
    -w "\nHTTP_CODE:%{http_code}" \
    -m 10 2>&1)

if echo "$CORS_RESPONSE" | grep -q "HTTP_CODE:200\|HTTP_CODE:204"; then
    test_result 0 "CORS preflight request successful"
else
    test_result 1 "CORS preflight failed"
    echo "Response: $CORS_RESPONSE"
fi
echo ""

# Test 4: CORS Headers Check
echo "Test 4: CORS Headers in Response"
CORS_HEADERS=$(curl -s -I -X GET "$BACKEND_URL/" \
    -H "Origin: $FRONTEND_URL" \
    -m 10 2>&1 | grep -i "access-control")

if [ -n "$CORS_HEADERS" ]; then
    test_result 0 "CORS headers present in response"
    echo "Headers: $CORS_HEADERS"
else
    test_result 1 "CORS headers missing"
fi
echo ""

# Test 5: Upload Endpoint Availability
echo "Test 5: Upload Endpoint Availability"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BACKEND_URL/api/v1/analysis/upload" \
    -H "Origin: $FRONTEND_URL" \
    -m 10 2>&1)
# 400 is expected (no file provided), but endpoint should be reachable
if [ "$HTTP_CODE" = "400" ] || [ "$HTTP_CODE" = "422" ]; then
    test_result 0 "Upload endpoint is reachable (returned $HTTP_CODE - expected for missing file)"
else
    test_result 1 "Upload endpoint returned $HTTP_CODE (expected 400 or 422)"
fi
echo ""

# Test 6: Response Time Check
echo "Test 6: Response Time Check"
RESPONSE_TIME=$(curl -s -o /dev/null -w "%{time_total}" -m 10 "$BACKEND_URL/" 2>&1)
if (( $(echo "$RESPONSE_TIME < 5.0" | bc -l) )); then
    test_result 0 "Response time acceptable: ${RESPONSE_TIME}s"
else
    test_result 1 "Response time too slow: ${RESPONSE_TIME}s"
fi
echo ""

# Summary
echo "=================================="
echo "Test Summary:"
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "🎉 All tests passed! Backend is ready for use."
    exit 0
else
    echo "⚠️  Some tests failed. Backend may not be ready."
    exit 1
fi



