"""
Command-line interface for python-harness.
"""

import os
import sys

import typer
from dotenv import load_dotenv
from rich.console import Console

from python_harness.evaluator import Evaluator

# Try to find .env file explicitly before anything else executes
env_path = os.path.join(os.getcwd(), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # Fallback to default search

app = typer.Typer(help="Agentic harness tool for universal Python codebase evaluation.")
console = Console()


@app.command()
def refine(
    path: str = typer.Argument(".", help="The path to evaluate and evolve"),
    steps: int = typer.Option(1, help="Number of evolution steps to perform"),
    max_retries: int = typer.Option(3, help="Maximum retries per variant if tests fail")
) -> None:
    """
    Refine the codebase through an agentic Edit-Test-Improve loop.
    Generates variants based on suggestions, tests them, and picks the best.
    """
    console.print(
        f"[bold magenta]Starting evolution loop for path:[/bold magenta] {path} "
        f"[dim](steps={steps}, max_retries={max_retries})[/dim]"
    )
    
    # 1. First, run a baseline evaluation to get suggestions
    evaluator = Evaluator(path)
    console.print("[cyan]Running baseline evaluation...[/cyan]")
    hard_results = evaluator.hard_evaluator.evaluate()
    soft_results = evaluator.soft_evaluator.evaluate()
    baseline_report = evaluator.soft_evaluator.generate_final_report(
        hard_results, soft_results
    )
    
    suggestions = baseline_report.get("suggestions", [])
    if not suggestions:
        console.print("[yellow]No suggestions found to evolve. Exiting.[/yellow]")
        return
        
    console.print(
        f"[green]Found {len(suggestions)} suggestions. "
        f"Starting evolution branches...[/green]"
    )
    
    # TODO: Implement the Git branching and Agent modification logic here.
    # The loop will be:
    # for step in range(steps):
    #   for suggestion in suggestions:
    #     checkout new branch variant-X
    #     for retry in range(max_retries):
    #       ask LLM to apply suggestion to code
    #       run pytest
    #       if pytest passes:
    #         run harness . to get new score
    #         break
    #       else:
    #         feed error back to LLM for retry
    #   compare all variants and checkout the best one
    
    console.print(
        "[yellow]Evolution engine skeleton ready. "
        "Actual git mutation logic pending.[/yellow]"
    )
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
    
    # 1. Hard Evaluation Gate (First Fence)
    console.print("[bold blue]Running Hard Evaluation (ruff, mypy)...[/bold blue]")
    hard_results = evaluator.hard_evaluator.evaluate()
    
    if not hard_results["all_passed"]:
        console.print("[bold red]Hard Evaluation Failed! Exiting.[/bold red]")
        if hard_results["ruff"]["status"] != "success":
            console.print("[red]Ruff issues found:[/red]")
            # Assuming ruff output is JSON as configured in HardEvaluator
            for issue in hard_results["ruff"].get("issues", []):
                file = issue.get("filename", "unknown")
                line = issue.get("location", {}).get("row", "?")
                msg = issue.get("message", "unknown issue")
                console.print(f"  - {file}:{line} {msg}")
        if hard_results["mypy"]["status"] != "success":
            output = hard_results["mypy"].get("output", "")
            console.print(f"[red]Mypy issues found:[/red]\n{output}")
        if hard_results["ty"]["status"] not in ("success", "warning"):
            output = hard_results["ty"].get("output", "")
            # ty might print to stderr instead of stdout, or it might be missing
            error_msg = hard_results["ty"].get("error_message", "")
            if output:
                console.print(f"[red]Ty issues found:[/red]\n{output}")
            elif error_msg:
                console.print(f"[red]Ty error:[/red]\n{error_msg}")
            else:
                console.print(
                    "[red]Ty failed, but no standard output was captured.[/red]"
                )
        elif hard_results["ty"]["status"] == "warning":
            msg = hard_results["ty"].get("error_message", "ty not found")
            console.print(f"[yellow]Ty warning:[/yellow] {msg}")
        if hard_results["radon_cc"]["status"] != "success":
            issues = hard_results["radon_cc"].get("issues", [])
            console.print(
                f"[red]Cyclomatic Complexity too high "
                f"({len(issues)} functions > 15):[/red]"
            )
            for issue in issues:
                console.print(
                    f"  - {issue['file']}: {issue['type']} '{issue['name']}' "
                    f"has CC {issue['complexity']}"
                )
            
            # If radon failed for another reason 
            # (e.g. radon not installed or syntax error)
            if not issues and hard_results["radon_cc"].get("error_message"):
                err_msg = hard_results['radon_cc'].get('error_message')
                console.print(f"[red]Radon CC Error:[/red] {err_msg}")
            elif not issues:
                console.print(
                    "[red]Radon CC failed but no specific issues were parsed.[/red]"
                )
        elif hard_results["radon_cc"]["status"] == "warning":
            console.print(f"[yellow]Radon CC warning:[/yellow] {hard_results['radon_cc'].get('error_message')}")
        sys.exit(1)
        
    console.print("[bold green]Hard Evaluation Passed![/bold green]")
    
    # Print Maintainability Index scorecard
    mi_scores = hard_results.get("radon_mi", {}).get("mi_scores", {})
    if mi_scores:
        avg_mi = sum(mi_scores.values()) / len(mi_scores)
        color = "green" if avg_mi > 50 else "yellow" if avg_mi > 20 else "red"
        console.print(
            f"[{color}]Average Maintainability Index: {avg_mi:.1f}/100[/{color}]"
        )

    # 2. Governance/QC Evaluation (Second Fence)
    console.print("\n[bold blue]Running Governance QC (Second Fence)...[/bold blue]")
    qc_results = evaluator.qc_evaluator.evaluate()
    
    if not qc_results["all_passed"]:
        console.print("[bold red]Governance QC Failed! Exiting.[/bold red]")
        console.print(
            "[red]The proposed changes violate governance constraints "
            "or lack sufficient evidence.[/red]"
        )
        for failure in qc_results["failures"]:
            console.print(f"[red]- {failure}[/red]")
        sys.exit(1)
        
    console.print(
        "[bold green]Governance QC Passed! (Change is admissible)[/bold green]"
    )

    # 3. Soft Evaluation/Readability (Third Fence)
    console.print(
        "[bold blue]Running Soft Evaluation "
        "(Readability & Understandability)...[/bold blue]"
    )
    soft_results = evaluator.soft_evaluator.evaluate()

    pkg_summary = soft_results["package_summary"]
    console.print(
        f"[green]Analyzed {pkg_summary['total_files']} files with a total of "
        f"{pkg_summary['total_tokens']} tokens.[/green]"
    )
    console.print(
        f"[magenta]Agent's Understanding of the Package:[/magenta]\n"
        f"{pkg_summary['package_understanding']}"
    )
    
    console.print(
        f"\n[cyan]Overall Understandability Score:[/cyan] "
        f"{soft_results['understandability_score']:.1f}/100"
    )
    
    qa_results = soft_results.get("qa_results", {}).get("sampled_entities", [])
    if qa_results:
        console.print("\n[bold yellow]Blind QA Sampling Results:[/bold yellow]")
        for qa in qa_results:
            color = "green" if qa['score'] >= 80 else "red"
            console.print(f"  - [{color}]{qa['entity']}: Score {qa['score']}[/{color}]")
            console.print(f"    [dim]Feedback: {qa['feedback']}[/dim]")

    console.print("\n[yellow]Evaluation completed. Generating report...[/yellow]\n")
    
    # Generate Final Report
    final_report = evaluator.soft_evaluator.generate_final_report(
        hard_results, soft_results
    )
    
    if final_report:
        verdict = final_report.get("verdict", "Unknown")
        verdict_color = "bold green" if "Pass" in verdict else "bold red"
        
        console.print(
            f"[{verdict_color}]=== FINAL VERDICT: {verdict} ===[/{verdict_color}]"
        )
        console.print(f"[bold]Summary:[/bold] {final_report.get('summary', '')}\n")
        
        suggestions = final_report.get("suggestions", [])
        if suggestions:
            console.print("[bold cyan]Top 3 Improvement Suggestions:[/bold cyan]")
            for i, sug in enumerate(suggestions, 1):
                console.print(
                    f"  {i}. [bold]{sug.get('title', 'Suggestion')}[/bold] "
                    f"(Target: [yellow]{sug.get('target_file', 'unknown')}[/yellow])"
                )
                console.print(f"     [dim]{sug.get('description', '')}[/dim]")
        
        if "Fail" in verdict:
            sys.exit(1)


if __name__ == "__main__":
    app()
