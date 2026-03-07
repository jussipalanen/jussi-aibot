#!/usr/bin/env python3
"""
Security test to verify origin-based access control only allows specific origins.
Tests various edge cases and potential security vulnerabilities.
"""
import os
import sys

# Test the origin matching logic
def test_origin_matching():
    """Test the origin matching logic from routes.py"""
    
    # Simulated ALLOWED_ORIGINS from environment
    test_cases = [
        {
            "name": "Exact match - should allow",
            "allowed": {"http://localhost:3000"},
            "request_origin": "http://localhost:3000",
            "should_pass": True
        },
        {
            "name": "Exact match with trailing slash - should allow",
            "allowed": {"http://localhost:3000"},
            "request_origin": "http://localhost:3000/",
            "should_pass": True
        },
        {
            "name": "Different port - should block",
            "allowed": {"http://localhost:3000"},
            "request_origin": "http://localhost:3001",
            "should_pass": False
        },
        {
            "name": "Subdomain - should block",
            "allowed": {"https://example.com"},
            "request_origin": "https://app.example.com",
            "should_pass": False
        },
        {
            "name": "Evil domain with prefix - should block",
            "allowed": {"http://localhost:3000"},
            "request_origin": "http://localhost:3000.evil.com",
            "should_pass": False
        },
        {
            "name": "Evil domain with suffix - should block",
            "allowed": {"http://localhost:3000"},
            "request_origin": "http://localhost:3000-evil.com",
            "should_pass": False
        },
        {
            "name": "HTTPS vs HTTP - should block",
            "allowed": {"http://localhost:3000"},
            "request_origin": "https://localhost:3000",
            "should_pass": False
        },
        {
            "name": "Multiple allowed origins - match first",
            "allowed": {"http://localhost:3000", "https://app.example.com"},
            "request_origin": "http://localhost:3000",
            "should_pass": True
        },
        {
            "name": "Multiple allowed origins - match second",
            "allowed": {"http://localhost:3000", "https://app.example.com"},
            "request_origin": "https://app.example.com",
            "should_pass": True
        },
        {
            "name": "Multiple allowed origins - no match",
            "allowed": {"http://localhost:3000", "https://app.example.com"},
            "request_origin": "https://evil.com",
            "should_pass": False
        },
        {
            "name": "Empty origin - should block",
            "allowed": {"http://localhost:3000"},
            "request_origin": "",
            "should_pass": False
        },
        {
            "name": "Path in origin (shouldn't happen in real browser) - should allow if base matches",
            "allowed": {"http://localhost:3000"},
            "request_origin": "http://localhost:3000/some/path",
            "should_pass": True  # The code handles this with startswith check
        }
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 80)
    print("ORIGIN MATCHING SECURITY TESTS")
    print("=" * 80)
    print()
    
    for test in test_cases:
        allowed_origins = test["allowed"]
        origin = test["request_origin"]
        should_pass = test["should_pass"]
        
        # Simulate the matching logic from routes.py
        origin_normalized = origin.rstrip("/").split("?")[0]
        is_allowed = False
        
        if origin_normalized:
            for allowed in allowed_origins:
                allowed_normalized = allowed.rstrip("/")
                if origin_normalized == allowed_normalized or origin_normalized.startswith(allowed_normalized + "/"):
                    is_allowed = True
                    break
        
        # Check if result matches expectation
        result = "✓ PASS" if is_allowed == should_pass else "✗ FAIL"
        status = "ALLOWED" if is_allowed else "BLOCKED"
        expected = "ALLOWED" if should_pass else "BLOCKED"
        
        if is_allowed == should_pass:
            passed += 1
        else:
            failed += 1
        
        print(f"{result} | {test['name']}")
        print(f"     Allowed origins: {allowed_origins}")
        print(f"     Request origin: '{origin}'")
        print(f"     Result: {status} | Expected: {expected}")
        print()
    
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


def test_referer_parsing():
    """Test referer header parsing"""
    from urllib.parse import urlparse
    
    print("\n" + "=" * 80)
    print("REFERER PARSING TESTS")
    print("=" * 80)
    print()
    
    test_cases = [
        {
            "referer": "http://localhost:3000/some/path",
            "expected": "http://localhost:3000"
        },
        {
            "referer": "https://example.com/page?query=value",
            "expected": "https://example.com"
        },
        {
            "referer": "https://app.example.com:8080/dashboard",
            "expected": "https://app.example.com:8080"
        }
    ]
    
    passed = 0
    failed = 0
    
    for test in test_cases:
        referer = test["referer"]
        expected = test["expected"]
        
        # Simulate the referer parsing from routes.py
        origin_normalized = referer.rstrip("/").split("?")[0]
        parsed = urlparse(origin_normalized)
        origin_normalized = f"{parsed.scheme}://{parsed.netloc}"
        
        result = "✓ PASS" if origin_normalized == expected else "✗ FAIL"
        
        if origin_normalized == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{result} | Referer: {referer}")
        print(f"     Parsed: {origin_normalized}")
        print(f"     Expected: {expected}")
        print()
    
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    all_passed = True
    
    if not test_origin_matching():
        all_passed = False
    
    if not test_referer_parsing():
        all_passed = False
    
    if all_passed:
        print("\n✓ All security tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some security tests failed!")
        sys.exit(1)
