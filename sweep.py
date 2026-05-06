"""Parameter sweeper that rewrites a numeric trader constant and backtests it."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List


NUMERIC_ASSIGNMENT_TEMPLATE = r"^(\s*{name}(?:\s*:\s*[^=]+)?\s*=\s*)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(\s*(?:#.*)?)$"


def print_error(message: str) -> None:
    """Print a clear error message to stderr."""
    print(f"ERROR: {message}", file=sys.stderr)


def project_root() -> Path:
    """Return the project root based on the location of this script."""
    return Path(__file__).resolve().parent.parent


def traders_dir() -> Path:
    """Return the traders directory."""
    return project_root() / "traders"


def analysis_dir() -> Path:
    """Return the analysis directory."""
    return project_root() / "analysis"


def replace_parameter(source: str, param_name: str, new_value: str) -> str:
    """Replace one numeric assignment in a trader file."""
    pattern = re.compile(NUMERIC_ASSIGNMENT_TEMPLATE.format(name=re.escape(param_name)), re.MULTILINE)
    replacement, count = pattern.subn(
        lambda match: f"{match.group(1)}{new_value}{match.group(3)}",
        source,
        count=1,
    )
    if count == 0:
        raise ValueError(f"Could not find numeric assignment for parameter '{param_name}'")
    return replacement


def extract_total_pnl(output: str) -> float:
    """Pull the Total PnL value out of backtester stdout."""
    match = re.search(r"Total PnL:\s*([-+]?\d+(?:\.\d+)?)", output)
    if not match:
        raise ValueError("Backtester output did not contain a Total PnL line")
    return float(match.group(1))


def run_backtest(temp_module_name: str) -> float:
    """Execute full_backtest.py for one temporary trader module."""
    command = [sys.executable, "full_backtest.py", temp_module_name]
    completed = subprocess.run(
        command,
        cwd=analysis_dir(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Backtest failed")
    return extract_total_pnl(completed.stdout)


def main(argv: List[str]) -> int:
    """Parse CLI arguments, sweep a parameter, and report PnL per value."""
    if len(argv) < 4:
        print(
            "Usage: python sweep.py <trader_module_name> <param_name> <value1> <value2> ...",
            file=sys.stderr,
        )
        return 1

    trader_module = argv[1]
    param_name = argv[2]
    values = argv[3:]

    original_trader_path = traders_dir() / f"{trader_module}.py"
    temp_trader_path = traders_dir() / "_temp_sweep.py"

    if not original_trader_path.exists():
        print_error(f"Trader file not found: {original_trader_path}")
        return 1

    try:
        original_source = original_trader_path.read_text(encoding="utf-8")
        for value in values:
            try:
                updated_source = replace_parameter(original_source, param_name, value)
                temp_trader_path.write_text(updated_source, encoding="utf-8")
                pnl = run_backtest("_temp_sweep")
                print(f"{param_name}={value} -> PnL={pnl:.2f}")
            except Exception:
                print(f"{param_name}={value} -> PnL=ERROR")
    finally:
        if temp_trader_path.exists():
            temp_trader_path.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
