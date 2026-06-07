"""
EchoSQL Eval Harness
====================
Runs every test case in test_cases.py through the full NL→SQL→execute pipeline
and reports five metrics per query:

  EXEC_OK     Did the SQL execute without a database error?
  ROWS_OK     Did it return at least one row?
  TABLES_OK   Do all expected table/view names appear in the SQL?
  KEYWORDS_OK Do all required SQL keywords appear? Are blocked ones absent?
  EVAL_SCORE  LLM self-assessment score (0-100, --no-llm-eval to skip)

Usage (from the backend/ directory with the venv activated):

  python -m eval.run_eval
  python -m eval.run_eval --no-llm-eval      # skip the extra LLM evaluation call
  python -m eval.run_eval --ids simple_01,agg_01   # run specific cases

Results are printed to stdout and saved to eval/results/eval_<timestamp>.json
"""

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.test_cases import TEST_CASES
from services.llm_service import explain_sql, generate_sql
from services.db_service import execute_query
from utils.sql_validator import validate_sql


RESULTS_DIR = Path(__file__).parent / "results"
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"


def _colour(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}"


def _check_sql(sql: str, case: dict) -> tuple[bool, bool, list[str]]:
    """
    Returns (tables_ok, keywords_ok, failures).
    failures is a list of human-readable failure reasons.
    """
    sql_upper = sql.upper()
    failures = []

    # expected tables
    missing_tables = [
        t for t in case.get("expected_tables", [])
        if t.lower() not in sql.lower()
    ]
    tables_ok = not missing_tables
    if missing_tables:
        failures.append(f"missing tables: {missing_tables}")

    # must_have keywords
    missing_kw = [
        kw for kw in case.get("must_have", [])
        if kw.upper() not in sql_upper
    ]
    if missing_kw:
        failures.append(f"missing keywords: {missing_kw}")

    # must_not_have keywords
    bad_kw = [
        kw for kw in case.get("must_not_have", [])
        if kw.upper() in sql_upper
    ]
    if bad_kw:
        failures.append(f"unexpected keywords: {bad_kw}")

    keywords_ok = not (missing_kw or bad_kw)
    return tables_ok, keywords_ok, failures


async def _run_case(case: dict, llm_eval: bool) -> dict:
    result = {
        "id":          case["id"],
        "nl":          case["nl"],
        "category":    case["category"],
        "sql":         None,
        "exec_ok":     False,
        "rows_ok":     False,
        "tables_ok":   False,
        "keywords_ok": False,
        "row_count":   0,
        "eval_score":  None,
        "eval_match":  None,
        "explanation": None,
        "error":       None,
        "latency_ms":  0.0,
    }
    t0 = time.perf_counter()

    # ── 1. Generate SQL ───────────────────────────────────────────────────────
    sql = await generate_sql(case["nl"])
    if not sql:
        result["error"] = "LLM returned no SQL"
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return result
    result["sql"] = sql

    # ── 2. Validate SQL ───────────────────────────────────────────────────────
    ok, reason = validate_sql(sql)
    if not ok:
        result["error"] = f"Validation: {reason}"
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return result

    # ── 3. Structural checks (tables + keywords) ──────────────────────────────
    tables_ok, keywords_ok, struct_failures = _check_sql(sql, case)
    result["tables_ok"]   = tables_ok
    result["keywords_ok"] = keywords_ok

    # ── 4. Execute against DB ─────────────────────────────────────────────────
    try:
        rows = await execute_query(sql)
        result["exec_ok"]   = True
        result["row_count"] = len(rows)
        result["rows_ok"]   = len(rows) > 0
    except Exception as e:
        result["error"] = f"DB error: {e}"
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return result

    # ── 5. LLM self-evaluation (optional) ────────────────────────────────────
    if llm_eval:
        ev = await explain_sql(case["nl"], sql)
        result["eval_score"]  = ev.get("score")
        result["eval_match"]  = ev.get("match")
        result["explanation"] = ev.get("explanation")

    result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


def _verdict(r: dict) -> str:
    if r["error"]:
        return FAIL
    if r["exec_ok"] and r["tables_ok"] and r["keywords_ok"]:
        return PASS
    return FAIL


def _print_report(results: list[dict], llm_eval: bool) -> None:
    total      = len(results)
    exec_ok    = sum(1 for r in results if r["exec_ok"])
    rows_ok    = sum(1 for r in results if r["rows_ok"])
    tables_ok  = sum(1 for r in results if r["tables_ok"])
    kw_ok      = sum(1 for r in results if r["keywords_ok"])
    passes     = sum(1 for r in results if _verdict(r) == PASS)

    scores = [r["eval_score"] for r in results if r["eval_score"] is not None]
    avg_score = round(sum(scores) / len(scores)) if scores else None

    width = 80
    print("\n" + "=" * width)
    print(_colour(f"  EchoSQL Eval Report  —  {datetime.now():%Y-%m-%d %H:%M}", _BOLD))
    print("=" * width)
    print(f"  Total cases    : {total}")
    print(f"  Overall PASS   : {_colour(str(passes), _GREEN if passes == total else _RED)}/{total}"
          f"  ({round(passes/total*100)}%)")
    print(f"  SQL executed   : {exec_ok}/{total}")
    print(f"  Returned rows  : {rows_ok}/{total}")
    print(f"  Tables correct : {tables_ok}/{total}")
    print(f"  Keywords OK    : {kw_ok}/{total}")
    if avg_score is not None:
        colour = _GREEN if avg_score >= 75 else (_YELLOW if avg_score >= 50 else _RED)
        print(f"  LLM confidence : {_colour(str(avg_score), colour)}/100  (avg)")
    print("-" * width)

    # Per-category breakdown
    categories = sorted({r["category"] for r in results})
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_pass = sum(1 for r in cat_results if _verdict(r) == PASS)
        print(f"  {cat:<12} {cat_pass}/{len(cat_results)} pass")
    print("-" * width)

    # Per-case detail
    print(f"  {'ID':<14} {'RESULT':<6} {'EXEC':<5} {'ROWS':<5} "
          f"{'TABLES':<7} {'KW':<4} {'SCORE':<6} {'MS':>7}  NL (truncated)")
    print("-" * width)
    for r in results:
        v      = _verdict(r)
        colour = _GREEN if v == PASS else _RED
        score  = str(r["eval_score"]) if r["eval_score"] is not None else "  — "
        exec_s = "✓" if r["exec_ok"]    else "✗"
        rows_s = "✓" if r["rows_ok"]    else "✗"
        tbl_s  = "✓" if r["tables_ok"]  else "✗"
        kw_s   = "✓" if r["keywords_ok"] else "✗"
        nl     = r["nl"][:45] + "…" if len(r["nl"]) > 45 else r["nl"]
        print(
            f"  {r['id']:<14} {_colour(v, colour):<15} {exec_s:<5} {rows_s:<5} "
            f"{tbl_s:<7} {kw_s:<4} {score:<6} {r['latency_ms']:>7.0f}  {nl}"
        )
        if r.get("error"):
            print(f"    {'':14} {_colour('→ ' + r['error'][:70], _RED)}")
        if r.get("explanation"):
            print(f"    {'':14} {_YELLOW}→ {r['explanation'][:80]}{_RESET}")
        if r.get("sql") and v == FAIL:
            print(f"    {'':14}   SQL: {r['sql'][:90]}")
    print("=" * width + "\n")


async def main(llm_eval: bool = True, ids: Optional[list[str]] = None) -> None:
    cases = TEST_CASES
    if ids:
        cases = [c for c in cases if c["id"] in ids]
        if not cases:
            print(f"No cases matched ids: {ids}")
            return

    print(f"\nRunning {len(cases)} eval cases"
          + (" (LLM self-eval enabled)" if llm_eval else " (LLM self-eval disabled)"))

    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i:>2}/{len(cases)}] {case['id']:<14} {case['nl'][:60]}", end="", flush=True)
        r = await _run_case(case, llm_eval)
        v = _verdict(r)
        colour = _GREEN if v == PASS else _RED
        print(f"  {_colour(v, colour)}  {r['latency_ms']:.0f}ms")
        results.append(r)

    _print_report(results, llm_eval)

    # Save results
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_at":    datetime.now(tz=timezone.utc).isoformat(),
                "llm_eval":  llm_eval,
                "total":     len(results),
                "pass":      sum(1 for r in results if _verdict(r) == PASS),
                "results":   results,
            },
            fh, indent=2, default=str,
        )
    print(f"Results saved → {out_path}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EchoSQL eval harness")
    parser.add_argument("--no-llm-eval", action="store_true",
                        help="Skip the LLM self-evaluation step (faster)")
    parser.add_argument("--ids", default="",
                        help="Comma-separated list of case IDs to run (default: all)")
    args = parser.parse_args()

    asyncio.run(main(
        llm_eval=not args.no_llm_eval,
        ids=[i.strip() for i in args.ids.split(",") if i.strip()] or None,
    ))
