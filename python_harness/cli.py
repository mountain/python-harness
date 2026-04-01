"""
Command-line interface for python-harness.
"""

import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from python_harness.cli_hard_details import print_hard_evaluation_summary
from python_harness.cli_hard_render import (
    _mi_scorecard_color as _render_mi_scorecard_color,
)
from python_harness.cli_hard_render import (
    print_mi_scorecard,
    print_qc_summary,
)
from python_harness.cli_soft_render import (
    print_final_report,
    print_soft_evaluation_start,
    print_soft_summary,
)
from python_harness.evaluator import Evaluator
from python_harness.refine_engine import run_refine

# Try to find .env file explicitly before anything else executes
env_path = os.path.join(os.getcwd(), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # Fallback to default search

app = typer.Typer(help="Agentic harness tool for universal Python codebase evaluation.")
console = Console()


def _mi_scorecard_color(avg_mi: float) -> str:
    return _render_mi_scorecard_color(avg_mi)


@app.command()
def refine(
    path: str = typer.Argument(".", help="The path to evaluate and evolve"),
    max_retries: int = typer.Option(3, help="Maximum retries per candidate"),
    loop: bool = typer.Option(False, help="Keep refining winners across rounds"),
    max_rounds: int = typer.Option(3, help="Maximum refine rounds when looping"),
) -> None:
    """
    Refine the codebase through a fixed two-level search and optional loop.
    """
    console.print(
        f"[bold magenta]Starting refine for path:[/bold magenta] {path} "
        f"[dim](loop={loop}, max_rounds={max_rounds}, "
        f"max_retries={max_retries})[/dim]"
    )
    target_path = Path(path).resolve()

    result = run_refine(
        target_path=target_path,
        max_retries=max_retries,
        loop=loop,
        max_rounds=max_rounds,
        progress_callback=lambda message: console.print(f"[dim]{message}[/dim]"),
    )
    console.print(f"[green]winner_id:[/green] {result['winner_id']}")
    console.print(f"[cyan]rounds_completed:[/cyan] {result['rounds_completed']}")
    console.print(f"[yellow]stop_reason:[/yellow] {result['stop_reason']}")
@app.command()
def measure(path: str = typer.Argument(".", help="The path to evaluate")) -> None:
    """
    Measure the codebase against hard, soft, and governance constraints.
    Outputs a final report with scores and actionable improvement suggestions.
    """
    console.print(
        f"[bold green]Starting harness measurement for path:[/bold green] {path}"
    )
    
    evaluator = Evaluator(path)
    console.print("[bold blue]Running Hard Evaluation (ruff, mypy)...[/bold blue]")
    hard_results = evaluator.hard_evaluator.evaluate()
    print_hard_evaluation_summary(console, hard_results)
    print_mi_scorecard(console, hard_results)

    qc_results = evaluator.qc_evaluator.evaluate()
    print_qc_summary(console, qc_results)

    print_soft_evaluation_start(console)
    soft_results = evaluator.soft_evaluator.evaluate()
    print_soft_summary(console, soft_results)

    final_report = evaluator.soft_evaluator.generate_final_report(
        hard_results, qc_results, soft_results
    )
    if not final_report:
        return

    print_final_report(console, final_report)
    if "Fail" in str(final_report.get("verdict", "Unknown")):
        sys.exit(1)


if __name__ == "__main__":
    app()
