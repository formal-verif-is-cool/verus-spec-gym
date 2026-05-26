# Running Verus-SpecGym in Harbor

These scripts prepare and run the Verus-SpecGym tasks in Harbor format. All paths are resolved relative to the Harbor checkout, so the scripts should not need any machine-specific absolute paths.

## Prepare the tasks

1. Download and extract the task zips:

```bash
uv run --with gdown python verus_spec_gym_specific_scripts/00_download_tasks_from_drive.py
```

The zips of the Harbor-format tasks are hosted [at this Google Drive link](https://drive.google.com/drive/folders/13OsxAM7t5xTnuqRoyVdMIApNuCJA4SyP).

This command downloads the zips into:

```text
datasets/tmp_folder_verus-spec-gym-zips
```

and extracts Harbor task directories into:

```text
datasets/verus-spec-gym
```

The script intentionally does not require `gdown` to be added as a permanent Harbor dependency. `uv run --with gdown ...` installs it only for this command. If you already have `gdown` on `PATH`, running `python3 verus_spec_gym_specific_scripts/00_download_tasks_from_drive.py` also works.

2. Add the task metadata expected by recent Harbor versions:

```bash
python3 verus_spec_gym_specific_scripts/01_add_task_string.py
```

This writes the missing `[task]` metadata into each extracted `task.toml`.

## To run the benchmark

`verus_spec_gym_specific_scripts/03_sample_run_with_oai.sh` is a small example runner for `swe-agent` through OpenRouter:

```bash
bash verus_spec_gym_specific_scripts/03_sample_run_with_oai.sh
```

The script reads `.env` from the Harbor checkout if present. For OpenRouter runs, set `OPENROUTER_API_KEY` in `.env` or in the environment. Common settings can be overridden inline:

```bash
MODEL_ID="openrouter/openai/gpt-5.3-codex" \
N_TASKS=5 \
N_CONCURRENT=1 \
JOB_NAME="sample_oai" \
bash verus_spec_gym_specific_scripts/03_sample_run_with_oai.sh
```

## To compile results from the logs

`verus_spec_gym_specific_scripts/02_calculate_results.py` takes a Harbor job directory or a single trial directory, parses the verifier artifacts directly, and prints per-task bucket scores:

```bash
python3 verus_spec_gym_specific_scripts/02_calculate_results.py <path to logs dir>
```

It prefers `SubmissionResultMoreDetail.json` when available, but it can also read `EvaluationFeedback.json` directly from verifier `results.zip`.
