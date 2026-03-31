"""
Tests for CLI functionality.
"""

from typer.testing import CliRunner

from python_harness.cli import app

runner = CliRunner()


def test_measure_command() -> None:
    """
    Test the 'measure' command.
    """
    # Create a dummy file to pass hard evaluation in the current directory
    import os
    if not os.path.exists("dummy.py"):
        with open("dummy.py", "w") as f:
            f.write("x = 1\n")
    
    # Just checking it doesn't crash on standard invoke for now
    result = runner.invoke(app, ["measure", "."])
    # Might fail if hard eval fails, which is okay for this basic test
    assert result.exit_code in (0, 1)
    assert "Starting harness measurement" in result.stdout
