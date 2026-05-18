from __future__ import annotations

import os
import sys
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
REPORT_FILE = BASE_DIR / "output" / "intraday_candidates.md"
TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 3900


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


def validate_report_file(path: Path = REPORT_FILE) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el informe {path}. Ejecuta primero python intraday_analyzer.py"
        )

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"El informe {path} esta vacio.")
    return content


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    chunks: list[str] = []
    current = ""

    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            for start in range(0, len(line), limit):
                chunks.append(line[start : start + limit].rstrip())
            continue

        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line

    if current.strip():
        chunks.append(current.rstrip())

    return chunks


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Error HTTP al enviar Telegram ({response.status_code}): {response.text}"
        )

    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rechazo el mensaje: {payload}")


def send_report() -> None:
    bot_token = get_required_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_required_env("TELEGRAM_CHAT_ID")
    report = validate_report_file()

    send_telegram_message(bot_token, chat_id, "📈 Informe diario de candidatas intradía")

    chunks = split_message(report)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"Parte {index}/{len(chunks)}\n\n" if len(chunks) > 1 else ""
        send_telegram_message(bot_token, chat_id, prefix + chunk)

    print(f"Informe enviado correctamente por Telegram en {len(chunks)} parte(s).")


def main() -> int:
    try:
        send_report()
        return 0
    except Exception as exc:  # noqa: BLE001 - show a clear CLI error and fail.
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
