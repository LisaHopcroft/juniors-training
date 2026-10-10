import pandas as pd

def to_seconds(s):
    """Convert 'mm:ss.s' (e.g. '02:38.8') to seconds (158.8)."""
    if pd.isna(s) or str(s).strip() == "":
        return float("nan")
    minutes, seconds = str(s).strip().split(":")
    return int(minutes) * 60 + float(seconds)


def to_mmss(x):
    """Convert seconds back to 'm:ss.s' for display."""
    if pd.isna(x):
        return ""
    m, s = divmod(x, 60)
    return f"{int(m)}:{s:04.1f}"
