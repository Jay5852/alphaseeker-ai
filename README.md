# ⚡ AlphaSeeker AI: Institutional Quantitative Terminal & Autonomous Trading Desk

AlphaSeeker AI is a quantitative, AI-assisted market analytics terminal and automated trade tracking system built to operate **100% free with zero paid API keys or subscriptions**.

It serves as your personal quantitative intelligence terminal:
* **Your Broker App (Zerodha, Groww, Dhan, Robinhood, Schwab, etc.):** Where you hold real funds and execute live orders.
* **AlphaSeeker AI (This System):** Your quantitative research terminal, timing engine, risk manager, and automated position manager.

---

## 🌟 Institutional Capabilities & Upgrades

### 1. 💼 Autonomous Virtual Broker & Paper Trading Ledger (Upgrade A)
* **Local SQLite Database (`data/trading_ledger.db`):** Zero server maintenance, 100% free.
* **Automated Trade State Machine:**
  * **Target 1 Achieved:** Automatically books **50% profit** and trails Stop-Loss to Entry Price (**Risk-Free Break-Even Trade**).
  * **Target 2 Achieved:** Closes remaining 50% for maximum profit.
  * **Stop-Loss Triggered:** Cuts losers cleanly strictly at predefined risk limit.
* **Official Track Record:** Logs live portfolio equity curve, cash balance, win rate %, and profit factor.

### 2. ⏱️ Target Timeline & Holding Period Predictor (Upgrade D)
* **Quantile Holding Distribution:** Predicts fastest 25%, median, and 75% holding period in trading days.
* **Calendar Date Arrival Forecast:** Computes calendar ETAs for Target 1 and Target 2, skipping weekends and market holidays for US and Indian (NSE) exchanges.
* **Automated Time-Stops:** If a stock stalls past the 75th percentile date without hitting Target 1, it triggers a **Time-Stop alert** to prevent dead money.
* **Kaplan-Meier Survival Analysis:** Estimates probability of achieving Target 1 before time-stop.

### 3. 🤖 Marcos López de Prado Quantitative ML Meta-Labeler (Upgrade B)
* Applies a secondary ML probability filter on top of technical setups.
* Predicts $P(\text{Win}) \ge 65\%$ across 7 quantitative features (RVOL, distance to 52W high, VCP contraction ratio, Bollinger Bandwidth, 200 SMA slope, macro regime).
* Discards low-probability setups before you risk real capital.

### 4. 🐋 Live Options Flow & Gamma Squeeze Detection (Upgrade C.1)
* Scrapes live options chains for free (zero API keys).
* Computes Put-to-Call Ratio (PCR), Unusual Call Ratio ($UCR \ge 3.5$), Volume-to-Open Interest ($VOI \ge 1.8$), and Market Maker **Gamma Wall** strikes.
* Flags high-conviction Gamma Squeeze setups.

### 5. 🛡️ P0 Capital Preservation Armor & Circuit Breakers
* **Drawdown Circuit Breakers:**
  * **🟡 Yellow (-5% Drawdown):** Cuts max risk sizing by 50%.
  * **⚠️ Orange (-10% Drawdown):** Halts intraday momentum trades, cuts risk by 65%.
  * **🚨 Red Lockout (-15% Drawdown):** Full desk lockout to prevent catastrophic loss.
* **Portfolio Concentration Guard:** Caps maximum concurrent open positions (6) and prevents duplicate exposure.

### 6. ⏰ Autonomous 24/7 Market Daemon (Upgrade A.2)
* Background market clock loop that wakes up automatically:
  * **Market Open (9:30 AM):** 15-Minute ORB momentum scans.
  * **Hourly / Continuous:** Monitors active positions, updates trailing stops to break-even, and pushes notifications to Telegram.
  * **Market Close (4:00 PM):** End-of-Day Minervini swing scan and daily portfolio digest.

### 7. 📊 Multi-Timeframe Confluence Scoring (Improvement G)
* Confirms every swing setup across **Monthly, Weekly, Daily, and 4-Hour** charts before approval.
* **Score: 4/4 = Maximum Confluence** (full conviction + AI score bonus), **3/4 = Strong**. Only 3/4 and 4/4 signals are traded — moderate and weak alignments are rejected.
* Monthly checks structural trend (Price > 10-Month SMA, RSI > 45), Weekly checks trend quality (40-Week SMA, MACD), Daily checks the setup, and 4-Hour checks entry timing (20-EMA pullback, no chasing).

---

## 📁 System Architecture

```
Trading/
├── config/
│   ├── settings.py              # Risk thresholds, capital sizes, Telegram tokens
│   └── universes.py             # Watchlists for US (S&P 500) and India (NSE Nifty)
├── data/
│   ├── base.py                  # Abstract MarketDataProvider interface
│   ├── provider.py              # Universal data fetcher (US & Indian stocks) with local cache
│   ├── live_scrapers.py         # Multi-source scrapers (SEC, NSE, Wikipedia, Google News)
│   └── trading_ledger.db        # SQLite database for persistent position tracking
├── ledger/
│   ├── database.py              # SQLite schema, tables (trades, snapshots, logs)
│   └── virtual_broker.py        # Order lifecycle manager & auto-break-even trailing stops
├── ml/
│   ├── features.py              # ATR, RVOL, VWAP, SMAs, Bollinger Squeeze, 52W High
│   ├── regime.py                # Market regime classifier (Bullish, Bearish, Chop)
│   ├── time_predictor.py        # Upgrade D: Quantile regression & Survival Target ETA
│   └── meta_labeler.py          # Upgrade B: López de Prado ML Meta-Label probability
├── engines/
│   ├── swing_engine.py          # Minervini Stage-2 + VCP multi-month trend finder
│   ├── confluence_scorer.py     # Improvement G: Monthly/Weekly/Daily/4H Confluence Score
│   ├── intraday_engine.py       # 15m ORB + RVOL + VWAP momentum finder
│   └── value_growth_engine.py   # Peter Lynch GARP & Buffett Undervalued Multi-Bagger
├── intelligence/
│   ├── macro_and_smart_money.py # Ray Dalio Quadrants, Form 4 Insiders, Politician STOCK Act
│   └── options_darkpool.py      # Upgrade C.1: Free options flow & Gamma Squeeze scanner
├── daemon/
│   └── market_daemon.py         # Upgrade A.2: 24/7 Background Market Clock Daemon
├── risk/
│   └── manager.py               # Position sizing, Circuit Breakers (-5%/-10%/-15%), Correlation Guard
├── alerts/
│   ├── formatter.py             # Structured Markdown trade cards with Timeline & ML scores
│   └── telegram_bot.py          # Real-time alert dispatcher to Telegram
├── dashboard/
│   └── app.py                   # 5-Tab Interactive Streamlit Terminal (Plotly, Ledger, Options)
└── main.py                      # Master CLI controller
```

---

## 🚀 Quickstart & Terminal Commands

### 1. Launch the Complete Web Terminal
```bash
python -m streamlit run dashboard/app.py
```
Open `http://localhost:8501` to access:
* **Tab 1: 🚀 Live Screener & Signal Radar** (Run scans, inspect Gamma walls, click `📥 Track in Portfolio`)
* **Tab 2: 💼 Virtual Portfolio & Active Desk** (Inspect live trailing stops, equity curves, manual trade entry)
* **Tab 3: 🧪 Strategy Backtester** (Multi-year historical simulations)
* **Tab 4: 💎 Undervalued Growth** (Peter Lynch PEG & Buffett filters)
* **Tab 5: 🏛️ Smart Money & Macro** (Dalio macro cycles, politician disclosures, Form 4)

### 2. Terminal CLI Commands

**View your portfolio equity, win rate, and active positions:**
```bash
python main.py --portfolio
```

**Check live quotes and auto-trail stops to break-even:**
```bash
python main.py --update-ledger
```

**Scan US Swing setups and automatically track the top pick:**
```bash
python main.py --market US --timeframe swing --auto-track
```

**Scan Indian Market (NSE) for Multi-Month Swing Trades:**
```bash
python main.py --market INDIA --timeframe swing
```

**Launch the Autonomous 24/7 Market Daemon:**
```bash
python main.py --daemon
```

---

## 📱 Telegram Alerts Setup (100% Free)

1. Open Telegram and message `@BotFather` to create a bot. Copy your **API Token**.
2. Message `@userinfobot` to get your numeric **Chat ID**.
3. Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"
```
The system will now push real-time trade signals with Target ETAs, ML win probabilities, and trailing stop triggers directly to your phone.
