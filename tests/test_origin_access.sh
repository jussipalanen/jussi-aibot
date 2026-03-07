#!/bin/bash
# Test script for origin-based access control

API_URL="http://127.0.0.1:8000/ai/review"
TEST_FILE="test_resume.txt"

# Create a dummy test file if it doesn't exist
if [ ! -f "$TEST_FILE" ]; then
  echo "Creating dummy test file..."
  echo "Ansioluettelo
  
Nimi: Testi Henkilö
Kokemus: 5 vuotta ohjelmistokehityksessä
Koulutus: Tietojenkäsittelytieteen kandidaatti" > "$TEST_FILE"
fi

echo "========================================"
echo "Testing Origin-Based Access Control"
echo "========================================"
echo ""

echo "Test 1: Request WITHOUT origin and WITHOUT API key (should fail with 401)"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  -F "file=@$TEST_FILE" \
  "$API_URL"
echo ""

echo "Test 2: Request WITH allowed origin and WITHOUT API key (should succeed with 200)"
echo "   Note: Set ALLOWED_ORIGINS=http://localhost:3000 in your environment"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  -H "Origin: http://localhost:3000" \
  -F "file=@$TEST_FILE" \
  "$API_URL"
echo ""

echo "Test 3: Request WITH non-allowed origin and WITHOUT API key (should fail with 401)"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  -H "Origin: http://evil.com" \
  -F "file=@$TEST_FILE" \
  "$API_URL"
echo ""

echo "Test 4: Request WITHOUT origin but WITH valid API key (should succeed with 200)"
echo "   Note: Set API_KEYS=dev-key in your environment"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  -H "X-API-Key: dev-key" \
  -F "file=@$TEST_FILE" \
  "$API_URL"
echo ""

echo "Test 5: Request WITH non-allowed origin but WITH valid API key (should succeed with 200)"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
  -H "Origin: http://evil.com" \
  -H "X-API-Key: dev-key" \
  -F "file=@$TEST_FILE" \
  "$API_URL"
echo ""

echo "========================================"
echo "Testing Complete"
echo "========================================"
echo ""
echo "Expected results when API_KEYS=dev-key and ALLOWED_ORIGINS=http://localhost:3000:"
echo "  Test 1: 401 (no origin, no key)"
echo "  Test 2: 200 (allowed origin, no key needed)"
echo "  Test 3: 401 (non-allowed origin, no key)"
echo "  Test 4: 200 (no origin, but has valid key)"
echo "  Test 5: 200 (non-allowed origin, but has valid key)"
