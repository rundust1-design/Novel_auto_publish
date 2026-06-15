"""Simple publish-result logger.  One line per chapter in logs/publish.log."""

import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "publish.log")


def log_result(platform_key, filename, success, reason=""):
    """Write one result line to the publish log.

    Args:
        platform_key: e.g. 'fanqie', 'migu'
        filename:    base name of the chapter file, e.g. '第32章 红册画圈.txt'
        success:     True if published, False if failed
        reason:      failure reason (empty on success)
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if success else "FAIL"
    line = f"[{timestamp}] {platform_key} {filename} {status}"
    if not success and reason:
        line += f"  |  {reason}"
    line += "\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
