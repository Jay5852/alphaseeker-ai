# AlphaSeeker AI: Free Build Guide (Step-by-Step)

This guide turns your prototype into a cleaner, more scalable platform using only free tools. It follows the roadmap's Phase 1 (foundations) and part of Phase 2 (research rigor). Follow the steps in order and finish each checkpoint before moving on.

## 1. Goals and ground rules

- **Zero recurring cost**: free tiers, open-source software, and daily data only.
- **Swing trading first**: daily bars are free and small. Skip tick data and streaming until you can pay for them.
- **Portable by design**: every outside dependency (data, broker, hosting) sits behind an interface so you can swap it later.
- **Paper trade only** until the validation gates in Step 12 are passed. Nothing here places real orders.

## 2. The free stack

| Layer | Tool | Free-tier limit to know |
| --- | --- | --- |
| Code and CI | GitHub + GitHub Actions | Monthly CI minutes are capped |
| Database | PostgreSQL with TimescaleDB (self-hosted in Docker) | Limited by your disk |
| Backend API | FastAPI + Uvicorn | None |
| Worker / scheduler | Python worker container + cron or systemd | None |
| Hosting | Your own PC, a Raspberry Pi, or an Oracle Cloud Always Free VM | Free tiers can change; capacity is sometimes scarce |
| HTTPS | Caddy (automatic Let's Encrypt certificates) | Needs a domain; a free subdomain service works |
| Frontend | Keep Streamlit for now; later Vercel or Cloudflare Pages | Fine for personal use |
| Market data | Alpaca free tier (US), NSE/BSE bhavcopy files (India), SEC EDGAR, FRED, yfinance as backup | Daily or delayed data only |
| Alerts | Telegram bot | None meaningful |
| Monitoring | Grafana + Prometheus (optional) | Uses some RAM |
| ML | scikit-learn, LightGBM, Google Colab for heavy training | Colab sessions time out |

Check each vendor's current terms before relying on them, since free tiers change.

## 3. Target architecture

One machine running three containers, all started by Docker Compose:

1. **db**: PostgreSQL + TimescaleDB. Holds prices, signals, orders, positions, and equity snapshots.
2. **api**: FastAPI service. The dashboard, CLI, and future frontend all talk to it instead of touching the database directly.
3. **worker**: runs scheduled jobs (nightly data refresh, scans, position updates, Telegram alerts).

Data flow: data provider (free feed) → Parquet cache on disk → worker computes features and signals → database → API → dashboard and Telegram.

## 4. Step 0: Prerequisites

- A computer or VM with 2 GB RAM or more (4 GB is more comfortable).
- Docker and Docker Compose installed.
- Git and a GitHub account.
- Python 3.11+ for local development.
- Your existing AlphaSeeker repository, backed up (copy the folder and `trading_ledger.db` somewhere safe).

**Checkpoint:** `docker compose version` and `python --version` both work.

## 5. Step 1: Restructure the repository

Move toward a layout that separates the app from scripts and tests:

```
alphaseeker/
├── app/
│   ├── main.py            # FastAPI entry point
│   ├── config.py          # settings from environment variables
│   ├── db.py              # database connection
│   ├── data/              # provider interface + implementations + cache
│   ├── engines/           # swing, intraday, value (your existing logic)
│   ├── ml/                # features, meta-labeler, time predictor
│   ├── risk/              # manager, circuit breakers
│   ├── ledger/            # virtual broker, orders, positions
│   └── worker/            # scheduled jobs
├── migrations/            # SQL files
├── scripts/               # one-off tools (SQLite migration, backfills)
├── tests/
├── data_cache/            # Parquet files (git-ignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .gitignore
```

Add `.env`, `data_cache/`, `*.db`, and `__pycache__/` to `.gitignore` so secrets and data never reach GitHub.

**Checkpoint:** your existing scan code still runs from the new folders.

## 6. Step 2: Docker Compose stack

Create `.env` (never commit it):

```
POSTGRES_USER=alpha
POSTGRES_PASSWORD=change_me_to_a_long_random_value
POSTGRES_DB=alphaseeker
DATABASE_URL=postgresql://alpha:change_me_to_a_long_random_value@db:5432/alphaseeker
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

Create `Dockerfile` (runs as a non-root user, unlike the root-based systemd setup in your old deployment guide):

```
FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser && chown -R appuser /srv
USER appuser
```

Create `docker-compose.yml`:

```
services:
  db:
    image: timescale/timescaledb:latest-pg16
    env_file: .env
    volumes:
      - dbdata:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}']
      interval: 5s
      retries: 10
    restart: unless-stopped

  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    ports:
      - '127.0.0.1:8000:8000'
    volumes:
      - ./data_cache:/srv/data_cache
    restart: unless-stopped

  worker:
    build: .
    command: python -m app.worker.main
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./data_cache:/srv/data_cache
    restart: unless-stopped

volumes:
  dbdata:
```

Binding the API to `127.0.0.1` keeps it private until you put HTTPS in front of it (Step 9).

Start it:

```
docker compose up -d --build
docker compose logs -f
```

**Checkpoint:** `docker compose ps` shows `db` as healthy and `api` and `worker` running.

## 7. Step 3: Database schema

Save as `migrations/001_init.sql`. Files in that folder run automatically the first time the database volume is created.

```
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE prices_daily (
    symbol  TEXT NOT NULL,
    ts      DATE NOT NULL,
    open    DOUBLE PRECISION,
    high    DOUBLE PRECISION,
    low     DOUBLE PRECISION,
    close   DOUBLE PRECISION,
    volume  BIGINT,
    PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('prices_daily', 'ts', chunk_time_interval => INTERVAL '1 year');

CREATE TABLE signals (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol      TEXT NOT NULL,
    market      TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    entry       DOUBLE PRECISION,
    stop_loss   DOUBLE PRECISION,
    target_1    DOUBLE PRECISION,
    target_2    DOUBLE PRECISION,
    ml_win_prob DOUBLE PRECISION,
    meta        JSONB
);

CREATE TABLE orders (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    qty         NUMERIC NOT NULL,
    price       NUMERIC,
    status      TEXT NOT NULL DEFAULT 'NEW',
    signal_id   BIGINT REFERENCES signals(id),
    reason      TEXT
);

CREATE TABLE positions (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    opened_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at   TIMESTAMPTZ,
    qty         NUMERIC NOT NULL,
    entry       NUMERIC NOT NULL,
    stop_loss   NUMERIC NOT NULL,
    target_1    NUMERIC,
    target_2    NUMERIC,
    status      TEXT NOT NULL DEFAULT 'OPEN',
    realized_pnl NUMERIC DEFAULT 0
);

CREATE TABLE equity_snapshots (
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    equity  NUMERIC NOT NULL,
    cash    NUMERIC NOT NULL,
    drawdown_pct NUMERIC
);

CREATE TABLE audit_log (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    detail  JSONB
);
```

The `audit_log` table records every automated decision (why a trade was opened, why a breaker fired). Firms treat this as non-negotiable, and it makes debugging far easier.

Adapt the columns to match your existing ledger fields if they differ.

**Checkpoint:** `docker compose exec db psql -U alpha -d alphaseeker -c '\dt'` lists the tables.

## 8. Step 4: Data provider interface and Parquet cache

Save as `app/data/provider.py`. This is the abstraction that lets you swap free data for a paid feed later without touching strategy code.

```python
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

CACHE_DIR = Path('data_cache')


class MarketDataProvider(ABC):
    @abstractmethod
    def fetch_daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        '''Return columns: open, high, low, close, volume, indexed by date.'''


class YFinanceProvider(MarketDataProvider):
    def fetch_daily(self, symbol, start, end):
        import yfinance as yf
        df = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)[['open', 'high', 'low', 'close', 'volume']]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df.dropna()


class CachedProvider:
    '''Wraps any provider; downloads only what is missing and stores Parquet.'''

    def __init__(self, inner: MarketDataProvider):
        self.inner = inner
        CACHE_DIR.mkdir(exist_ok=True)

    def daily(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        path = CACHE_DIR / (symbol.replace('/', '_') + '.parquet')
        cached = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        need_from = start
        if not cached.empty:
            need_from = (cached.index.max() + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        if need_from <= end:
            fresh = self.inner.fetch_daily(symbol, need_from, end)
            cached = pd.concat([cached, fresh])
            cached = cached[~cached.index.duplicated(keep='last')].sort_index()
            if not cached.empty:
                cached.to_parquet(path)
        return cached.loc[start:end]
```

Add `pyarrow` and `pandas` to `requirements.txt` for Parquet support.

Later, write `AlpacaProvider` or an `NseBhavcopyProvider` that implements the same `fetch_daily` method and swap it in. Nothing else changes.

Two data-quality rules to apply from day one:

- **Validate every download**: reject rows with zero or negative prices, missing volume, or price jumps over a threshold that are not explained by a split.
- **Keep delisted symbols** in your research universe when you can. Testing only on stocks that survived to today inflates results (survivorship bias).

**Checkpoint:** calling `CachedProvider(YFinanceProvider()).daily('AAPL', '2023-01-01', '2026-10-01')` twice makes a network call only the first time.

## 9. Step 5: Migrate your SQLite ledger to PostgreSQL

Save as `scripts/migrate_sqlite.py`. It copies rows table by table. Run it once, after checking that column names match your new schema.

```python
import os
import sqlite3
import psycopg

SQLITE_PATH = 'data/trading_ledger.db'
# Map: sqlite table -> (postgres table, list of columns to copy)
TABLES = {
    'trades': ('positions', ['symbol', 'qty', 'entry', 'stop_loss', 'target_1', 'target_2', 'status']),
}

src = sqlite3.connect(SQLITE_PATH)
src.row_factory = sqlite3.Row

with psycopg.connect(os.environ['DATABASE_URL']) as dst:
    for s_table, (d_table, cols) in TABLES.items():
        rows = src.execute('SELECT ' + ', '.join(cols) + ' FROM ' + s_table).fetchall()
        placeholders = ', '.join(['%s'] * len(cols))
        sql = 'INSERT INTO ' + d_table + ' (' + ', '.join(cols) + ') VALUES (' + placeholders + ')'
        with dst.cursor() as cur:
            cur.executemany(sql, [tuple(r) for r in rows])
        print('copied', len(rows), 'rows into', d_table)
```

Before running, open your SQLite file and list its real table and column names, then edit the `TABLES` mapping to match. Keep the old `.db` file untouched as a backup.

**Checkpoint:** row counts in PostgreSQL match the SQLite counts for every migrated table.

## 10. Step 6: FastAPI service skeleton

Save as `app/main.py`:

```python
import os
import psycopg
from fastapi import FastAPI

app = FastAPI(title='AlphaSeeker API')


def get_conn():
    return psycopg.connect(os.environ['DATABASE_URL'])


@app.get('/health')
def health():
    with get_conn() as conn:
        conn.execute('SELECT 1')
    return {'status': 'ok'}


@app.get('/positions')
def positions():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, qty, entry, stop_loss, target_1, target_2 "
            "FROM positions WHERE status = 'OPEN' ORDER BY opened_at DESC"
        ).fetchall()
    keys = ['symbol', 'qty', 'entry', 'stop_loss', 'target_1', 'target_2']
    return [dict(zip(keys, r)) for r in rows]
```

Add `fastapi`, `uvicorn`, and `psycopg[binary]` to `requirements.txt`. Then open `http://localhost:8000/docs` for the automatic interactive API page.

Over the next steps, add endpoints for signals, equity history, and a protected route to trigger a scan. Point your Streamlit dashboard at the API instead of reading files, so the UI and logic are separate.

**Checkpoint:** `curl http://localhost:8000/health` returns `{'status': 'ok'}`.

## 11. Step 7: Scheduled worker

The worker replaces the always-on daemon with discrete, restartable jobs. Save as `app/worker/main.py`:

```python
import time
import schedule


def refresh_data():
    print('refreshing daily bars...')


def run_scans():
    print('running scans and storing signals...')


def update_positions():
    print('checking stops, targets, time-stops, circuit breakers...')


schedule.every().day.at('21:30').do(refresh_data)
schedule.every().day.at('21:45').do(run_scans)
schedule.every(1).hours.do(update_positions)

while True:
    schedule.run_pending()
    time.sleep(30)
```

Add `schedule` to `requirements.txt`. Set the times to match your market's close and your server's timezone (set `TZ` in the compose file, or convert to UTC).

Design rules for each job:

- **Idempotent**: running it twice must not create duplicate positions or alerts.
- **Logged**: write start, end, and errors to the `audit_log` table or to stdout.
- **Safe on failure**: wrap each job in try/except, send a Telegram message on error, and never let one failed job stop the loop.

**Checkpoint:** `docker compose logs worker` shows the jobs firing on schedule.

## 12. Step 8: Research rigor (backtesting and ML)

This is the step that decides whether the system makes sense of the real world or only looks good on paper.

**Backtester requirements**

- Charge commissions and slippage on every simulated trade. A simple start is 0.05% to 0.10% per side for liquid large caps, higher for small caps.
- Execute at the next bar's open after a signal, never at the same bar's close you used to generate it (this avoids look-ahead bias).
- Use only data available on each historical date. Do not use today's index membership or today's fundamentals for past dates.
- Include a trade list and equity curve, plus Sharpe, Sortino, max drawdown, win rate, profit factor, and average holding time.

**Fixing the ML meta-labeler**

- Build labels with the triple-barrier method (profit target, stop, time limit), as in your design.
- Validate with **purged k-fold cross-validation with an embargo**, so overlapping trade windows do not leak between training and test sets. Ordinary random k-fold will overstate accuracy.
- Check **calibration**: when the model says 70%, roughly 70% of those trades should win. Plot a reliability curve.
- Compare against a simple baseline (for example, the raw technical setup with no ML filter). If the model does not beat it out-of-sample after costs, remove it.
- Treat the 65% threshold as something to tune on validation data, not a fixed truth.

**Walk-forward testing**: train on a window, test on the next period, roll forward, and combine the out-of-sample results. This is closer to live behavior than a single train/test split.

**Checkpoint:** you can produce an out-of-sample, after-costs equity curve and explain every metric on it.

## 13. Step 9: Free deployment

Option A: your own machine or a Raspberry Pi. Simplest, but it must stay on and connected.

Option B: an Oracle Cloud Always Free VM. Check Oracle's current Always Free terms and region availability first.

On the server (Ubuntu):

```
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin git ufw
sudo usermod -aG docker $USER
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable
git clone https://github.com/YOUR_USERNAME/alphaseeker.git
cd alphaseeker
cp .env.example .env   # then edit .env with real values
docker compose up -d --build
```

For HTTPS, add Caddy, which fetches and renews certificates automatically. Create a `Caddyfile`:

```
yourdomain.com {
    reverse_proxy api:8000
}
```

Then add a `caddy` service to `docker-compose.yml` with ports 80 and 443, mounting the `Caddyfile`. If you do not own a domain, use a free dynamic-DNS subdomain, or keep the service private and reach it through an SSH tunnel.

To update later:

```
cd alphaseeker && git pull && docker compose up -d --build
```

**Checkpoint:** the API answers on your domain over HTTPS, and the stack comes back by itself after a server reboot.

## 14. Step 10: Monitoring and alerts

Start simple and add more as needed.

- **Telegram alerts** for: new signals, stop or target hits, circuit breaker changes, and any worker error.
- **Heartbeat**: the worker sends one message a day ("alive, N positions, equity X"). If it stops arriving, something is wrong.
- **Backups**: a nightly `pg_dump` to a compressed file, copied off the machine (for example, to a private GitHub repo with encrypted files or to free cloud storage). Test a restore at least once.
- **Optional**: Grafana and Prometheus for charts of equity, job durations, and error counts.

**Checkpoint:** you receive a heartbeat, and you have restored a backup into a scratch database successfully.

## 15. Step 11: Security checklist

- No secrets in git. Use `.env` and rotate any token that was ever committed.
- Containers run as a non-root user.
- Database port is not published to the internet (it is not in the compose file above, so keep it that way).
- Firewall allows only SSH and web ports; use SSH keys and disable password login.
- Put authentication in front of any route that changes data (API keys or a login), especially anything that can create or close positions.
- Keep dependencies updated and pin versions in `requirements.txt`.
- Keep an `audit_log` of every automated action.

## 16. Step 12: Validation gates before any real money

Use paper trading to pass these gates, in order. Do not skip any.

1. **Backtest gate**: positive expectancy after costs across several years and both bull and bear periods, with a reasonable max drawdown.
2. **Out-of-sample gate**: walk-forward results are still positive and not dramatically worse than in-sample.
3. **Paper-trading gate**: at least 3 to 6 months of live paper trading with results consistent with the backtest.
4. **Risk gate**: circuit breakers, position limits, and the kill switch have been tested by deliberately triggering them.
5. **Reconciliation gate**: positions in your database match what you actually hold at your broker.

When you do go live, start with a very small amount you can afford to lose entirely. This guide is educational and not financial advice; you are responsible for your own trading decisions and any regulatory obligations in your country.

## 17. What to upgrade later (when you can pay)

| Trigger | Upgrade |
| --- | --- |
| Free data keeps breaking or you need intraday | Paid daily and minute data feed |
| One server is not enough | Managed database, separate worker machines |
| Multiple users | Real authentication, roles, and a React or Next.js frontend |
| Live execution | Broker API integration with a proper order management layer and reconciliation |
| Many strategies | Message queue (Redpanda or Kafka) and a feature store |

## 18. Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `db` never becomes healthy | Wrong credentials in `.env`, or an old volume. Run `docker compose down -v` (this deletes data) and start again |
| Migration SQL did not run | Init scripts only run on a fresh volume. Apply later changes with `psql` or a migration tool |
| yfinance returns empty data | Rate limiting or a changed Yahoo response. Retry with a delay, update the package, or switch provider |
| Worker runs jobs at the wrong hour | Container timezone is UTC. Set `TZ` or convert your schedule to UTC |
| Duplicate alerts or positions | Jobs are not idempotent. Add unique constraints and check before inserting |
| Backtest looks too good | Look for look-ahead bias, no costs, survivorship bias, or leakage between training and test sets |

## 19. Progress checklist

- [ ] Repository restructured and backed up
- [ ] Docker Compose stack running (db, api, worker)
- [ ] Schema created
- [ ] Data provider interface and Parquet cache working
- [ ] SQLite ledger migrated and verified
- [ ] API serving health and positions
- [ ] Scheduled worker running idempotent jobs
- [ ] Realistic backtester with costs and walk-forward testing
- [ ] ML meta-labeler validated with purged cross-validation and calibration
- [ ] Deployed with HTTPS, firewall, and non-root containers
- [ ] Telegram alerts, heartbeat, and tested backups
- [ ] All five validation gates passed
