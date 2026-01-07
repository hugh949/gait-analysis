#!/bin/bash
# Upload Functionality Test Script
# Tests the complete upload workflow

set -e

BACKEND_URL="${BACKEND_URL:-https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io}"
FRONTEND_URL="${FRONTEND_URL:-https://jolly-meadow-0a467810f.1.azurestaticapps.net}"

echo "🧪 Upload Functionality Tests"
echo "============================="
echo ""

# Create a small test video file (1 second, minimal size)
TEST_VIDEO="/tmp/test_video.mp4"
echo "📹 Creating test video file..."

# Use ffmpeg if available, otherwise create a dummy file
if command -v ffmpeg &> /dev/null; then
    ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -pix_fmt yuv420p "$TEST_VIDEO" -y 2>/dev/null || {
        echo "⚠️  ffmpeg not available, creating minimal test file"
        echo "test video content" > "$TEST_VIDEO"
    }
else
    echo "⚠️  ffmpeg not available, creating minimal test file"
    echo "test video content" > "$TEST_VIDEO"
fi

echo "✅ Test video created: $TEST_VIDEO"
echo ""

# Test 1: Upload with proper CORS headers
echo "Test 1: Upload Request with CORS"
UPLOAD_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/analysis/upload" \
    -H "Origin: $FRONTEND_URL" \
    -H "Content-Type: multipart/form-data" \
    -F "file=@$TEST_VIDEO" \
    -w "\nHTTP_CODE:%{http_code}" \
    -m 30 2>&1)

HTTP_CODE=$(echo "$UPLOAD_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$UPLOAD_RESPONSE" | sed '/HTTP_CODE/d')

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo "✅ Upload request successful (HTTP $HTTP_CODE)"
    if echo "$BODY" | grep -q "analysis_id"; then
        ANALYSIS_ID=$(echo "$BODY" | grep -o '"analysis_id":"[^"]*"' | cut -d'"' -f4)
        echo "✅ Analysis ID received: $ANALYSIS_ID"
    else
        echo "⚠️  Response body: $BODY"
    fi
else
    echo "❌ Upload request failed (HTTP $HTTP_CODE)"
    echo "Response: $BODY"
    exit 1
fi
echo ""

# Test 2: Check analysis status
if [ -n "$ANALYSIS_ID" ]; then
    echo "Test 2: Analysis Status Check"
    sleep 2
    STATUS_RESPONSE=$(curl -s "$BACKEND_URL/api/v1/analysis/$ANALYSIS_ID" -m 10 2>&1)
    if echo "$STATUS_RESPONSE" | grep -q "status"; then
        echo "✅ Status endpoint working"
        echo "Status: $STATUS_RESPONSE"
    else
        echo "⚠️  Status check returned: $STATUS_RESPONSE"
    fi
    echo ""
fi

# Cleanup
rm -f "$TEST_VIDEO"
echo "✅ Test completed"
echo ""



