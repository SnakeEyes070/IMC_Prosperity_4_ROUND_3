# IMC Prosperity 4 – Quantitative Trading Research & Backtesting Framework

This repository contains my research workflow, strategy development process, and backtesting infrastructure used during the IMC Prosperity 4 Trading Competition.

The project focuses on developing and evaluating systematic trading strategies using quantitative analysis, statistical reasoning, and market simulation techniques. It includes custom backtesting tools, parameter tuning utilities, live log analysis workflows, and trading strategy experimentation across Round 3 market datasets.

Final competition submission strategy:

* `trader_167.py`

---

# Competition Overview

IMC Prosperity is an international quantitative trading competition where participants design algorithmic trading strategies for simulated financial markets under dynamic market conditions.

The challenge involves:

* market making
* statistical arbitrage
* signal generation
* pricing inefficiencies
* inventory management
* risk-aware execution

This repository documents my research and experimentation pipeline during Round 3 of the competition.

---

# Key Features

## Quantitative Research Workflow

* Historical market data analysis
* Product-level statistical analysis
* Strategy iteration and experimentation
* Parameter optimization and performance evaluation

## Backtesting Infrastructure

* Local event-driven backtesting framework
* Timestamp-based order simulation
* Position limit enforcement
* PnL evaluation across multiple trading days

## Strategy Development

Implemented and tested quantitative trading concepts including:

* market-making logic
* statistical arbitrage exploration
* spread-based execution
* volatility-aware parameter tuning
* Black-Scholes based voucher mispricing checks

## Performance Analysis

* cumulative PnL tracking
* live submission log analysis
* trade-level diagnostics
* execution behavior analysis

---

# Technologies Used

* Python
* Statistical Analysis
* Quantitative Finance Concepts
* Backtesting & Simulation
* CSV Market Data Processing
* Black-Scholes Pricing Logic

---

# Repository Structure

```text
analyze_capsule.py        # Market and product analysis tools
full_backtest.py          # Local backtesting engine
live_log_analyzer.py      # Submission log analytics
sweep.py                  # Parameter optimization utility
trader.py                 # Experimental trading strategy
trader_167.py             # Final Round 3 submission strategy
datamodel.py              # Prosperity-compatible trading datamodel
```

---

# Research Workflow

## 1. Market Data Analysis

Historical Round 3 datasets were analyzed to identify:

* pricing behavior
* spread characteristics
* volatility patterns
* potential inefficiencies

## 2. Strategy Experimentation

Multiple trading approaches and parameter combinations were tested using local simulations and iterative backtesting.

## 3. Backtesting & Evaluation

Strategies were evaluated using:

* cumulative PnL
* execution behavior
* consistency across trading days
* simulated market conditions

## 4. Submission Log Diagnostics

Live Prosperity submission logs were analyzed to study:

* trade execution quality
* product-wise profitability
* market edge behavior
* strategy robustness

---

# Learning Outcomes

Through this project I gained practical exposure to:

* quantitative trading workflows
* market simulation
* event-driven strategy evaluation
* parameter optimization
* systematic research methodology
* probabilistic reasoning in financial markets

The competition significantly strengthened my interest in quantitative research, algorithmic trading, and data-driven financial systems.

---

# Running the Project

## Analyze Market Data

```bash
python analyze_capsule.py
```

## Run Local Backtest

```bash
python full_backtest.py trader_167
```

## Sweep Parameters

```bash
python sweep.py trader_167 PARAM 1 2 3 4
```

## Analyze Submission Logs

```bash
python live_log_analyzer.py path_to_log.json
```

---

# Note

This repository is intended for research, experimentation, and educational purposes related to quantitative trading strategy development during the IMC Prosperity 4 competition.
