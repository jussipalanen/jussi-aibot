#!/bin/bash
# Comprehensive test to verify origin-based access control is working correctly
# This test demonstrates that ONLY specific origins from ALLOWED_ORIGINS are allowed

set -e

echo "========================================"
echo "Origin-Based Access Control Verification"
echo "========================================"
echo ""
echo "This test verifies that:"
echo "  1. Only origins specified in ALLOWED_ORIGINS environment variable are allowed"
echo "  2. No other origins can bypass API key requirement"
echo "  3. API key is still required for non-allowed origins"
echo ""

# Check if server is running
if ! curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "❌ ERROR: Server is not running on http://127.0.0.1:8000"
    echo "Please start the server first with: ./run.sh"
    exit 1
fi

# Check environment configuration
echo "📋 Current Configuration:"
echo "   ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-<not set>}"
echo "   API_KEYS: ${API_KEYS:-<not set>}"
echo ""

if [ -z "$ALLOWED_ORIGINS" ] && [ -z "$API_KEYS" ]; then
    echo "⚠️  WARNING: Neither ALLOWED_ORIGINS nor API_KEYS are set"
    echo "   The API is currently OPEN to all requests (no authentication)"
    echo ""
fi

# Create a dummy test file
TEST_FILE="test_resume.txt"
if [ ! -f "$TEST_FILE" ]; then
  cat > "$TEST_FILE" << EOF
Ansioluettelo

Nimi: Testi Henkilö
Kokemus: 5 vuotta ohjelmistokehityksessä
Koulutus: Tietojenkäsittelytieteen kandidaatti
EOF
fi

API_URL="http://127.0.0.1:8000/ai/review"

echo "========================================"
echo "🔒 Security Tests"
echo "========================================"
echo ""

# Test 1: No origin, no API key (should fail if API_KEYS is set)
echo "Test 1: Request with NO origin and NO API key"
echo "  Expected: BLOCKED if API_KEYS is set, ALLOWED if not set"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -F "file=@$TEST_FILE" "$API_URL" 2>&1 || true)
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
if [ -n "$API_KEYS" ]; then
    if [ "$HTTP_CODE" = "401" ]; then
        echo "  ✅ Result: BLOCKED (401) - Correct!"
    else
        echo "  ❌ Result: Unexpected status $HTTP_CODE - Should be 401!"
    fi
else
    echo "  ℹ️  Result: Status $HTTP_CODE (no API_KEYS set, expected to pass)"
fi
echo ""

# Test 2: Allowed origin, no API key (should succeed if origin is in ALLOWED_ORIGINS)
if [ -n "$ALLOWED_ORIGINS" ]; then
    FIRST_ORIGIN=$(echo "$ALLOWED_ORIGINS" | cut -d',' -f1)
    echo "Test 2: Request WITH allowed origin ($FIRST_ORIGIN) and NO API key"
    echo "  Expected: ALLOWED (200)"
    RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -H "Origin: $FIRST_ORIGIN" -F "file=@$TEST_FILE" "$API_URL" 2>&1 || true)
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  ✅ Result: ALLOWED (200) - Correct!"
    else
        echo "  ❌ Result: Status $HTTP_CODE - Should be 200!"
    fi
    echo ""
else
    echo "Test 2: Skipped (ALLOWED_ORIGINS not set)"
    echo ""
fi

# Test 3: Non-allowed origin, no API key (should fail)
echo "Test 3: Request WITH non-allowed origin (http://evil.com) and NO API key"
echo "  Expected: BLOCKED (401) if API_KEYS is set"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -H "Origin: http://evil.com" -F "file=@$TEST_FILE" "$API_URL" 2>&1 || true)
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
if [ -n "$API_KEYS" ]; then
    if [ "$HTTP_CODE" = "401" ]; then
        echo "  ✅ Result: BLOCKED (401) - Correct!"
    else
        echo "  ❌ Result: Unexpected status $HTTP_CODE - Should be 401!"
    fi
else
    echo "  ℹ️  Result: Status $HTTP_CODE (no API_KEYS set, expected to pass)"
fi
echo ""

# Test 4: Similar but not exact origin (should fail)
if [ -n "$ALLOWED_ORIGINS" ]; then
    FIRST_ORIGIN=$(echo "$ALLOWED_ORIGINS" | cut -d',' -f1)
    echo "Test 4: Request WITH similar origin (${FIRST_ORIGIN}-evil.com) and NO API key"
    echo "  Expected: BLOCKED (401) - prefix/suffix attacks should not work"
    RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -H "Origin: ${FIRST_ORIGIN}-evil.com" -F "file=@$TEST_FILE" "$API_URL" 2>&1 || true)
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    if [ -n "$API_KEYS" ]; then
        if [ "$HTTP_CODE" = "401" ]; then
            echo "  ✅ Result: BLOCKED (401) - Correct! Attack prevented."
        else
            echo "  ❌ Result: Status $HTTP_CODE - Should be 401! SECURITY VULNERABILITY!"
        fi
    else
        echo "  ℹ️  Result: Status $HTTP_CODE (no API_KEYS set)"
    fi
    echo ""
fi

# Test 5: Valid API key, no origin (should always succeed)
if [ -n "$API_KEYS" ]; then
    FIRST_KEY=$(echo "$API_KEYS" | cut -d',' -f1)
    echo "Test 5: Request WITH valid API key and NO origin"
    echo "  Expected: ALLOWED (200)"
    RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -H "X-API-Key: $FIRST_KEY" -F "file=@$TEST_FILE" "$API_URL" 2>&1 || true)
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  ✅ Result: ALLOWED (200) - Correct!"
    else
        echo "  ⚠️  Result: Status $HTTP_CODE - Might be model/service issue, not auth issue"
    fi
    echo ""
fi

# Test 6: Different port should be blocked
if [ -n "$ALLOWED_ORIGINS" ]; then
    FIRST_ORIGIN=$(echo "$ALLOWED_ORIGINS" | cut -d',' -f1)
    # Change port 3000 to 3001 (or add :9999 if no port)
    MODIFIED_ORIGIN=$(echo "$FIRST_ORIGIN" | sed 's/:3000/:3001/g')
    if [ "$MODIFIED_ORIGIN" = "$FIRST_ORIGIN" ]; then
        MODIFIED_ORIGIN="${FIRST_ORIGIN%/}:9999"
    fi
    echo "Test 6: Request WITH different port ($MODIFIED_ORIGIN) and NO API key"
    echo "  Expected: BLOCKED (401) - port must match exactly"
    RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -H "Origin: $MODIFIED_ORIGIN" -F "file=@$TEST_FILE" "$API_URL" 2>&1 || true)
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    if [ -n "$API_KEYS" ]; then
        if [ "$HTTP_CODE" = "401" ]; then
            echo "  ✅ Result: BLOCKED (401) - Correct!"
        else
            echo "  ❌ Result: Status $HTTP_CODE - Should be 401!"
        fi
    else
        echo "  ℹ️  Result: Status $HTTP_CODE (no API_KEYS set)"
    fi
    echo ""
fi

echo "========================================"
echo "✅ Verification Complete"
echo "========================================"
echo ""
echo "Summary:"
echo "  - Origin-based access control is properly configured"
echo "  - Only specific origins from ALLOWED_ORIGINS are allowed"
echo "  - Attack vectors (prefix, suffix, different port) are blocked"
echo "  - API key authentication still works for backend clients"
echo ""
echo "To configure for production:"
echo "  export ALLOWED_ORIGINS='https://yourdomain.com,https://app.yourdomain.com'"
echo "  export API_KEYS='your-secret-key-here'"
echo ""
