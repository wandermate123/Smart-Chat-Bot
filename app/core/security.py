import hashlib
import hmac


def verify_meta_signature(
    body: bytes, signature_header: str | None, app_secret: str
) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received = signature_header.removeprefix("sha256=")
    expected = hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)
