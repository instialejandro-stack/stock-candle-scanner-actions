from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
REPORT_FILE = BASE_DIR / "output" / "intraday_candidates.md"
CSV_FILE = BASE_DIR / "output" / "intraday_candidates.csv"
TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 3900
LOCAL_TZ = "Atlantic/Canary"


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


def validate_report_files(
    csv_path: Path = CSV_FILE,
    report_path: Path = REPORT_FILE,
) -> tuple[pd.DataFrame, str]:
    if not csv_path.exists():
        raise FileNotFoundError(
            "No existe output/intraday_candidates.csv. "
            "Ejecuta primero python intraday_analyzer.py."
        )
    if not report_path.exists():
        raise FileNotFoundError(
            "No existe output/intraday_candidates.md. "
            "Ejecuta primero python intraday_analyzer.py."
        )

    data = pd.read_csv(csv_path, na_values=["N/A"])
    content = report_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"El informe {report_path} esta vacio.")
    return data, content


def classification_counts(data: pd.DataFrame) -> dict[str, int]:
    classifications = (
        data["classification"] if "classification" in data.columns else pd.Series(dtype=str)
    )
    return {
        "Alta prioridad": int((classifications == "Alta prioridad").sum()),
        "Media prioridad": int((classifications == "Media prioridad").sum()),
        "Baja prioridad": int((classifications == "Baja prioridad").sum()),
        "Descartar": int((classifications == "Descartar").sum()),
    }


def best_candidate_message(data: pd.DataFrame) -> str:
    if data.empty:
        return "N/A"

    best = data.sort_values("score", ascending=False).iloc[0]
    return (
        f"{best['ticker']} - {best['name']}\n"
        f"Score: {best['score']}\n"
        f"Clasificación: {best['classification']}"
    )


def build_telegram_summary(data: pd.DataFrame) -> str:
    generated_at = pd.Timestamp.now(tz=LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    counts = classification_counts(data)
    return (
        "📈 Informe diario de candidatas intradía\n\n"
        f"Fecha: {generated_at}\n"
        f"Acciones analizadas: {len(data)}\n\n"
        f"🟢 Alta prioridad: {counts['Alta prioridad']}\n"
        f"🟡 Media prioridad: {counts['Media prioridad']}\n"
        f"🟠 Baja prioridad: {counts['Baja prioridad']}\n"
        f"🔴 Descartar: {counts['Descartar']}\n\n"
        "Mejor candidata:\n"
        f"{best_candidate_message(data)}\n\n"
        "📰 Noticias/resultados: pendiente revisión manual\n\n"
        "Antes de operar, revisar noticias, resultados, premarket, spread y stop loss."
    )


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
    data, report = validate_report_files()
    bot_token = get_required_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_required_env("TELEGRAM_CHAT_ID")

    send_telegram_message(bot_token, chat_id, build_telegram_summary(data))

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
