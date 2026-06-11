from fastapi import Request


def get_client_ip(request: Request | None) -> str | None:
    """Return the real client IP, honouring X-Forwarded-For set by Caddy."""
    if not request:
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None
