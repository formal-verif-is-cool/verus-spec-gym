#!/usr/bin/env python3
"""Add Harbor registry task names to the Verus-SpecGym task.toml files."""

# I was told Harbor changed their format a bit, so we need to add a task string to each task
# use relative paths
# load all tasks from verus_spec_gym_specific_scripts/tasks_list.json

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TASKS_LIST_PATH = SCRIPT_DIR / "tasks_list.json"
TASKS_DIR = REPO_ROOT / "datasets" / "verus-spec-gym"
ORG_NAME = "verus-spec-gym"


def problem_id_to_task_name(problem_id: str) -> str:
    contest_id, problem_index = problem_id.split("__", maxsplit=1)
    return f"verus-gym-{contest_id}-{problem_index.lower()}"


def load_problem_ids() -> list[str]:
    problem_ids = json.loads(TASKS_LIST_PATH.read_text())
    if not isinstance(problem_ids, list):
        raise TypeError(f"Expected a list in {TASKS_LIST_PATH}, got {type(problem_ids)}")
    if len(problem_ids) != len(set(problem_ids)):
        raise ValueError(f"Duplicate problem ids in {TASKS_LIST_PATH}")
    return problem_ids


def build_task_block(task_name: str) -> str:
    return (
        "[task]\n"
        f'name = "{ORG_NAME}/{task_name}"\n'
        'description = "Verus-SpecGym specification autoformalization task"\n'
        'keywords = ["verus", "codeforces", "specification"]\n'
        "\n"
        "[[task.authors]]\n"
        'name = "Verus-SpecGym Authors"\n'
        "\n"
    )


def replace_or_insert_task_block(task_toml: str, task_name: str) -> str:
    task_block = build_task_block(task_name)

    task_match = re.search(r"(?m)^\[task\]\s*$", task_toml)
    if task_match is not None:
        next_section = re.search(
            r"(?m)^\[(?!\[)(?!task\])[^]]+\]\s*$",
            task_toml[task_match.end() :],
        )
        end = task_match.end() + next_section.start() if next_section is not None else len(task_toml)
        return task_toml[: task_match.start()].rstrip() + "\n\n" + task_block + task_toml[end:].lstrip()

    metadata_match = re.search(r"(?m)^\[metadata\]\s*$", task_toml)
    if metadata_match is None:
        return task_toml.rstrip() + "\n\n" + task_block
    return task_toml[: metadata_match.start()].rstrip() + "\n\n" + task_block + task_toml[
        metadata_match.start() :
    ].lstrip()


def validate_task_name(task_toml: str, task_name: str) -> None:
    parsed = tomllib.loads(task_toml)
    expected = f"{ORG_NAME}/{task_name}"
    actual = parsed.get("task", {}).get("name")
    if actual != expected:
        raise ValueError(f"Expected task name {expected!r}, got {actual!r}")


def main() -> None:
    problem_ids = load_problem_ids()
    task_names = [problem_id_to_task_name(problem_id) for problem_id in problem_ids]

    missing_task_dirs = [task_name for task_name in task_names if not (TASKS_DIR / task_name).is_dir()]
    if missing_task_dirs:
        preview = "\n".join(f"  - {task_name}" for task_name in missing_task_dirs[:20])
        raise FileNotFoundError(
            f"Missing {len(missing_task_dirs)} task dirs under {TASKS_DIR}. First missing:\n{preview}"
        )

    changed = 0
    unchanged = 0
    for task_name in task_names:
        task_toml_path = TASKS_DIR / task_name / "task.toml"
        original = task_toml_path.read_text()
        updated = replace_or_insert_task_block(original, task_name)
        validate_task_name(updated, task_name)

        if updated == original:
            unchanged += 1
            continue
        task_toml_path.write_text(updated)
        changed += 1

    print(
        "Task metadata summary: "
        f"tasks={len(task_names)}, changed={changed}, already_current={unchanged}"
    )


if __name__ == "__main__":
    main()
