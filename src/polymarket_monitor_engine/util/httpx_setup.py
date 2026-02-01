from __future__ import annotations

import logging


def silence_httpx_logs() -> None:
    for logger_name in ("httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
