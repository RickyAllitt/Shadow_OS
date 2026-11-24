import re

def get_csrf_from_response(response):
    """Extracts CSRF token from HTML response."""
    html = response.data.decode('utf-8')
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def one_reset_ago():
    """
    A last_daily_reset timestamp from which exactly ONE daily reset (01:00 Madrid) is due now,
    at any time of day. ("now - 25h" processes two resets during the hour after 01:00.)
    """
    from datetime import datetime, timedelta, timezone
    from app.services import get_latest_daily_reset_time
    latest = get_latest_daily_reset_time().astimezone(timezone.utc)
    return latest - timedelta(days=1) + timedelta(minutes=1)
