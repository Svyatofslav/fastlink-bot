from __future__ import annotations

from pathlib import Path
import sys
import os

from dotenv import load_dotenv

from config import get_settings, get_crypto_key

# 1. Настроить sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Загрузить .env и .env.local ДО импортов тестовых модулей
if os.path.exists(".env"):
    load_dotenv(".env", override=False)
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

# 3. Сбросить кэш настроек, чтобы Settings() пересоздался с уже загруженными env
get_settings.cache_clear()
get_crypto_key.cache_clear()
