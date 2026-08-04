"""Application paths and runtime configuration."""

from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

WATCHLIST_FILE = DATA_DIR / "stocks_config.json"
WATCHLIST_EXAMPLE_FILE = DATA_DIR / "stocks_config.example.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
RESULTS_CACHE_FILE = DATA_DIR / "last_results.json"

# Number of tickers fetched concurrently. yfinance is network-bound, so a
# handful of threads is plenty and keeps us well clear of Yahoo's rate limits.
MAX_FETCH_WORKERS = 6

# Points kept in the price series used to draw the sparkline. One year of
# daily candles is ~252 rows; downsampling keeps the cached payload small.
SPARKLINE_POINTS = 80

load_dotenv(BASE_DIR / ".env")

DATA_DIR.mkdir(exist_ok=True)
