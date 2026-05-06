# IMC Prosperity 4 Pipeline

This project is a simple local workflow for iterating on IMC Prosperity 4 traders.
Everything is self-contained and uses only the Python standard library plus an optional
PowerShell helper for the Rust backtester.

## Folder Layout

- `traders/` stores your trader files such as `trader_01.py` or `trader_current.py`
- `data/` stores the Round 3 CSV files from the data capsule
- `logs/` stores downloaded live logs from Prosperity
- `analysis/` stores the tools you will run during research and backtesting

## 1. Copy Round 3 Data Into `data/`

Put these files into `data/`:

- `prices_round_3_day_0.csv`
- `prices_round_3_day_1.csv`
- `prices_round_3_day_2.csv`
- `trades_round_3_day_0.csv`
- `trades_round_3_day_1.csv`
- `trades_round_3_day_2.csv`

The local backtester requires the three `prices_*.csv` files. The trade files are useful
for the Rust backtester and future extensions.

## 2. Analyze The Capsule

From the project root:

```bash
cd analysis
python analyze_capsule.py
```

The script reads `../data/`, summarizes each product, prints a table of recommended
parameters, and runs a Black-Scholes mispricing check for detected voucher products such
as `VEV_4000`, `VEV_4500`, and similar strike symbols.

## 3. Write A Baseline Trader

Create a trader file inside `traders/`, for example:

- `traders/trader_01.py`
- `traders/trader_current.py`

The backtester imports the `Trader` class directly from that file. If your trader uses
the standard Prosperity-style `from datamodel import ...` import, the local backtester
provides a compatible in-memory datamodel automatically.

## 4. Run The Local Backtest

From `analysis/`:

```bash
python full_backtest.py trader_01
```

Example:

```bash
python full_backtest.py trader_current
```

The script groups rows by timestamp, calls `Trader.run()` once per timestamp, fills only
aggressive orders that cross the spread, applies hardcoded position limits, and prints:

- Day 0 PnL
- Day 1 PnL
- Day 2 PnL
- Total PnL
- Execution time

## 5. Sweep Parameters

If your trader has a numeric parameter such as:

```python
VEV_BUY_TOL = 4
```

you can test several values quickly:

```bash
python sweep.py trader_current VEV_BUY_TOL 2 3 4 5 6
```

The sweeper creates a temporary trader file, runs the full backtest for each value,
prints the resulting PnL, and deletes the temporary file at the end.

## 6. Analyze A Live Submission Log

After uploading a trader in Prosperity, download the resulting log JSON and place it
anywhere convenient, for example in `logs/`.

Then run:

```bash
python live_log_analyzer.py ..\logs\my_submission.json
```

The script will create:

- `my_submission_trades.csv`
- `my_submission_cumulative_pnl.csv`

It also prints a quick summary showing total PnL, trade counts per product, and the best
and worst submission-side trades using immediate mid-price edge when available.

## 7. Optional Rust Backtester Setup

If you want to compare against the Rust backtester:

```powershell
.\setup_rust_backtester.ps1
```

By default it looks for:

- `..\traders\trader_current.py`

You can point it to another trader file:

```powershell
.\setup_rust_backtester.ps1 -TraderPath ..\traders\trader_01.py
```

The script will:

- check for Rust and cargo
- switch to the GNU toolchain if the MSVC linker is missing
- clone `prosperity_rust_backtester` if needed
- copy your Round 3 CSVs into the expected dataset folder
- copy your trader to `traders/latest_trader.py`
- build and run the Rust backtester

## Typical Beginner Workflow

1. Copy the six Round 3 CSV files into `data/`.
2. Run `python analyze_capsule.py` from `analysis/`.
3. Create `traders/trader_current.py`.
4. Run `python full_backtest.py trader_current`.
5. Tune a parameter with `python sweep.py trader_current PARAM 1 2 3`.
6. Upload your trader to Prosperity.
7. Download the log and run `python live_log_analyzer.py path_to_log.json`.
8. Optionally compare with the Rust backtester.
