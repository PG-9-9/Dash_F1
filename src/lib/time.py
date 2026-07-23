import re
from typing import Optional


def format_time(seconds: float) -> str:
    """Format positive seconds as MM:SS.mmm for telemetry display."""
    if seconds is None or seconds < 0:
        return "N/A"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02}:{secs:06.3f}"


def parse_time_string(time_str: str) -> Optional[float]:
    """Parse FastF1 and CSV time strings into rounded total seconds."""
    if time_str is None:
        return None
    if "days" in str(time_str):
        time_str = str(time_str).split(" ", 2)[-1]
    else:
        time_str = str(time_str).split(" ")[0]

    s = str(time_str).strip()
    if not s:
        return None

    parts = re.split(r"[:.]", s)
    hh = 0
    micro = 0

    try:
        if len(parts) == 4:
            hh, mm, ss, micro = parts
        elif len(parts) == 3:
            if len(parts[2]) > 2:
                mm, ss, micro = parts
            else:
                hh, mm, ss = parts
        elif len(parts) == 2:
            mm, ss = parts
        else:
            return None

        hh = int(hh)
        mm = int(mm)
        ss = int(ss)
        micro = int(str(micro)[:6].ljust(6, "0")) if str(micro) else 0
        return round(hh * 3600 + mm * 60 + ss + micro / 1_000_000.0, 3)
    except (TypeError, ValueError):
        return None
