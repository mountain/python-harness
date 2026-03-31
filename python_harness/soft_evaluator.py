"""
Core module for agentic soft evaluation and code understanding.
"""

import ast
import contextlib
import json
import os
import random
from pathlib import Path
from typing import Any

import tiktoken
from openai import OpenAI
from pydantic import BaseModel
from rich.console import Console

console = Console()

class FileSummary(BaseModel):
    summary: str
    key_entities: list[str]
    complexity_score: int

class SoftEvaluator:
    """
    Evaluator for agentic code understanding and reasoning.
    """

    def __init__(self, target_path: str):
        self.target_path = Path(target_path).resolve()
        # Initialize token counter (using cl100k_base for gpt-4/claude-3)
        self.encoding: Any = None
        with contextlib.suppress(Exception):
            self.encoding = tiktoken.get_encoding("cl100k_base")

        # Initialize OpenAI client only if API key is present
        self.client = None
        api_key = os.environ.get("LLM_API_KEY")
        base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.model_name = os.environ.get("LLM_MODEL_NAME", "deepseek-reasoner")
        self.mini_model_name = os.environ.get("LLM_MINI_MODEL_NAME", "deepseek-chat")

        if api_key:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            console.print(
                "[yellow]Warning: LLM_API_KEY not set. "
                "Agent will run in mock mode.[/yellow]"
            )
            
        # Store extracted AST entities for sampling
        self.extracted_entities: list[dict[str, Any]] = []

    def _get_python_files(self) -> list[Path]:
        """
        Recursively find all Python files in the target directory,
        excluding hidden dirs and .venv.
        """
        python_files = []
        for root, dirs, files in os.walk(self.target_path):
            # Exclude hidden directories and virtual environments
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and d not in (
                    "__pycache__",
                    "venv",
                    "env",
                    "vendors",
                )
            ]
            for file in files:
                if file.endswith(".py"):
                    python_files.append(Path(root) / file)
        return python_files

    def calculate_token_complexity(self, file_path: Path) -> int:
        """
        Calculate the token count for a given file as a proxy
        for cognitive complexity.
        """
        if not self.encoding:
            return 0

        try:
            content = file_path.read_text(encoding="utf-8")
            return len(self.encoding.encode(content))
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not read {file_path} for token counting: "
                f"{e}[/yellow]"
            )
            return 0

    def _extract_ast_entities(self, file_path: Path, content: str) -> None:
        """
        Parse the AST of a file to extract:
        1. Classes and functions for later QA sampling.
        2. Fan-out (number of imported external modules) to measure coupling.
        """
        try:
            tree = ast.parse(content)
            
            # Calculate Fan-out (number of unique imported top-level modules)
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.add(node.module.split('.')[0])
            
            fan_out = len(imported_modules)
            
            # Extract classes and functions
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    try:
                        source_segment = ast.get_source_segment(content, node)
                        if source_segment:
                            if isinstance(node, ast.ClassDef):
                                entity_type = "Class"
                            else:
                                entity_type = "Function"
                            self.extracted_entities.append(
                                {
                                    "file": file_path.name,
                                    "type": entity_type,
                                    "name": node.name,
                                    "code": source_segment,
                                    "fan_out": fan_out,  # Context
                                }
                            )
                    except Exception:
                        pass
        except SyntaxError:
            pass  # Skip files with syntax errors

    def summarize_file(self, file_path: Path) -> dict[str, Any]:
        """
        Use LLM agent to summarize a single file's logic and structure.
        """
        tokens = self.calculate_token_complexity(file_path)

        try:
            content = file_path.read_text(encoding="utf-8")
            self._extract_ast_entities(file_path, content)
        except Exception:
            content = ""

        simulated_summary = f"File {file_path.name} contains {tokens} tokens."
        key_entities: list[str] = []

        # Only call LLM if file is not empty and not too large (e.g. > 100k tokens)
        if self.client and content and 0 < tokens < 100000:
            try:
                sys_prompt = (
                    "You are a senior Python architect. Analyze the provided Python "
                    "file and provide a concise summary of its purpose, a list of "
                    "its key entities (classes/functions/globals), and an estimated "
                    "cognitive complexity score (1-10).\n"
                    "Output MUST be in valid JSON matching this schema: "
                    '{"summary": "str", "key_entities": ["str"], "complexity_score": 1}'
                )
                completion = self.client.chat.completions.create(
                    model=self.mini_model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": sys_prompt,
                        },
                        {
                            "role": "user",
                            "content": (
                                f"File name: {file_path.name}\n\nContent:\n"
                                f"```python\n{content}\n```"
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                )

                content_str = completion.choices[0].message.content
                if content_str:
                    result = json.loads(content_str)
                    simulated_summary = result.get("summary", simulated_summary)
                    key_entities = result.get("key_entities", key_entities)
            except Exception as e:
                console.print(
                    f"[yellow]  Agent failed to read {file_path.name}: {e}[/yellow]"
                )

        try:
            rel_path = str(file_path.relative_to(self.target_path))
        except ValueError:
            rel_path = str(file_path)

        return {
            "file": rel_path,
            "tokens": tokens,
            "summary": simulated_summary,
            "key_entities": key_entities,
        }

    def summarize_package(self) -> dict[str, Any]:
        """
        Aggregate file summaries into a package-level understanding.
        """
        files = self._get_python_files()
        file_summaries = []
        total_tokens = 0

        console.print(
            f"[cyan]Agent is analyzing {len(files)} Python files "
            f"for cognitive load and architecture...[/cyan]"
        )

        for file in files:
            summary_data = self.summarize_file(file)
            file_summaries.append(summary_data)
            total_tokens += summary_data["tokens"]

        # Synthesize package architecture
        package_understanding = (
            f"The package contains {len(files)} files with a total cognitive load "
            f"of {total_tokens} tokens."
        )
        
        if self.client and file_summaries:
            try:
                console.print(
                    "[cyan]Agent is synthesizing global package architecture...[/cyan]"
                )
                manifest_lines = [
                    f"- {s['file']}: {s['summary']} "
                    f"(Entities: {', '.join(s['key_entities'])})"
                    for s in file_summaries
                ]
                manifest = "\n".join(manifest_lines)

                sys_prompt = (
                    "You are a senior software architect. Based on the following "
                    "summaries of individual files in a Python package, write a "
                    "coherent, high-level explanation of how this entire package "
                    "works and what its primary responsibilities are. Be concise "
                    "but comprehensive."
                )

                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": sys_prompt,
                        },
                        {
                            "role": "user",
                            "content": f"Package files and summaries:\n{manifest}",
                        },
                    ],
                )

                package_understanding = (
                    completion.choices[0].message.content or package_understanding
                )
            except Exception as e:
                console.print(
                    f"[yellow]Agent failed to synthesize package: {e}[/yellow]"
                )

        return {
            "total_files": len(files),
            "total_tokens": total_tokens,
            "file_level_summaries": file_summaries,
            "package_understanding": package_understanding,
        }

    def run_sampling_qa(self) -> dict[str, Any]:
        """
        Randomly sample modules/variables and ask the Agent questions
        to measure understandability.
        """
        if not self.extracted_entities:
            return {
                "qa_score": 100.0,
                "sampled_entities": [],
                "note": "No entities found for sampling.",
            }

        # Randomly sample up to 3 entities
        sample_size = min(3, len(self.extracted_entities))
        sampled = random.sample(self.extracted_entities, sample_size)

        console.print(
            f"\n[cyan]Agent is running Blind QA on {sample_size} "
            f"sampled entities...[/cyan]"
        )

        qa_results = []
        total_score = 0.0

        for entity in sampled:
            entity_name = entity["name"]
            entity_type = entity["type"]
            entity_code = entity["code"]
            fan_out = entity.get("fan_out", 0)

            if not self.client:
                # Mock evaluation
                score = 100.0
                feedback = "Mock evaluation: Code is perfectly readable."
            else:
                try:
                    sys_prompt = (
                        "You are an expert Code Reviewer and Software Architect. "
                        "You will be given a snippet of Python code (a class or "
                        "function) along with its module's Fan-out metric (number "
                        "of external dependencies). Your task is to evaluate its "
                        "readability and structural cohesion.\n"
                        "Output MUST be in valid JSON matching this schema: "
                        '{"explanation": "str", "readability_score": 1, '
                        '"feedback": "str"}\n'
                        "- `explanation`: Briefly explain what this code does.\n"
                        "- `readability_score`: A score from 0 to 100.\n"
                        "- `feedback`: What makes it easy/hard to understand? "
                        "Does a high Fan-out indicate bad cohesion here?"
                    )

                    user_content = (
                        f"Module Fan-out (Dependencies): {fan_out}\n\n"
                        f"Code Snippet:\n```python\n{entity_code}\n```"
                    )

                    completion = self.client.chat.completions.create(
                        model=self.mini_model_name,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        response_format={"type": "json_object"},
                    )

                    content_str = completion.choices[0].message.content
                    if content_str:
                        result = json.loads(content_str)
                        score = float(result.get("readability_score", 100))
                        feedback = result.get("feedback", "")
                    else:
                        score = 80.0
                        feedback = "Failed to parse Agent response."
                except Exception as e:
                    score = 0.0
                    feedback = f"Error during Agent evaluation: {e}"

            total_score += score
            qa_results.append(
                {
                    "entity": f"{entity_type} {entity_name} (from {entity['file']})",
                    "score": score,
                    "feedback": feedback,
                }
            )

        final_average_score = total_score / sample_size if sample_size > 0 else 100.0

        return {
            "qa_score": final_average_score,
            "sampled_entities": qa_results,
            "note": "Sampling QA completed.",
        }

    def generate_final_report(
        self, hard_results: dict[str, Any], soft_results: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Synthesize all evaluation results into a final verdict and exactly 
        3 actionable suggestions.
        """
        if not self.client:
            return {
                "verdict": "Pass (Mock)",
                "summary": "Mock evaluation completed without LLM.",
                "suggestions": [
                    {
                        "title": "Mock Suggestion 1",
                        "description": "Add more docstrings.",
                        "target_file": "all"
                    },
                    {
                        "title": "Mock Suggestion 2",
                        "description": "Refactor large functions.",
                        "target_file": "all"
                    },
                    {
                        "title": "Mock Suggestion 3",
                        "description": "Improve test coverage.",
                        "target_file": "tests/"
                    }
                ]
            }

        try:
            # Extract key metrics for the prompt
            cc_issues = hard_results.get("radon_cc", {}).get("issues", [])
            mi_scores = hard_results.get("radon_mi", {}).get("mi_scores", {})
            avg_mi = sum(mi_scores.values()) / len(mi_scores) if mi_scores else 100.0
            
            qa_score = soft_results.get("understandability_score", 100.0)
            qa_entities = soft_results.get("qa_results", {}).get("sampled_entities", [])
            
            sys_prompt = (
                "You are an elite Python Codebase Evaluator. You have just analyzed "
                "a repository. Your task is to provide a final judgment and EXACTLY "
                "3 concrete, actionable improvement suggestions. These suggestions "
                "MUST NOT change the external functionality (they are refactoring/"
                "quality improvements).\n\n"
                "Output MUST be in valid JSON matching this schema:\n"
                "{\n"
                '  "verdict": "Pass" or "Fail",\n'
                '  "summary": "One paragraph summary of codebase health",\n'
                '  "suggestions": [\n'
                '    {"title": "str", "description": "str", "target_file": "str"}\n'
                "  ]\n"
                "}\n"
                "Rule for Verdict: Pass if Average Maintainability > 50 and "
                "QA Score > 75 and no Critical CC issues (>15). Otherwise Fail."
            )

            user_content = (
                f"Metrics:\n"
                f"- Average Maintainability Index (MI): {avg_mi:.1f}/100\n"
                f"- Number of functions with Cyclomatic Complexity > 15: "
                f"{len(cc_issues)}\n"
                f"- Agent QA Readability Score: {qa_score:.1f}/100\n\n"
                f"QA Feedback Snippets:\n"
                + "\n".join(
                    [f"  * {q['entity']}: {q['feedback']}" for q in qa_entities]
                )
            )

            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )

            content_str = completion.choices[0].message.content
            if content_str:
                parsed_json = json.loads(content_str)
                if isinstance(parsed_json, dict):
                    return parsed_json
                else:
                    raise ValueError("JSON response is not a dictionary.")
            else:
                raise ValueError("Empty response from Agent.")
        except Exception as e:
            console.print(f"[yellow]Failed to generate final report: {e}[/yellow]")
            return {
                "verdict": "Error",
                "summary": f"Failed to synthesize report: {e}",
                "suggestions": []
            }
    def evaluate(self) -> dict[str, Any]:
        """
        Execute soft evaluation workflows including summarization and Q&A.
        """
        package_summary = self.summarize_package()
        qa_results = self.run_sampling_qa()

        # Calculate a mock understandability score based on token density
        # (just an example heuristic)
        # In reality, this will be based on the QA results and LLM judge
        understandability_score = qa_results["qa_score"]

        return {
            "status": "success",
            "understandability_score": understandability_score,
            "package_summary": package_summary,
            "qa_results": qa_results,
        }
