from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / ".cache" / "yfinance"
INPUT_FILE = OUTPUT_DIR / "top10_bullish_candles.csv"
CURRENT_OUTPUT_FILE = OUTPUT_DIR / "intraday_candidates.csv"
MARKDOWN_OUTPUT_FILE = OUTPUT_DIR / "intraday_candidates.md"
HISTORY_OUTPUT_FILE = OUTPUT_DIR / "history_intraday_candidates.csv"

LOCAL_TZ = ZoneInfo("Atlantic/Canary")
DAILY_PERIOD = "60d"
DAILY_INTERVAL = "1d"
INTRADAY_PERIOD = "2d"
INTRADAY_INTERVAL = "5m"

INPUT_COLUMNS = [
    "rank",
    "date",
    "ticker",
    "name",
    "isin",
    "market",
    "open",
    "close",
    "high",
    "low",
    "body",
    "body_pct",
    "volume",
]

DAILY_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

OUTPUT_COLUMNS = [
    "rank",
    "date",
    "ticker",
    "name",
    "isin",
    "market",
    "previous_open",
    "previous_close",
    "previous_high",
    "previous_low",
    "body",
    "body_pct",
    "last_volume",
    "avg_volume_20d",
    "relative_volume",
    "return_5d",
    "return_10d",
    "return_20d",
    "atr_14",
    "atr_pct",
    "close_position",
    "distance_to_20d_high_pct",
    "gap_pct",
    "score",
    "classification",
    "notes",
]

MARKDOWN_COLUMNS = [
    "rank",
    "ticker",
    "name",
    "body_pct",
    "relative_volume",
    "return_5d",
    "atr_pct",
    "close_position",
    "gap_pct",
    "score",
    "classification",
    "notes",
]

CONSOLE_COLUMNS = [
    "rank",
    "ticker",
    "name",
    "body_pct",
    "relative_volume",
    "return_5d",
    "atr_pct",
    "score",
    "classification",
]

RISK_WARNING = (
    "Este informe no constituye asesoramiento financiero. Las acciones clasificadas "
    "como candidatas intradía se seleccionan únicamente mediante criterios "
    "cuantitativos. Antes de operar debe revisarse la liquidez, el spread, la "
    "volatilidad, las noticias relevantes, el contexto del mercado y definir un "
    "stop loss."
)

PRIORITY_ORDER = {
    "Descartar": 0,
    "Baja prioridad": 1,
    "Media prioridad": 2,
    "Alta prioridad": 3,
}


def ensure_directories() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(CACHE_DIR))


def validate_input_file(path: Path = INPUT_FILE) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Ejecuta primero: python scanner.py"
        )

    data = pd.read_csv(path)
    data.columns = [column.strip().lower() for column in data.columns]

    missing_columns = [column for column in INPUT_COLUMNS if column not in data.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Faltan columnas obligatorias en {path}: {missing}")

    data = data[INPUT_COLUMNS].copy()
    data["ticker"] = data["ticker"].astype(str).str.strip()
    data = data[data["ticker"] != ""]
    return data.reset_index(drop=True)


def flatten_yfinance_columns(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data.columns, pd.MultiIndex):
        return data

    flattened = data.copy()
    first_level = list(flattened.columns.get_level_values(0))
    last_level = list(flattened.columns.get_level_values(-1))

    if set(DAILY_COLUMNS).issubset(first_level):
        flattened.columns = flattened.columns.get_level_values(0)
    elif set(DAILY_COLUMNS).issubset(last_level):
        flattened.columns = flattened.columns.get_level_values(-1)
    else:
        flattened.columns = [
            "_".join(str(part) for part in column if str(part))
            for column in flattened.columns.to_flat_index()
        ]

    return flattened


def download_daily_data(ticker: str) -> pd.DataFrame:
    data = yf.download(
        ticker,
        period=DAILY_PERIOD,
        interval=DAILY_INTERVAL,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    data = flatten_yfinance_columns(data)

    if data.empty:
        return data

    missing_columns = [column for column in DAILY_COLUMNS if column not in data.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Yahoo Finance no devolvio columnas esperadas: {missing}")

    return data.dropna(subset=DAILY_COLUMNS)


def calculate_returns(data: pd.DataFrame) -> dict[str, float | None]:
    returns: dict[str, float | None] = {}
    close = data["Close"]
    last_close = float(close.iloc[-1]) if not close.empty else 0.0

    for days in [5, 10, 20]:
        key = f"return_{days}d"
        if len(close) <= days or last_close <= 0:
            returns[key] = None
            continue

        previous_close = float(close.iloc[-days - 1])
        if previous_close <= 0:
            returns[key] = None
            continue

        returns[key] = ((last_close / previous_close) - 1) * 100

    return returns


def calculate_atr(data: pd.DataFrame) -> tuple[float | None, float | None]:
    if len(data) < 15:
        return None, None

    previous_close = data["Close"].shift(1)
    true_range = pd.concat(
        [
            data["High"] - data["Low"],
            (data["High"] - previous_close).abs(),
            (data["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_14 = float(true_range.tail(14).mean())
    last_close = float(data["Close"].iloc[-1])
    if last_close <= 0:
        return atr_14, None

    return atr_14, (atr_14 / last_close) * 100


def calculate_gap(ticker: str, previous_close: float) -> float | None:
    if previous_close <= 0:
        return None

    try:
        fast_info = yf.Ticker(ticker).fast_info
        current_price = fast_info.get("last_price") if fast_info else None
        if current_price and float(current_price) > 0:
            return ((float(current_price) - previous_close) / previous_close) * 100
    except Exception:
        pass

    try:
        intraday = yf.download(
            ticker,
            period=INTRADAY_PERIOD,
            interval=INTRADAY_INTERVAL,
            prepost=True,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        intraday = flatten_yfinance_columns(intraday)
        if intraday.empty or "Close" not in intraday.columns:
            return None

        intraday = intraday.dropna(subset=["Close"])
        if intraday.empty:
            return None

        latest_price = float(intraday["Close"].iloc[-1])
        if latest_price <= 0:
            return None

        return ((latest_price - previous_close) / previous_close) * 100
    except Exception:
        return None


def score_body_strength(body_pct: float) -> int:
    if body_pct >= 10:
        return 20
    if body_pct >= 5:
        return 15
    if body_pct >= 2:
        return 8
    return 3


def score_relative_volume(relative_volume: float | None) -> int:
    if relative_volume is None:
        return 0
    if relative_volume >= 3:
        return 20
    if relative_volume >= 2:
        return 15
    if relative_volume >= 1.5:
        return 10
    if relative_volume >= 1:
        return 5
    return 0


def score_trend(
    return_5d: float | None,
    return_10d: float | None,
    return_20d: float | None,
) -> int:
    score = 0
    if return_5d is not None and return_5d > 0:
        score += 5
    if return_10d is not None and return_10d > 0:
        score += 5
    if return_20d is not None and return_20d > 0:
        score += 5
    return score


def score_liquidity(avg_volume_20d: float | None) -> int:
    if avg_volume_20d is None:
        return 0
    if avg_volume_20d >= 1_000_000:
        return 10
    if avg_volume_20d >= 300_000:
        return 5
    return 0


def score_atr(atr_pct: float | None) -> int:
    if atr_pct is None:
        return 0
    if 3 <= atr_pct <= 8:
        return 10
    if 2 <= atr_pct < 3:
        return 6
    if 8 < atr_pct <= 12:
        return 5
    return 2


def score_close_position(close_position: float) -> int:
    if close_position >= 0.8:
        return 10
    if close_position >= 0.6:
        return 7
    if close_position >= 0.5:
        return 4
    return 0


def score_distance_to_high(distance_to_20d_high_pct: float | None) -> int:
    if distance_to_20d_high_pct is None:
        return 0
    if distance_to_20d_high_pct <= 2:
        return 5
    if distance_to_20d_high_pct <= 5:
        return 3
    return 0


def score_gap(gap_pct: float | None) -> tuple[int, int]:
    if gap_pct is None:
        return 0, 0
    if 0 <= gap_pct <= 4:
        return 10, 10
    if 4 < gap_pct <= 8:
        return 5, 10
    if -3 <= gap_pct < 0:
        return 3, 10
    return 0, 10


def calculate_penalties(
    body_pct: float,
    return_5d: float | None,
    gap_pct: float | None,
    atr_pct: float | None,
) -> tuple[int, list[str]]:
    penalty = 0
    notes: list[str] = []

    if body_pct > 20:
        penalty += 8
        notes.append("cuerpo de vela extremadamente alto")
    if return_5d is not None and return_5d > 30:
        penalty += 7
        notes.append("subida acumulada de 5 dias superior al 30%")
    if gap_pct is not None and gap_pct > 10:
        penalty += 5
        notes.append("gap superior al 10%")
    if atr_pct is not None and atr_pct > 15:
        penalty += 5
        notes.append("ATR superior al 15%")

    return min(penalty, 25), notes


def calculate_total_score(points: int, available_points: int, penalty: int) -> float:
    if available_points <= 0:
        return 0.0

    normalized = (points / available_points) * 100
    return max(0.0, min(100.0, normalized - penalty))


def clean_negative_zero(value: float | int | None) -> float | int | None:
    if value is None or pd.isna(value):
        return value
    if isinstance(value, (int, float)) and abs(float(value)) < 0.05:
        return 0.0
    return value


def classify_score(score: float) -> str:
    if score >= 75:
        return "Alta prioridad"
    if score >= 60:
        return "Media prioridad"
    if score >= 45:
        return "Baja prioridad"
    return "Descartar"


def liquidity_cap(avg_volume_20d: float | None) -> str:
    if avg_volume_20d is None or avg_volume_20d < 300_000:
        return "Baja prioridad"
    if avg_volume_20d < 1_000_000:
        return "Media prioridad"
    return "Alta prioridad"


def apply_liquidity_cap(
    classification: str,
    avg_volume_20d: float | None,
) -> tuple[str, str | None]:
    cap = liquidity_cap(avg_volume_20d)
    capped_priority = min(PRIORITY_ORDER[classification], PRIORITY_ORDER[cap])
    final_classification = {
        priority: label for label, priority in PRIORITY_ORDER.items()
    }[capped_priority]

    if final_classification == classification:
        return final_classification, None

    threshold = "300.000" if cap == "Baja prioridad" else "1.000.000"
    note = (
        f"Score alto, pero clasificacion limitada a {final_classification} "
        f"por volumen medio inferior a {threshold}."
    )
    return final_classification, note


def build_notes(
    body_pct: float,
    relative_volume: float | None,
    return_5d: float | None,
    atr_pct: float | None,
    close_position: float,
    gap_pct: float | None,
    penalty_notes: list[str],
    liquidity_note: str | None,
    missing_notes: list[str],
) -> str:
    notes: list[str] = []

    if body_pct >= 5:
        notes.append("fuerte vela alcista")
    elif body_pct >= 2:
        notes.append("buen cuerpo alcista")
    else:
        notes.append("cuerpo alcista reducido")

    if relative_volume is None or relative_volume < 1:
        notes.append("volumen relativo debil")
    elif relative_volume >= 2:
        notes.append("volumen relativo alto")

    if close_position >= 0.8:
        notes.append("cierre cerca de maximos")
    elif close_position < 0.5:
        notes.append("cierre lejos del maximo diario")

    if return_5d is not None and return_5d > 30:
        notes.append("riesgo por subida acumulada")
    if atr_pct is not None and atr_pct > 12:
        notes.append("volatilidad elevada")
    if gap_pct is None:
        notes.append("gap no disponible")

    notes.extend(penalty_notes)
    notes.extend(missing_notes)

    if liquidity_note:
        notes.append(liquidity_note)

    clean_notes = []
    for note in notes:
        if note and note not in clean_notes:
            clean_notes.append(note)

    return ". ".join(clean_notes[:5]) + "."


def analyze_ticker(row: pd.Series) -> tuple[dict | None, str | None]:
    ticker = str(row["ticker"])

    try:
        data = download_daily_data(ticker)
        if data.empty:
            return None, "sin datos diarios completos"

        previous_open = float(row["open"])
        previous_close = float(row["close"])
        previous_high = float(row["high"])
        previous_low = float(row["low"])
        body = float(row["body"])
        body_pct = float(row["body_pct"])
        last_volume = float(row["volume"])

        avg_volume_20d = (
            float(data["Volume"].tail(20).mean()) if len(data) >= 1 else None
        )
        relative_volume = (
            last_volume / avg_volume_20d
            if avg_volume_20d is not None and avg_volume_20d > 0
            else None
        )

        returns = calculate_returns(data)
        return_5d = returns["return_5d"]
        return_10d = returns["return_10d"]
        return_20d = returns["return_20d"]
        atr_14, atr_pct = calculate_atr(data)

        candle_range = previous_high - previous_low
        close_position = (
            (previous_close - previous_low) / candle_range if candle_range > 0 else 0.0
        )
        close_position = max(0.0, min(1.0, close_position))

        high_20d = float(data["High"].tail(20).max()) if len(data) >= 1 else None
        distance_to_20d_high_pct = (
            ((high_20d - previous_close) / previous_close) * 100
            if high_20d is not None and previous_close > 0
            else None
        )

        gap_pct = calculate_gap(ticker, previous_close)
        if gap_pct is not None and abs(gap_pct) < 0.5:
            gap_pct = None

        missing_notes: list[str] = []
        if return_5d is None or return_10d is None or return_20d is None:
            missing_notes.append("rentabilidad reciente incompleta")
        if atr_14 is None or atr_pct is None:
            missing_notes.append("ATR incompleto")
        if relative_volume is None:
            missing_notes.append("volumen relativo no disponible")

        gap_points, gap_available_points = score_gap(gap_pct)
        points = (
            score_body_strength(body_pct)
            + score_relative_volume(relative_volume)
            + score_trend(return_5d, return_10d, return_20d)
            + score_liquidity(avg_volume_20d)
            + score_atr(atr_pct)
            + score_close_position(close_position)
            + score_distance_to_high(distance_to_20d_high_pct)
            + gap_points
        )
        available_points = 90 + gap_available_points

        penalty, penalty_notes = calculate_penalties(
            body_pct=body_pct,
            return_5d=return_5d,
            gap_pct=gap_pct,
            atr_pct=atr_pct,
        )
        score = calculate_total_score(points, available_points, penalty)
        base_classification = classify_score(score)
        classification, liquidity_note = apply_liquidity_cap(
            base_classification, avg_volume_20d
        )

        return {
            "date": row["date"],
            "ticker": ticker,
            "name": row["name"],
            "isin": row["isin"],
            "market": row["market"],
            "previous_open": previous_open,
            "previous_close": previous_close,
            "previous_high": previous_high,
            "previous_low": previous_low,
            "body": body,
            "body_pct": body_pct,
            "last_volume": int(last_volume),
            "avg_volume_20d": avg_volume_20d,
            "relative_volume": relative_volume,
            "return_5d": return_5d,
            "return_10d": return_10d,
            "return_20d": return_20d,
            "atr_14": atr_14,
            "atr_pct": atr_pct,
            "close_position": close_position,
            "distance_to_20d_high_pct": distance_to_20d_high_pct,
            "gap_pct": gap_pct,
            "score": score,
            "classification": classification,
            "notes": build_notes(
                body_pct=body_pct,
                relative_volume=relative_volume,
                return_5d=return_5d,
                atr_pct=atr_pct,
                close_position=close_position,
                gap_pct=gap_pct,
                penalty_notes=penalty_notes,
                liquidity_note=liquidity_note,
                missing_notes=missing_notes,
            ),
        }, None
    except Exception as exc:  # noqa: BLE001 - ticker failures should not stop analysis.
        return None, str(exc)


def build_intraday_candidates(top10: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []

    for index, row in top10.iterrows():
        ticker = row["ticker"]
        print(f"[INFO] Analizando {ticker} ({index + 1}/{len(top10)})")
        result, error = analyze_ticker(row)
        if error:
            print(f"[ERROR] {ticker}: {error}")
            errors.append({"ticker": ticker, "error": error})
            continue
        if result:
            rows.append(result)

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), errors

    candidates = (
        pd.DataFrame(rows)
        .sort_values("score", ascending=False)
        .reset_index(drop=True)
    )
    candidates.insert(0, "rank", range(1, len(candidates) + 1))
    return format_output(candidates), errors


def format_output(data: pd.DataFrame) -> pd.DataFrame:
    formatted = data.copy()
    decimal_columns = [
        "previous_open",
        "previous_close",
        "previous_high",
        "previous_low",
        "body",
        "body_pct",
        "avg_volume_20d",
        "relative_volume",
        "return_5d",
        "return_10d",
        "return_20d",
        "atr_14",
        "atr_pct",
        "close_position",
        "distance_to_20d_high_pct",
        "gap_pct",
        "score",
    ]

    for column in decimal_columns:
        if column in formatted.columns:
            formatted[column] = pd.to_numeric(formatted[column], errors="coerce").round(2)
            formatted[column] = formatted[column].map(clean_negative_zero)

    if "close_position" in formatted.columns:
        formatted["close_position"] = pd.to_numeric(
            formatted["close_position"], errors="coerce"
        ).clip(lower=0, upper=1)

    if "score" in formatted.columns:
        formatted["score"] = pd.to_numeric(
            formatted["score"], errors="coerce"
        ).clip(lower=0, upper=100)

    if "last_volume" in formatted.columns:
        formatted["last_volume"] = pd.to_numeric(
            formatted["last_volume"], errors="coerce"
        ).astype("Int64")

    return formatted.reindex(columns=OUTPUT_COLUMNS)


def save_markdown_report(df: pd.DataFrame) -> None:
    generated_at = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    markdown_df = format_output(df).reindex(columns=MARKDOWN_COLUMNS).fillna("N/A")
    table = markdown_df.to_markdown(index=False)
    content = (
        "# Informe de candidatas intradía\n\n"
        f"Fecha de generacion: {generated_at}\n\n"
        f"{table}\n\n"
        "## Advertencia de riesgo\n\n"
        f"{RISK_WARNING}\n"
    )
    MARKDOWN_OUTPUT_FILE.write_text(content, encoding="utf-8")


def update_history(df: pd.DataFrame) -> pd.DataFrame:
    current = format_output(df)

    if HISTORY_OUTPUT_FILE.exists():
        history = pd.read_csv(HISTORY_OUTPUT_FILE)
        combined = pd.concat([history, current], ignore_index=True)
    else:
        combined = current.copy()

    if combined.empty:
        combined = pd.DataFrame(columns=OUTPUT_COLUMNS)
    else:
        combined = combined.drop_duplicates(subset=["date", "ticker"], keep="last")
        combined = combined.sort_values(["date", "rank"], ascending=[False, True])

    combined = format_output(combined)
    combined.to_csv(HISTORY_OUTPUT_FILE, index=False, na_rep="N/A")
    return combined


def print_table(df: pd.DataFrame) -> None:
    if df.empty:
        print("No se pudieron generar candidatas intradia.")
        return

    compact = format_output(df).reindex(columns=CONSOLE_COLUMNS).fillna("N/A")
    print(compact.to_markdown(index=False))


def print_summary(df: pd.DataFrame, analyzed_count: int) -> None:
    classifications = df["classification"] if "classification" in df.columns else pd.Series(dtype=str)

    print("Resumen intradia")
    print(f"- Acciones analizadas: {analyzed_count}")
    print(f"- Alta prioridad: {(classifications == 'Alta prioridad').sum()}")
    print(f"- Media prioridad: {(classifications == 'Media prioridad').sum()}")
    print(f"- Baja prioridad: {(classifications == 'Baja prioridad').sum()}")
    print(f"- Descartar: {(classifications == 'Descartar').sum()}")
    print(f"- CSV: {CURRENT_OUTPUT_FILE}")
    print(f"- Markdown: {MARKDOWN_OUTPUT_FILE}")
    print(f"- Historico: {HISTORY_OUTPUT_FILE}")


def main() -> int:
    try:
        ensure_directories()
        top10 = validate_input_file()
        print(f"Tickers cargados desde {INPUT_FILE}: {len(top10)}")
        print()

        candidates, errors = build_intraday_candidates(top10)
        candidates.to_csv(CURRENT_OUTPUT_FILE, index=False, na_rep="N/A")
        save_markdown_report(candidates)
        update_history(candidates)

        print()
        print_table(candidates)
        print()
        print_summary(candidates, analyzed_count=len(top10))
        print(f"Errores: {len(errors)}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
