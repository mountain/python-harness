"""
Core module for agentic soft evaluation and code understanding.
"""

import contextlib
import random
from pathlib import Path
from typing import Any, cast

import tiktoken
from rich.console import Console

from python_harness.llm_client import build_llm_client, load_llm_settings
from python_harness.python_file_inventory import collect_python_files
from python_harness.soft_eval_defaults import (
    MOCK_EVALUATION_FEEDBACK,
    MOCK_EVALUATION_SCORE,
    QA_SAMPLE_SIZE,
)
from python_harness.soft_eval_file_summary import (
    build_default_file_summary,
    build_file_summary_cache_key,
    build_file_summary_messages,
    build_relative_file_path,
    cache_file_summary,
    get_cached_file_summary,
    parse_file_summary_response,
    should_call_file_summary_llm,
)
from python_harness.soft_eval_file_summary import (
    clear_file_summary_cache as clear_soft_eval_file_summary_cache,
)
from python_harness.soft_eval_package import (
    build_package_manifest,
    build_package_synthesis_messages,
    build_package_understanding,
)
from python_harness.soft_eval_report import (
    build_final_report_messages,
    build_mock_final_report,
    build_mock_summary,
    collect_hard_errors,
    determine_verdict,
    extract_metrics,
    parse_final_report_response,
)
from python_harness.soft_eval_sampling import (
    build_sampled_entity_result,
    build_sampling_qa_messages,
    extract_ast_entities,
    parse_sampling_qa_response,
)

console = Console()


def clear_file_summary_cache() -> None:
    clear_soft_eval_file_summary_cache()


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

        settings = load_llm_settings()
        self.client = None
        self.model_name = settings.model_name
        self.mini_model_name = settings.mini_model_name
        self.request_timeout_seconds = settings.request_timeout_seconds

        client = build_llm_client(settings)
        if client is not None:
            self.client = client
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
        return collect_python_files(self.target_path)

    def _read_file_text(self, file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8")

    def _count_tokens(self, content: str) -> int:
        if not self.encoding:
            return 0
        return len(self.encoding.encode(content))

    def _relative_file_path(self, file_path: Path) -> str:
        return build_relative_file_path(file_path, self.target_path)

    def _build_default_file_summary(
        self,
        file_path: Path,
        tokens: int,
    ) -> dict[str, Any]:
        return build_default_file_summary(file_path, self.target_path, tokens)

    def _should_call_file_summary_llm(self, content: str, tokens: int) -> bool:
        return should_call_file_summary_llm(self.client, content, tokens)

    def _build_file_summary_messages(
        self,
        file_path: Path,
        content: str,
    ) -> list[dict[str, str]]:
        return build_file_summary_messages(file_path, content)

    def _parse_file_summary_response(
        self,
        raw_content: str,
        fallback_summary: dict[str, Any],
    ) -> dict[str, Any]:
        return parse_file_summary_response(raw_content, fallback_summary)

    def _file_summary_cache_key(self, content: str) -> tuple[str, str]:
        return build_file_summary_cache_key(self.mini_model_name, content)

    def _summarize_file_with_llm(
        self,
        file_path: Path,
        content: str,
        fallback_summary: dict[str, Any],
    ) -> dict[str, Any]:
        cache_key = self._file_summary_cache_key(content)
        cached_summary = get_cached_file_summary(cache_key, fallback_summary)
        if cached_summary is not None:
            return cached_summary
        client = cast(Any, self.client)
        completion = self._create_completion(
            client,
            model=self.mini_model_name,
            messages=self._build_file_summary_messages(file_path, content),
            response_format={"type": "json_object"},
        )
        content_str = completion.choices[0].message.content
        if not content_str:
            return fallback_summary
        summary = self._parse_file_summary_response(content_str, fallback_summary)
        cache_file_summary(cache_key, summary)
        return summary

    def _extract_metrics(
        self,
        hard_results: dict[str, Any],
        qc_results: dict[str, Any],
        soft_results: dict[str, Any],
    ) -> dict[str, Any]:
        return extract_metrics(hard_results, qc_results, soft_results)

    def _collect_hard_errors(self, hard_results: dict[str, Any]) -> list[str]:
        return collect_hard_errors(hard_results)

    def _determine_verdict(self, metrics: dict[str, Any], mock: bool = False) -> str:
        return determine_verdict(metrics, mock=mock)

    def _build_mock_summary(
        self,
        metrics: dict[str, Any],
        hard_results: dict[str, Any],
    ) -> str:
        return build_mock_summary(metrics, hard_results)

    def _create_completion(self, client: Any, **kwargs: Any) -> Any:
        return client.chat.completions.create(
            timeout=self.request_timeout_seconds,
            **kwargs,
        )

    def _build_mock_final_report(
        self,
        hard_results: dict[str, Any],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        return build_mock_final_report(hard_results, metrics)

    def _build_final_report_messages(
        self,
        metrics: dict[str, Any],
    ) -> list[dict[str, str]]:
        return build_final_report_messages(metrics)

    def _parse_final_report_response(self, raw_content: str) -> dict[str, Any]:
        return parse_final_report_response(raw_content)

    def _summarize_package_files(
        self,
        files: list[Path],
    ) -> tuple[list[dict[str, Any]], int]:
        file_summaries: list[dict[str, Any]] = []
        total_tokens = 0

        for index, file_path in enumerate(files, start=1):
            console.print(
                f"[dim]File summary {index}/{len(files)} started: "
                f"{file_path.name}[/dim]"
            )
            summary_data = self.summarize_file(file_path)
            file_summaries.append(summary_data)
            total_tokens += summary_data["tokens"]
            console.print(
                f"[dim]File summary {index}/{len(files)} completed: "
                f"{file_path.name}[/dim]"
            )

        return file_summaries, total_tokens

    def _synthesize_package_understanding(
        self,
        file_summaries: list[dict[str, Any]],
        total_files: int,
        total_tokens: int,
    ) -> str:
        package_understanding = build_package_understanding(total_files, total_tokens)
        if not self.client or not file_summaries:
            return package_understanding

        try:
            console.print(
                "[cyan]Agent is synthesizing global package architecture...[/cyan]"
            )
            manifest = build_package_manifest(file_summaries)
            client = cast(Any, self.client)
            completion = self._create_completion(
                client,
                model=self.model_name,
                messages=build_package_synthesis_messages(manifest),
            )
            return completion.choices[0].message.content or package_understanding
        except Exception as e:
            console.print(f"[yellow]Agent failed to synthesize package: {e}[/yellow]")
            return package_understanding

    def _sample_entities_for_qa(self) -> list[dict[str, Any]]:
        sample_size = min(QA_SAMPLE_SIZE, len(self.extracted_entities))
        return random.sample(self.extracted_entities, sample_size)

    def _evaluate_sampled_entity(
        self,
        entity: dict[str, Any],
    ) -> tuple[float, str]:
        entity_code = entity["code"]
        fan_out = entity.get("fan_out", 0)

        if not self.client:
            return MOCK_EVALUATION_SCORE, MOCK_EVALUATION_FEEDBACK

        try:
            client = cast(Any, self.client)
            completion = self._create_completion(
                client,
                model=self.mini_model_name,
                messages=build_sampling_qa_messages(entity_code, fan_out),
                response_format={"type": "json_object"},
            )
            content_str = completion.choices[0].message.content
            if not content_str:
                return 80.0, "Failed to parse Agent response."
            result = parse_sampling_qa_response(content_str)
            return result["score"], result["feedback"]
        except Exception as e:
            return 0.0, f"Error during Agent evaluation: {e}"

    def _request_final_report(self, metrics: dict[str, Any]) -> dict[str, Any]:
        client = cast(Any, self.client)
        completion = self._create_completion(
            client,
            model=self.mini_model_name,
            messages=self._build_final_report_messages(metrics),
            response_format={"type": "json_object"},
        )
        content_str = completion.choices[0].message.content
        if content_str:
            return self._parse_final_report_response(content_str)
        raise ValueError("Empty response from Agent.")

    def calculate_token_complexity(self, file_path: Path) -> int:
        """
        Calculate the token count for a given file as a proxy
        for cognitive complexity.
        """
        if not self.encoding:
            return 0

        try:
            content = self._read_file_text(file_path)
            return self._count_tokens(content)
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
        self.extracted_entities.extend(extract_ast_entities(file_path, content))

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

        fallback_summary = self._build_default_file_summary(file_path, tokens)
        if not self._should_call_file_summary_llm(content, tokens):
            return fallback_summary

        try:
            return self._summarize_file_with_llm(file_path, content, fallback_summary)
        except Exception as e:
            console.print(
                f"[yellow]  Agent failed to read {file_path.name}: {e}[/yellow]"
            )
            return fallback_summary

    def summarize_package(self) -> dict[str, Any]:
        """
        Aggregate file summaries into a package-level understanding.
        """
        files = self._get_python_files()

        console.print(
            f"[cyan]Agent is analyzing {len(files)} Python files "
            f"for cognitive load and architecture...[/cyan]"
        )
        file_summaries, total_tokens = self._summarize_package_files(files)
        package_understanding = self._synthesize_package_understanding(
            file_summaries=file_summaries,
            total_files=len(files),
            total_tokens=total_tokens,
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

        sampled = self._sample_entities_for_qa()
        sample_size = len(sampled)

        console.print(
            f"\n[cyan]Agent is running Blind QA on {sample_size} "
            f"sampled entities...[/cyan]"
        )

        qa_results = []
        total_score = 0.0

        for index, entity in enumerate(sampled, start=1):
            entity_name = entity["name"]
            entity_type = entity["type"]
            console.print(
                f"[dim]Blind QA item {index}/{sample_size} started: "
                f"{entity_type} {entity_name}[/dim]"
            )
            score, feedback = self._evaluate_sampled_entity(entity)
            total_score += score
            console.print(
                f"[dim]Blind QA item {index}/{sample_size} completed: "
                f"{entity_type} {entity_name} -> {score:.1f}[/dim]"
            )
            qa_results.append(build_sampled_entity_result(entity, score, feedback))

        final_average_score = total_score / sample_size if sample_size > 0 else 100.0

        return {
            "qa_score": final_average_score,
            "sampled_entities": qa_results,
            "note": "Sampling QA completed.",
        }

    def generate_final_report(
        self,
        hard_results: dict[str, Any],
        qc_results: dict[str, Any],
        soft_results: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Synthesize all evaluation results into a final verdict and exactly
        3 actionable suggestions.
        """
        metrics = self._extract_metrics(hard_results, qc_results, soft_results)
        if not self.client:
            return self._build_mock_final_report(hard_results, metrics)

        try:
            console.print("[dim]Final report synthesis started[/dim]")
            report = self._request_final_report(metrics)
            console.print("[dim]Final report synthesis completed[/dim]")
            return report
        except Exception as e:
            console.print(f"[yellow]Failed to generate final report: {e}[/yellow]")
            return {
                "verdict": "Error",
                "summary": f"Failed to synthesize report: {e}",
                "suggestions": [],
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
