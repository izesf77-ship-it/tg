"""Скрипт запуска бота: python run.py"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
