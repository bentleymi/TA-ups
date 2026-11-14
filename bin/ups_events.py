#!/usr/bin/env python3
"""Emit one JSON event per cycle with per-device UPS health."""
import sys

from ups_common import discover, emit

ABSENT = {"status": "absent", "backend": None, "device_count": 0, "ups": {}}


def main():
    try:
        emit(discover())
    except Exception:
        emit(dict(ABSENT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
