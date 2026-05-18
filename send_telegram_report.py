from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parent
REPORT_FILE = BASE_DIR / "output" / "intraday_candidates.md"
CSV_FILE = BASE_DIR / "output" / "intraday_candidates.csv"
TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 3900
LOCAL_TZ = "Atlantic/Canary"

ACTIVE_COLUMNS = [
    "rank",
    "ticker",
    "name",
    "body_pct",
    "relative_volume",
    "score",
    "classification",
]


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


def build_active_candidates_message(data: pd.DataFrame) -> str:
    active = data[data["classification"] != "Descartar"].copy()
    if active.empty:
        return (
            "Candidatas activas\n\n"
            "No hay candidatas activas. Todas las acciones han sido clasificadas como Descartar."
        )

    active = active.reindex(columns=ACTIVE_COLUMNS)
    for column in ["body_pct", "relative_volume", "score"]:
        active[column] = pd.to_numeric(active[column], errors="coerce").round(2)

    return "Candidatas activas\n\n" + active.to_markdown(index=False)


def build_manual_checklist_message() -> str:
    return (
        "Revisión manual antes de operar:\n"
        "- Noticias recientes\n"
        "- Resultados empresariales\n"
        "- Premarket / apertura\n"
        "- Spread en Trade Republic\n"
        "- Liquidez real\n"
        "- Contexto de mercado y sector\n"
        "- Entrada, stop loss y objetivo"
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


def check_telegram_response(response: requests.Response, action: str) -> None:
    if response.status_code >= 400:
        raise RuntimeError(
            f"Error HTTP al {action} Telegram ({response.status_code}): {response.text}"
        )

    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rechazo la accion {action}: {payload}")


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
    check_telegram_response(response, "enviar mensaje a")


def send_telegram_document(bot_token: str, chat_id: str, document_path: Path) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendDocument"
    with document_path.open("rb") as document:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": "Informe completo de candidatas intradía",
            },
            files={"document": (document_path.name, document, "text/markdown")},
            timeout=60,
        )
    check_telegram_response(response, "enviar documento a")


def send_markdown_fallback(bot_token: str, chat_id: str, report: str) -> None:
    chunks = split_message(report)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"Parte {index}/{len(chunks)}\n\n" if len(chunks) > 1 else ""
        send_telegram_message(bot_token, chat_id, prefix + chunk)
    print(f"Informe Markdown enviado como texto en {len(chunks)} parte(s).")


def send_report() -> None:
    data, report = validate_report_files()
    bot_token = get_required_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_required_env("TELEGRAM_CHAT_ID")

    send_telegram_message(bot_token, chat_id, build_telegram_summary(data))
    send_telegram_message(bot_token, chat_id, build_active_candidates_message(data))
    send_telegram_message(bot_token, chat_id, build_manual_checklist_message())

    try:
        send_telegram_document(bot_token, chat_id, REPORT_FILE)
        print("Informe enviado correctamente por Telegram como documento.")
    except Exception as exc:  # noqa: BLE001 - fallback keeps the report deliverable.
        print(f"[WARN] No se pudo enviar el documento: {exc}", file=sys.stderr)
        print("[WARN] Enviando Markdown completo como mensajes divididos.", file=sys.stderr)
        send_markdown_fallback(bot_token, chat_id, report)


def main() -> int:
    try:
        send_report()
        return 0
    except Exception as exc:  # noqa: BLE001 - show a clear CLI error and fail.
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
