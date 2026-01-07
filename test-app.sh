#!/bin/bash
# Quick Test Script for Gait Analysis Application

API_URL="https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io"
FRONTEND_URL="https://gentle-wave-0d4e1d10f.4.azurestaticapps.net"

echo "🧪 Testing Gait Analysis Application"
echo "===================================="
echo ""

echo "1️⃣  Testing Frontend..."
if curl -s --max-time 5 "$FRONTEND_URL" > /dev/null; then
    echo "   ✅ Frontend is accessible"
    echo "   📍 URL: $FRONTEND_URL"
else
    echo "   ❌ Frontend is not accessible"
fi
echo ""

echo "2️⃣  Testing Backend Health Check..."
HEALTH_RESPONSE=$(curl -s --max-time 30 "$API_URL/health" 2>&1)
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "   ✅ Backend is healthy"
    echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"
else
    echo "   ⚠️  Backend may be starting (scales from zero)"
    echo "   Response: $HEALTH_RESPONSE"
    echo "   💡 First request may take 30-60 seconds to wake up the container"
fi
echo ""

echo "3️⃣  Testing Backend Root Endpoint..."
ROOT_RESPONSE=$(curl -s --max-time 30 "$API_URL/" 2>&1)
if echo "$ROOT_RESPONSE" | grep -q "status"; then
    echo "   ✅ Backend root endpoint works"
    echo "$ROOT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$ROOT_RESPONSE"
else
    echo "   ⚠️  Backend may be starting"
    echo "   Response: $ROOT_RESPONSE"
fi
echo ""

echo "4️⃣  Testing CORS Configuration..."
CORS_TEST=$(curl -s -X OPTIONS \
  -H "Origin: $FRONTEND_URL" \
  -H "Access-Control-Request-Method: POST" \
  --max-time 30 \
  "$API_URL/api/v1/analysis/upload" 2>&1)
if echo "$CORS_TEST" | grep -qi "access-control"; then
    echo "   ✅ CORS headers present"
else
    echo "   ⚠️  CORS check inconclusive (may need to check browser)"
fi
echo ""

echo "📋 Testing Summary"
echo "=================="
echo "Frontend URL: $FRONTEND_URL"
echo "Backend URL:  $API_URL"
echo ""
echo "✅ To test video upload:"
echo "   1. Open $FRONTEND_URL in your browser"
echo "   2. Click 'Upload Video'"
echo "   3. Select a video file and upload"
echo ""
echo "   OR use curl:"
echo "   curl -X POST $API_URL/api/v1/analysis/upload \\"
echo "     -F 'file=@your-video.mp4' \\"
echo "     -F 'view_type=front'"
echo ""
echo "💡 Note: First request may take 30-60 seconds (container scales from zero)"



