#!/usr/bin/env python3
"""Download and extract the Verus-SpecGym Harbor task zips.

The source zips were produced by verus_gym/upload_data/upload_zips.py from the
final 581-task list. This script intentionally resolves paths relative to this
Harbor checkout so it can be copied/run from a fresh clone without editing
machine-specific absolute paths.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import zipfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TASKS_LIST_PATH = SCRIPT_DIR / "tasks_list.json"

DRIVE_FOLDER_ID = "13OsxAM7t5xTnuqRoyVdMIApNuCJA4SyP"
DRIVE_FOLDER_URL = f"https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID}"

ZIP_DIR = REPO_ROOT / "datasets" / "tmp_folder_verus-spec-gym-zips"
TASKS_DIR = REPO_ROOT / "datasets" / "verus-spec-gym"
DOWNLOAD_WORKERS = 4
DOWNLOAD_TIMEOUT_SECONDS = 180
DOWNLOAD_RETRIES = 4
DOWNLOAD_RETRY_BACKOFF_SECONDS = 5
DOWNLOAD_HEARTBEAT_SECONDS = 15
EXTRACT_WORKERS = 4

REQUIRED_TASK_FILES = (
    "task.toml",
    "instruction.md",
    "environment/Dockerfile",
    "solution/solve.sh",
    "tests/test.sh",
)


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


def is_valid_zip(path: Path) -> bool:
    return path.is_file() and zipfile.is_zipfile(path)


def find_zip(task_name: str) -> Path | None:
    direct_path = ZIP_DIR / f"{task_name}.zip"
    if is_valid_zip(direct_path):
        return direct_path

    matches = sorted(path for path in ZIP_DIR.rglob(f"{task_name}.zip") if is_valid_zip(path))
    if not matches:
        return None
    if len(matches) > 1:
        raise RuntimeError(f"Found multiple zips for {task_name}: {matches}")
    return matches[0]


def task_dir_is_complete(task_dir: Path) -> bool:
    return task_dir.is_dir() and all((task_dir / rel_path).is_file() for rel_path in REQUIRED_TASK_FILES)


def load_drive_zip_index() -> dict[str, str]:
    try:
        import gdown
    except ImportError as exc:
        raise RuntimeError(
            "Missing task zips and could not import `gdown`.\n"
            "Run with `uv run --with gdown python "
            "verus_spec_gym_specific_scripts/00_download_tasks_from_drive.py`, "
            f"or manually place zips under {ZIP_DIR}.\n"
            f"Google Drive folder: {DRIVE_FOLDER_URL}"
        ) from exc

    print(f"Listing Google Drive folder: {DRIVE_FOLDER_URL}")
    drive_files = gdown.download_folder(
        DRIVE_FOLDER_URL,
        output=str(ZIP_DIR),
        quiet=True,
        use_cookies=False,
        skip_download=True,
    )

    zip_ids_by_name: dict[str, str] = {}
    for drive_file in drive_files:
        zip_name = Path(drive_file.path).name
        if not zip_name.endswith(".zip"):
            continue
        if zip_name in zip_ids_by_name:
            raise RuntimeError(f"Found duplicate zip in Drive folder: {zip_name}")
        zip_ids_by_name[zip_name] = drive_file.id
    return zip_ids_by_name


def download_one_zip_once(task_name: str, file_id: str) -> Path:
    zip_path = ZIP_DIR / f"{task_name}.zip"
    partial_path = ZIP_DIR / f"{task_name}.zip.part"
    if is_valid_zip(zip_path):
        return zip_path
    if zip_path.exists():
        zip_path.unlink()
    if partial_path.exists():
        partial_path.unlink()

    command = (
        sys.executable,
        "-c",
        (
            "import gdown, sys; "
            "path = gdown.download(id=sys.argv[1], output=sys.argv[2], "
            "quiet=True, use_cookies=False); "
            "raise SystemExit(0 if path else 2)"
        ),
        file_id,
        str(partial_path),
    )
    subprocess.run(
        command,
        check=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not is_valid_zip(partial_path):
        raise RuntimeError(f"Downloaded file is not a valid zip: {partial_path}")
    partial_path.replace(zip_path)
    return zip_path


def download_one_zip(task_name: str, file_id: str) -> Path:
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            return download_one_zip_once(task_name, file_id)
        except subprocess.TimeoutExpired as exc:
            last_error = TimeoutError(
                f"{task_name}.zip attempt {attempt}/{DOWNLOAD_RETRIES} timed out "
                f"after {DOWNLOAD_TIMEOUT_SECONDS}s"
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            details = stderr or stdout or f"exit code {exc.returncode}"
            last_error = RuntimeError(
                f"{task_name}.zip attempt {attempt}/{DOWNLOAD_RETRIES} failed: {details}"
            )
        except Exception as exc:
            last_error = exc

        zip_path = ZIP_DIR / f"{task_name}.zip"
        partial_path = ZIP_DIR / f"{task_name}.zip.part"
        if zip_path.exists() and not is_valid_zip(zip_path):
            zip_path.unlink()
        if partial_path.exists():
            partial_path.unlink()
        if attempt < DOWNLOAD_RETRIES:
            time.sleep(DOWNLOAD_RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(
        f"Failed to download {task_name}.zip after {DOWNLOAD_RETRIES} attempts. "
        f"Last error: {last_error}"
    ) from last_error


def summarize_download_failures(
    task_names: list[str],
    drive_zip_ids: dict[str, str],
    errors_by_task: dict[str, str],
) -> str:
    lines = []
    for task_name in task_names:
        file_id = drive_zip_ids.get(f"{task_name}.zip")
        browser_url = f"https://drive.google.com/uc?id={file_id}" if file_id else "<missing file id>"
        error = errors_by_task.get(task_name, "<not attempted or no captured error>")
        lines.append(f"  - {task_name}.zip")
        lines.append(f"    browser_url: {browser_url}")
        lines.append(f"    error: {error}")
    return "\n".join(lines)


def download_missing_zips(task_names: list[str]) -> None:
    missing = [task_name for task_name in task_names if find_zip(task_name) is None]
    if not missing:
        print(f"All {len(task_names)} zips already exist under {ZIP_DIR}")
        return

    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    drive_zip_ids = load_drive_zip_index()
    missing_from_drive = [
        task_name for task_name in missing if f"{task_name}.zip" not in drive_zip_ids
    ]
    if missing_from_drive:
        preview = "\n".join(f"  - {task_name}.zip" for task_name in missing_from_drive[:20])
        raise FileNotFoundError(
            f"Missing {len(missing_from_drive)} expected zips in Drive folder. First missing:\n{preview}"
        )

    already_present = len(task_names) - len(missing)
    print(
        f"Downloading {len(missing)} missing zips with {DOWNLOAD_WORKERS} workers "
        f"({already_present}/{len(task_names)} already present). "
        f"Each file has {DOWNLOAD_RETRIES} attempts and a {DOWNLOAD_TIMEOUT_SECONDS}s timeout."
    )
    try:
        from tqdm import tqdm
    except ImportError as exc:
        raise RuntimeError(
            "Could not import `tqdm`. Run with `uv run --with gdown python "
            "verus_spec_gym_specific_scripts/00_download_tasks_from_drive.py`."
        ) from exc

    with tqdm(
        total=len(task_names),
        initial=already_present,
        desc="Downloading task zips",
        unit="zip",
    ) as pbar:
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
            futures = {
                executor.submit(download_one_zip, task_name, drive_zip_ids[f"{task_name}.zip"]): task_name
                for task_name in missing
            }
            failures: dict[str, str] = {}
            while futures:
                done, _ = wait(
                    futures,
                    timeout=DOWNLOAD_HEARTBEAT_SECONDS,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    pbar.set_postfix_str(f"waiting on {len(futures)} downloads")
                    pbar.refresh()
                    continue
                for future in done:
                    task_name = futures.pop(future)
                    try:
                        future.result()
                    except Exception as exc:
                        failures[task_name] = str(exc)
                        pbar.set_postfix_str(f"failed={len(failures)}, waiting={len(futures)}")
                        continue
                    pbar.update(1)
                    pbar.set_postfix_str(f"last={task_name}")

    still_missing = [task_name for task_name in task_names if find_zip(task_name) is None]
    if still_missing:
        preview = summarize_download_failures(
            still_missing[:20],
            drive_zip_ids,
            failures,
        )
        raise RuntimeError(
            f"Still missing {len(still_missing)} zips after attempting every download. "
            "This usually means Google Drive/gdown throttled or refused those public links. "
            "You can rerun this script later; valid zips already on disk will be skipped. "
            f"First missing files:\n{preview}"
        )


def safe_extract(zip_path: Path, output_dir: Path) -> None:
    output_root = output_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (output_dir / member.filename).resolve()
            if output_root != target and output_root not in target.parents:
                raise RuntimeError(f"Refusing unsafe zip member {member.filename!r} in {zip_path}")
        zf.extractall(output_dir)


def extract_one_task(task_name: str) -> bool:
    task_dir = TASKS_DIR / task_name
    if task_dir_is_complete(task_dir):
        return False

    zip_path = find_zip(task_name)
    if zip_path is None:
        raise FileNotFoundError(f"Missing zip for {task_name}")
    safe_extract(zip_path, TASKS_DIR)

    if not task_dir_is_complete(task_dir):
        missing = [rel_path for rel_path in REQUIRED_TASK_FILES if not (task_dir / rel_path).is_file()]
        raise RuntimeError(f"Extracted {zip_path}, but {task_dir} is incomplete: {missing}")
    return True


def main() -> None:
    problem_ids = load_problem_ids()
    task_names = [problem_id_to_task_name(problem_id) for problem_id in problem_ids]

    print(f"Task list: {TASKS_LIST_PATH}")
    print(f"Number of tasks: {len(task_names)}")
    print(f"Zip dir: {ZIP_DIR}")
    print(f"Output task dir: {TASKS_DIR}")
    print(f"Download workers: {DOWNLOAD_WORKERS}")
    print(f"Extract workers: {EXTRACT_WORKERS}")

    download_missing_zips(task_names)

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    extracted = 0
    skipped = 0
    from tqdm import tqdm

    with tqdm(total=len(task_names), desc="Extracting task zips", unit="task") as pbar:
        with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as executor:
            futures = {executor.submit(extract_one_task, task_name): task_name for task_name in task_names}
            while futures:
                done, _ = wait(
                    futures,
                    timeout=DOWNLOAD_HEARTBEAT_SECONDS,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    pbar.set_postfix_str(f"waiting on {len(futures)} extracts")
                    pbar.refresh()
                    continue
                for future in done:
                    task_name = futures.pop(future)
                    did_extract = future.result()
                    if did_extract:
                        extracted += 1
                    else:
                        skipped += 1
                    pbar.update(1)
                    pbar.set_postfix_str(f"last={task_name}")

    print(
        "Download/extract summary: "
        f"tasks={len(task_names)}, extracted={extracted}, already_complete={skipped}"
    )


if __name__ == "__main__":
    main()
