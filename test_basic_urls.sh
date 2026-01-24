#!/bin/bash
# Test basic URLs to check if the application is running

echo "Testing basic application URLs..."
echo ""

# Default to localhost if no URL provided
BASE_URL="${1:-http://localhost:8000}"

echo "Base URL: $BASE_URL"
echo ""

# Test root endpoint
echo "1. Testing root endpoint (/)..."
curl -s -o /dev/null -w "Status: %{http_code}\n" "$BASE_URL/" || echo "❌ Failed to connect"
echo ""

# Test health endpoint
echo "2. Testing /health endpoint..."
curl -s "$BASE_URL/health" | python3 -m json.tool 2>/dev/null || curl -s "$BASE_URL/health"
echo ""
echo ""

# Test API health endpoint
echo "3. Testing /api/v1/health endpoint..."
curl -s "$BASE_URL/api/v1/health" | python3 -m json.tool 2>/dev/null || curl -s "$BASE_URL/api/v1/health"
echo ""
echo ""

# Test debug routes endpoint
echo "4. Testing /api/v1/debug/routes endpoint..."
curl -s "$BASE_URL/api/v1/debug/routes" | python3 -m json.tool 2>/dev/null || curl -s "$BASE_URL/api/v1/debug/routes"
echo ""
echo ""

echo "Done!"
