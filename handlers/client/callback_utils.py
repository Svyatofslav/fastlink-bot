from __future__ import annotations


def extract_callback_id(data: str | None, prefix: str) -> int | None:
    """Извлекает числовой id из callback_data вида `{prefix}:{id}`."""
    if data is None or not data.startswith(f"{prefix}:"):
        return None

    raw_id = data.rsplit(":", 1)[-1]
    if not raw_id.isdigit():
        return None

    return int(raw_id)
