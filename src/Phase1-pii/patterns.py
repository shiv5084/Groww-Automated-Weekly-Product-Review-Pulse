import re

# PII Regex Patterns
# Focus on Email, Phone, Username, Device ID/IP

PII_PATTERNS = {
    "EMAIL": re.compile(r"[\w\.-]+@[\w\.-]+\.\w+", flags=re.IGNORECASE),
    
    # Phone numbers: +91 98765 43210, 9876543210, 09876543210
    # At least 7-10 digits, optionally with +, -, (), spaces
    "PHONE": re.compile(r"\+?\d[\d\s\-\(\)]{7,}\d"),
    
    # Usernames: @username
    "USERNAME": re.compile(r"@[a-zA-Z0-9_]{3,}"),
    
    # Device ID / IPv4 (Basic pattern)
    "DEVICE_ID": re.compile(r"\b(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b|\b(?:\d{1,3}\.){3}\d{1,3}\b")
}

# Known false positives that should not be redacted
ALLOWLIST = [
    "@groww",
    "@zerodha",
    "@upstox",
    "@paytm",
    "@phonepe",
    "@gpay"
]
