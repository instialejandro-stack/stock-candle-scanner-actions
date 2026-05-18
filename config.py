from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

UNIVERSE_CSV = DATA_DIR / "trade_republic_stocks.csv"
CURRENT_OUTPUT_CSV = OUTPUT_DIR / "top10_bullish_candles.csv"
CURRENT_OUTPUT_MD = OUTPUT_DIR / "top10_bullish_candles.md"
HISTORY_OUTPUT_CSV = OUTPUT_DIR / "history_top10_bullish_candles.csv"
INTRADAY_OUTPUT_CSV = OUTPUT_DIR / "intraday_candidates.csv"
INTRADAY_OUTPUT_MD = OUTPUT_DIR / "intraday_candidates.md"
HISTORY_INTRADAY_OUTPUT_CSV = OUTPUT_DIR / "history_intraday_candidates.csv"

YFINANCE_PERIOD = "10d"
YFINANCE_INTERVAL = "1d"
ANALYZER_DAILY_PERIOD = "3mo"
ANALYZER_INTRADAY_PERIOD = "2d"
ANALYZER_INTRADAY_INTERVAL = "5m"

TOP_N = 10

BASE_COLUMNS = [
    "rank",
    "date",
    "ticker",
    "name",
    "isin",
    "open",
    "close",
    "high",
    "low",
    "body",
    "body_pct",
    "volume",
]

INTRADAY_COLUMNS = [
    "rank",
    "date",
    "ticker",
    "name",
    "isin",
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

INTRADAY_MARKDOWN_COLUMNS = [
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
