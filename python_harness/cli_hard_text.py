HARD_EVALUATION_PASSED = "[bold green]Hard Evaluation Passed![/bold green]"
HARD_EVALUATION_FAILED = "[bold red]Hard Evaluation Failed![/bold red]"
RUFF_ISSUES_FOUND = "[red]Ruff issues found:[/red]"
TY_CAPTURE_MISSING = "[red]Ty failed, but no standard output was captured.[/red]"
RADON_PARSE_MISSING = "[red]Radon CC failed but no specific issues were parsed.[/red]"
CONTINUE_AFTER_HARD_FAILURE = (
    "[yellow]Continuing to soft evaluation to generate "
    "suggestions despite hard failures...[/yellow]"
)
GOVERNANCE_QC_HEADER = "[bold blue]Running Governance QC (Second Fence)...[/bold blue]"
GOVERNANCE_QC_PASSED = (
    "[bold green]Governance QC Passed! (Change is admissible)[/bold green]"
)
GOVERNANCE_QC_FAILED = "[bold red]Governance QC Failed![/bold red]"
GOVERNANCE_QC_EXPLANATION = (
    "[red]The proposed changes violate governance constraints "
    "or lack sufficient evidence.[/red]"
)
CONTINUE_AFTER_QC_FAILURE = (
    "[yellow]Continuing to soft evaluation to generate "
    "suggestions despite QC failures...[/yellow]"
)
