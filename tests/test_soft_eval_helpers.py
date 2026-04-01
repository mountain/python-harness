"""
Tests for soft evaluation helper modules.
"""

from pathlib import Path

from python_harness.soft_eval_file_summary import (
    build_default_file_summary,
    build_file_summary_messages,
    build_relative_file_path,
)
from python_harness.soft_eval_package import (
    build_package_manifest,
    build_package_synthesis_messages,
    build_package_understanding,
)
from python_harness.soft_eval_sampling import (
    build_sampled_entity_result,
    extract_ast_entities,
    parse_sampling_qa_response,
)


def test_file_summary_helpers_build_relative_defaults(tmp_path: Path) -> None:
    file_path = tmp_path / "pkg" / "module.py"
    file_path.parent.mkdir()
    file_path.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")

    relative_path = build_relative_file_path(file_path, tmp_path)
    summary = build_default_file_summary(file_path, tmp_path, tokens=12)
    file_content = "def value() -> int:\n    return 1\n"
    messages = build_file_summary_messages(file_path, file_content)

    assert relative_path == "pkg/module.py"
    assert summary == {
        "file": "pkg/module.py",
        "tokens": 12,
        "summary": "File module.py contains 12 tokens.",
        "key_entities": [],
    }
    assert messages[1]["content"].startswith("File name: module.py")


def test_package_helpers_build_manifest_and_messages() -> None:
    package_understanding = build_package_understanding(total_files=2, total_tokens=30)
    manifest = build_package_manifest(
        [
            {
                "file": "a.py",
                "summary": "Handles A.",
                "key_entities": ["foo", "Bar"],
            },
            {
                "file": "b.py",
                "summary": "Handles B.",
                "key_entities": [],
            },
        ]
    )
    messages = build_package_synthesis_messages(manifest)

    assert package_understanding == (
        "The package contains 2 files with a total cognitive load of 30 tokens."
    )
    assert "- a.py: Handles A. (Entities: foo, Bar)" in manifest
    assert "- b.py: Handles B. (Entities: )" in manifest
    assert "Package files and summaries" in messages[1]["content"]


def test_sampling_helpers_extract_and_format_entities(tmp_path: Path) -> None:
    content = (
        "import os\n"
        "from pathlib import Path\n\n"
        "def foo():\n"
        "    return 1\n\n"
        "class Bar:\n"
        "    pass\n"
    )

    entities = extract_ast_entities(tmp_path / "sample.py", content)
    qa_result = parse_sampling_qa_response(
        '{"explanation":"ok","readability_score":88,"feedback":"clear"}'
    )
    sampled_entity = build_sampled_entity_result(
        entities[0],
        score=qa_result["score"],
        feedback=qa_result["feedback"],
    )

    assert {entity["name"] for entity in entities} == {"foo", "Bar"}
    assert {entity["fan_out"] for entity in entities} == {2}
    assert sampled_entity["score"] == 88.0
    assert sampled_entity["feedback"] == "clear"
    assert sampled_entity["entity"].endswith("(from sample.py)")
