"""Позволяет запускать пакет как модуль: python -m bot"""

from __future__ import annotations

import asyncio
import sys

from bot.main import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
