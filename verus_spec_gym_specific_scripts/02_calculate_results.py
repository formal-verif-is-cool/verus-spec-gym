#!/usr/bin/env python3
"""Summarize Verus-SpecGym Harbor results.

Usage:
    python3 verus_spec_gym_specific_scripts/02_calculate_results.py <job-or-trials-dir>

The script intentionally does not assume access to the Verus-Gym analysis cache.
It reads each Harbor trial directory directly, preferring
`SubmissionResultMoreDetail.json` when present and otherwise reading
`EvaluationFeedback.json` from the verifier `results.zip`.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TASKS_LIST_PATH = SCRIPT_DIR / "tasks_list.json"

BUCKETS = ("pre_sound", "pre_complete", "post_complete", "post_sound")
RESULTS_ZIP_RELATIVE_PATH = (
    Path("verifier") / "compressed_verdicts" / "run_on_all_samples" / "results.zip"
)
DETAIL_JSON_RELATIVE_PATH = (
    Path("verifier")
    / "compressed_verdicts"
    / "run_on_all_samples"
    / "unzipped_results"
    / "SubmissionResultMoreDetail.json"
)
FEEDBACK_JSON_RELATIVE_PATH = (
    Path("verifier")
    / "compressed_verdicts"
    / "run_on_all_samples"
    / "unzipped_results"
    / "EvaluationFeedback.json"
)


@dataclass(frozen=True)
class BucketScore:
    num_passed: int
    num_total: int

    @property
    def fraction(self) -> float | None:
        if self.num_total == 0:
            return None
        return self.num_passed / self.num_total


@dataclass(frozen=True)
class TaskScore:
    task_name: str
    trial_dir: Path
    buckets: dict[str, BucketScore]
    did_pass: bool
    source: str
    reward: float | None = None
    exception_type: str | None = None


def problem_id_to_task_name(problem_id: str) -> str:
    contest_id, problem_index = problem_id.split("__", maxsplit=1)
    return f"verus-gym-{contest_id}-{problem_index.lower()}"


def load_expected_task_names() -> list[str]:
    problem_ids = json.loads(TASKS_LIST_PATH.read_text(encoding="utf-8"))
    if not isinstance(problem_ids, list):
        raise TypeError(f"Expected list in {TASKS_LIST_PATH}")
    if len(problem_ids) != len(set(problem_ids)):
        raise ValueError(f"Duplicate problem ids in {TASKS_LIST_PATH}")
    return [problem_id_to_task_name(problem_id) for problem_id in problem_ids]


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_from_zip(zip_path: Path, member_name: str) -> Any:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member_name) as f:
            return json.loads(f.read().decode("utf-8"))


def reward_from_result_json(trial_dir: Path) -> tuple[float | None, str | None]:
    result_path = trial_dir / "result.json"
    if not result_path.is_file():
        return None, None
    result = load_json_file(result_path)
    exception_info = result.get("exception_info")
    exception_type = None
    if isinstance(exception_info, dict):
        exception_type = exception_info.get("type") or exception_info.get("exception_type")
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    reward = rewards.get("reward")
    return (float(reward) if reward is not None else None), exception_type


def testcase_has_runtime_compile_error(testcase_result: dict[str, Any]) -> bool:
    for runtime_key in ("execution_soundness_verdict", "execution_completeness_verdict"):
        runtime_artifact = testcase_result.get(runtime_key)
        if not runtime_artifact:
            continue
        compile_verdict = runtime_artifact.get("compile_verdict") or {}
        if int(compile_verdict.get("exit_code") or 0) != 0:
            return True
    return False


def bucket_scores_from_feedback(feedback: dict[str, Any]) -> tuple[dict[str, BucketScore], bool]:
    syntax_feedback = feedback.get("syntax_check_feedback") or {}
    syntax_passed = bool(syntax_feedback.get("has_passed_syntax_checks"))
    execution_feedback = feedback.get("execution_feedback")
    if not syntax_passed or execution_feedback is None:
        return {bucket: BucketScore(num_passed=0, num_total=0) for bucket in BUCKETS}, False

    buckets: dict[str, BucketScore] = {}
    for bucket in BUCKETS:
        bucket_payload = execution_feedback.get(bucket) or {}
        if not isinstance(bucket_payload, dict):
            raise TypeError(f"Expected dict payload for bucket {bucket}, got {type(bucket_payload)}")
        num_total = len(bucket_payload)
        num_passed = sum(
            1
            for testcase_result in bucket_payload.values()
            if bool(testcase_result.get("does_testcase_have_expected_verdict"))
        )
        buckets[bucket] = BucketScore(num_passed=num_passed, num_total=num_total)

    did_pass = all(score.num_total > 0 and score.num_passed == score.num_total for score in buckets.values())
    return buckets, did_pass


def score_from_detail_json(task_name: str, trial_dir: Path, detail: dict[str, Any]) -> TaskScore:
    buckets = {
        bucket: BucketScore(
            num_passed=int(detail[f"num_passed_{bucket}"]),
            num_total=int(detail[f"num_total_{bucket}"]),
        )
        for bucket in BUCKETS
    }
    reward, exception_type = reward_from_result_json(trial_dir)
    return TaskScore(
        task_name=task_name,
        trial_dir=trial_dir,
        buckets=buckets,
        did_pass=bool(detail["did_solve_problem"]),
        source="SubmissionResultMoreDetail.json",
        reward=reward,
        exception_type=exception_type,
    )


def score_from_feedback(task_name: str, trial_dir: Path, feedback: dict[str, Any], source: str) -> TaskScore:
    buckets, did_pass = bucket_scores_from_feedback(feedback)
    reward, exception_type = reward_from_result_json(trial_dir)
    return TaskScore(
        task_name=task_name,
        trial_dir=trial_dir,
        buckets=buckets,
        did_pass=did_pass,
        source=source,
        reward=reward,
        exception_type=exception_type,
    )


def score_from_reward_only(task_name: str, trial_dir: Path) -> TaskScore | None:
    reward, exception_type = reward_from_result_json(trial_dir)
    if reward is None and exception_type is None:
        return None
    return TaskScore(
        task_name=task_name,
        trial_dir=trial_dir,
        buckets={bucket: BucketScore(num_passed=0, num_total=0) for bucket in BUCKETS},
        did_pass=(reward == 1.0),
        source="result.json reward only",
        reward=reward,
        exception_type=exception_type,
    )


def load_task_score(task_name: str, trial_dir: Path) -> TaskScore | None:
    detail_path = trial_dir / DETAIL_JSON_RELATIVE_PATH
    if detail_path.is_file():
        return score_from_detail_json(task_name, trial_dir, load_json_file(detail_path))

    feedback_path = trial_dir / FEEDBACK_JSON_RELATIVE_PATH
    if feedback_path.is_file():
        return score_from_feedback(
            task_name,
            trial_dir,
            load_json_file(feedback_path),
            "EvaluationFeedback.json",
        )

    results_zip_path = trial_dir / RESULTS_ZIP_RELATIVE_PATH
    if results_zip_path.is_file():
        feedback = load_json_from_zip(results_zip_path, "EvaluationFeedback.json")
        return score_from_feedback(
            task_name,
            trial_dir,
            feedback,
            "results.zip/EvaluationFeedback.json",
        )

    return score_from_reward_only(task_name, trial_dir)


def is_trial_dir(path: Path) -> bool:
    return (path / "result.json").is_file() and (path / "config.json").is_file()


def task_name_from_trial_dir(path: Path) -> str | None:
    result_path = path / "result.json"
    if result_path.is_file():
        try:
            result = load_json_file(result_path)
            task_name = result.get("task_name")
            if isinstance(task_name, str) and task_name:
                return task_name.split("/")[-1]
        except Exception:
            pass
    if "__" in path.name:
        return path.name.split("__", maxsplit=1)[0]
    if path.name.startswith("verus-gym-"):
        return path.name
    return None


def discover_trial_dirs(results_root: Path) -> dict[str, Path]:
    candidates: dict[str, list[Path]] = {}

    child_trial_dirs = [
        child
        for child in sorted(results_root.iterdir() if results_root.is_dir() else [])
        if child.is_dir() and is_trial_dir(child)
    ]

    if child_trial_dirs:
        for child in child_trial_dirs:
            task_name = task_name_from_trial_dir(child)
            if task_name is None:
                continue
            candidates.setdefault(task_name, []).append(child)
    elif is_trial_dir(results_root):
        task_name = task_name_from_trial_dir(results_root)
        if task_name is not None:
            candidates.setdefault(task_name, []).append(results_root)

    selected: dict[str, Path] = {}
    for task_name, paths in candidates.items():
        selected[task_name] = max(paths, key=lambda path: (path / "result.json").stat().st_mtime_ns)
    return selected


def format_score(score: BucketScore) -> str:
    if score.num_total == 0:
        return "-"
    assert score.fraction is not None
    return f"{score.num_passed}/{score.num_total} ({score.fraction:.3f})"


def print_table(rows: list[TaskScore]) -> None:
    headers = ["task", *BUCKETS, "did_pass", "source"]
    table_rows = [
        [
            row.task_name,
            *(format_score(row.buckets[bucket]) for bucket in BUCKETS),
            "1" if row.did_pass else "0",
            row.source,
        ]
        for row in rows
    ]
    widths = [
        max(len(str(value)) for value in [header, *(table_row[idx] for table_row in table_rows)])
        for idx, header in enumerate(headers)
    ]
    fmt = "  ".join(f"{{:<{width}}}" for width in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * width for width in widths)))
    for table_row in table_rows:
        print(fmt.format(*table_row))


def print_summary(rows: list[TaskScore], expected_count: int) -> None:
    if not rows:
        print("No scored rows found.")
        return

    print("\nAverages over found/scored tasks:")
    for bucket in BUCKETS:
        fractions = [
            score.buckets[bucket].fraction
            for score in rows
            if score.buckets[bucket].fraction is not None
        ]
        if fractions:
            print(f"  {bucket}: {sum(fractions) / len(fractions):.4f} over {len(fractions)} tasks")
        else:
            print(f"  {bucket}: n/a")
    print(f"  did_pass: {sum(row.did_pass for row in rows) / len(rows):.4f} over {len(rows)} tasks")

    reward_rows = [row for row in rows if row.reward is not None]
    if reward_rows:
        print(f"  Harbor reward mean: {sum(row.reward or 0.0 for row in reward_rows) / len(reward_rows):.4f} over {len(reward_rows)} tasks")

    exception_counts: dict[str, int] = {}
    for row in rows:
        if row.exception_type:
            exception_counts[row.exception_type] = exception_counts.get(row.exception_type, 0) + 1
    if exception_counts:
        print("  Exceptions:")
        for exception_type, count in sorted(exception_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"    {exception_type}: {count}")

    print(f"\nCoverage: scored={len(rows)}, expected={expected_count}, missing={expected_count - len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path, help="Path to a Harbor job dir or trials dir.")
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Print missing expected task names.",
    )
    args = parser.parse_args()

    expected_task_names = load_expected_task_names()
    expected_set = set(expected_task_names)
    trial_dirs_by_task = discover_trial_dirs(args.results_dir)
    found_expected_names = [task_name for task_name in expected_task_names if task_name in trial_dirs_by_task]
    missing_names = [task_name for task_name in expected_task_names if task_name not in trial_dirs_by_task]

    print(f"Task list: {TASKS_LIST_PATH}")
    print(f"Results dir: {args.results_dir.resolve()}")
    print(
        f"Found trajectory/result dirs for {len(found_expected_names)} "
        f"out of {len(expected_task_names)} expected tasks."
    )
    unexpected = sorted(set(trial_dirs_by_task) - expected_set)
    if unexpected:
        print(f"Found {len(unexpected)} extra trial dirs not in tasks_list.json.")

    rows: list[TaskScore] = []
    failed_to_parse: list[tuple[str, str]] = []
    for task_name in found_expected_names:
        trial_dir = trial_dirs_by_task[task_name]
        try:
            score = load_task_score(task_name, trial_dir)
        except Exception as exc:
            failed_to_parse.append((task_name, repr(exc)))
            continue
        if score is not None:
            rows.append(score)

    if failed_to_parse:
        print(f"Failed to parse {len(failed_to_parse)} found trial dirs. First failures:")
        for task_name, error in failed_to_parse[:10]:
            print(f"  {task_name}: {error}")

    if args.show_missing and missing_names:
        print("\nMissing expected tasks:")
        for task_name in missing_names:
            print(f"  {task_name}")

    print()
    print_table(rows)
    print_summary(rows, expected_count=len(expected_task_names))


if __name__ == "__main__":
    main()
