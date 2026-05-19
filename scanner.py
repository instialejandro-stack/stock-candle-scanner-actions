from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "trade_republic_stocks.csv"
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / ".cache" / "yfinance"
CURRENT_OUTPUT_FILE = OUTPUT_DIR / "top10_bullish_candles.csv"
HISTORY_OUTPUT_FILE = OUTPUT_DIR / "history_top10_bullish_candles.csv"

YFINANCE_PERIOD = "10d"
YFINANCE_INTERVAL = "1d"
TOP_N = 10
LOCAL_TZ = ZoneInfo("Atlantic/Canary")

REQUIRED_INPUT_COLUMNS = ["ticker", "name", "isin", "market", "trade_republic_status"]
YFINANCE_COLUMNS = ["Open", "Close", "High", "Low", "Volume"]
OUTPUT_COLUMNS = [
    "rank",
    "date",
    "ticker",
    "name",
    "isin",
    "market",
    "trade_republic_status",
    "open",
    "close",
    "high",
    "low",
    "body",
    "body_pct",
    "volume",
]


def ensure_directories() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(CACHE_DIR))


def normalize_trade_republic_status(value: str) -> str:
    return str(value).strip().casefold()


def validate_input_file(path: Path = DATA_FILE) -> tuple[pd.DataFrame, int, int]:
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el archivo de entrada: {path}. "
            "Crea data/trade_republic_stocks.csv con columnas "
            "ticker,name,isin,market,trade_republic_status."
        )

    stocks = pd.read_csv(path, dtype=str).fillna("")
    stocks.columns = [column.strip().lower() for column in stocks.columns]

    missing_columns = [
        column for column in REQUIRED_INPUT_COLUMNS if column not in stocks.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(
            f"Faltan columnas obligatorias en {path}: {missing}. "
            "El CSV debe incluir ticker,name,isin,market,trade_republic_status. "
            "Marca como Disponible las acciones que deban analizarse."
        )

    stocks = stocks[REQUIRED_INPUT_COLUMNS].copy()
    for column in REQUIRED_INPUT_COLUMNS:
        stocks[column] = stocks[column].astype(str).str.strip()

    stocks = stocks[stocks["ticker"] != ""]
    stocks = stocks[~stocks["ticker"].str.startswith("^")]
    stocks = stocks.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    total_tickers = len(stocks)

    available_mask = (
        stocks["trade_republic_status"].map(normalize_trade_republic_status)
        == "disponible"
    )
    available_stocks = stocks[available_mask].reset_index(drop=True)
    excluded_tickers = total_tickers - len(available_stocks)

    return available_stocks, total_tickers, excluded_tickers


def flatten_yfinance_columns(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data.columns, pd.MultiIndex):
        return data

    flattened = data.copy()
    first_level = list(flattened.columns.get_level_values(0))
    last_level = list(flattened.columns.get_level_values(-1))

    if set(YFINANCE_COLUMNS).issubset(first_level):
        flattened.columns = flattened.columns.get_level_values(0)
    elif set(YFINANCE_COLUMNS).issubset(last_level):
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
        period=YFINANCE_PERIOD,
        interval=YFINANCE_INTERVAL,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    data = flatten_yfinance_columns(data)

    if data.empty:
        return data

    missing_columns = [column for column in YFINANCE_COLUMNS if column not in data.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Yahoo Finance no devolvio columnas esperadas: {missing}")

    return data.dropna(subset=YFINANCE_COLUMNS)


def get_last_bullish_candle(stock: pd.Series) -> dict | None:
    ticker = stock["ticker"]
    data = download_daily_data(ticker)

    if data.empty:
        print(f"[INFO] {ticker}: sin datos diarios completos.")
        return None

    latest = data.iloc[-1]
    open_price = float(latest["Open"])
    close_price = float(latest["Close"])

    if open_price <= 0:
        print(f"[ERROR] {ticker}: open no valido para calcular body_pct.")
        return None

    if close_price <= open_price:
        return None

    high_price = float(latest["High"])
    low_price = float(latest["Low"])
    body = close_price - open_price
    body_pct = (body / open_price) * 100
    date = pd.Timestamp(data.index[-1]).date().isoformat()

    return {
        "date": date,
        "ticker": ticker,
        "name": stock["name"],
        "isin": stock["isin"],
        "market": stock["market"],
        "trade_republic_status": stock["trade_republic_status"],
        "open": open_price,
        "close": close_price,
        "high": high_price,
        "low": low_price,
        "body": body,
        "body_pct": body_pct,
        "volume": int(latest["Volume"]),
    }


def format_output(data: pd.DataFrame) -> pd.DataFrame:
    formatted = data.copy()
    for column in ["open", "close", "high", "low", "body"]:
        if column in formatted.columns:
            formatted[column] = pd.to_numeric(formatted[column], errors="coerce").round(4)

    if "body_pct" in formatted.columns:
        formatted["body_pct"] = pd.to_numeric(
            formatted["body_pct"], errors="coerce"
        ).round(2)

    if "volume" in formatted.columns:
        formatted["volume"] = pd.to_numeric(
            formatted["volume"], errors="coerce"
        ).astype("Int64")

    return formatted.reindex(columns=OUTPUT_COLUMNS)


def build_top10_bullish_candles(stocks: pd.DataFrame) -> pd.DataFrame:
    bullish_rows: list[dict] = []

    for index, stock in stocks.iterrows():
        ticker = stock["ticker"]
        try:
            candle = get_last_bullish_candle(stock)
            if candle:
                bullish_rows.append(candle)
        except Exception as exc:  # noqa: BLE001 - ticker failures should not stop the scan.
            print(f"[ERROR] {ticker}: {exc}")

        if (index + 1) % 25 == 0:
            print(f"[INFO] Procesados {index + 1}/{len(stocks)} tickers.")

    if not bullish_rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    top10 = (
        pd.DataFrame(bullish_rows)
        .sort_values("body_pct", ascending=False)
        .head(TOP_N)
        .reset_index(drop=True)
    )
    top10.insert(0, "rank", range(1, len(top10) + 1))
    return format_output(top10)


def update_history(top10: pd.DataFrame) -> pd.DataFrame:
    ensure_directories()
    current = format_output(top10)

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
    combined.to_csv(HISTORY_OUTPUT_FILE, index=False)
    return combined


def print_table(top10: pd.DataFrame) -> None:
    if top10.empty:
        print("No se encontraron velas alcistas en la ultima sesion disponible.")
        return

    print(top10.to_markdown(index=False))


def main() -> int:
    try:
        ensure_directories()
        execution_time = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        stocks, total_tickers, excluded_tickers = validate_input_file()

        print(f"Hora de ejecucion: {execution_time}")
        print(f"Tickers totales en CSV: {total_tickers}")
        print(f"Tickers disponibles analizados: {len(stocks)}")
        print(f"Tickers excluidos: {excluded_tickers}")
        print()

        top10 = build_top10_bullish_candles(stocks)
        top10.to_csv(CURRENT_OUTPUT_FILE, index=False)
        update_history(top10)

        print_table(top10)
        print()
        print(f"Archivo actualizado: {CURRENT_OUTPUT_FILE}")
        print(f"Historico actualizado: {HISTORY_OUTPUT_FILE}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
