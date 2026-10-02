import re
_PATTERNS=[re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?([^'\"\s]+)"),re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")]
def redact_secrets(text):
    count=0;out=text
    for pattern in _PATTERNS:
        def repl(match):
            nonlocal count;count+=1
            return f"{match.group(1)}=<REDACTED_SECRET>" if match.lastindex and match.lastindex>=1 else "<REDACTED_SECRET>"
        out=pattern.sub(repl,out)
    return out,count
