from typing import Any

from python_harness.cli_soft_text import (
    EVALUATION_COMPLETED,
    PACKAGE_UNDERSTANDING_LABEL,
    QA_RESULTS_HEADER,
    SOFT_EVALUATION_HEADER,
    TOP_SUGGESTIONS_HEADER,
    UNDERSTANDABILITY_SCORE_LABEL,
)


def print_soft_evaluation_start(console: Any) -> None:
    console.print(SOFT_EVALUATION_HEADER)


def print_soft_summary(console: Any, soft_results: dict[str, Any]) -> None:
    pkg_summary = soft_results["package_summary"]
    console.print(
        f"[green]Analyzed {pkg_summary['total_files']} files with a total of "
        f"{pkg_summary['total_tokens']} tokens.[/green]"
    )
    console.print(
        f"{PACKAGE_UNDERSTANDING_LABEL}\n{pkg_summary['package_understanding']}"
    )
    console.print()
    console.print(
        f"{UNDERSTANDABILITY_SCORE_LABEL} "
        f"{soft_results['understandability_score']:.1f}/100"
    )

    qa_results = soft_results.get("qa_results", {}).get("sampled_entities", [])
    if qa_results:
        console.print()
        console.print(QA_RESULTS_HEADER)
        for qa in qa_results:
            color = "green" if qa["score"] >= 80 else "red"
            console.print(f"  - [{color}]{qa['entity']}: Score {qa['score']}[/{color}]")
            console.print(f"    [dim]Feedback: {qa['feedback']}[/dim]")

    console.print()
    console.print(EVALUATION_COMPLETED)
    console.print()


def print_final_report(console: Any, final_report: dict[str, Any]) -> None:
    verdict = str(final_report.get("verdict", "Unknown"))
    verdict_color = "bold green" if "Pass" in verdict else "bold red"
    console.print(
        f"[{verdict_color}]=== FINAL VERDICT: {verdict} ===[/{verdict_color}]"
    )
    console.print(f"[bold]Summary:[/bold] {final_report.get('summary', '')}")
    console.print()
    suggestions = final_report.get("suggestions", [])
    if not suggestions:
        return
    console.print(TOP_SUGGESTIONS_HEADER)
    for index, suggestion in enumerate(suggestions[:3], 1):
        console.print(
            f"  {index}. [bold]{suggestion.get('title', 'Suggestion')}[/bold] "
            f"(Target: [yellow]{suggestion.get('target_file', 'unknown')}[/yellow])"
        )
        console.print(f"     [dim]{suggestion.get('description', '')}[/dim]")
