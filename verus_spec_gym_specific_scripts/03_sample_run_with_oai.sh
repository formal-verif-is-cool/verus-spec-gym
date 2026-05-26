#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/.env"
  set +a
fi

MODEL_ID="${MODEL_ID:-openrouter/openai/gpt-5.3-codex}"
DATASET_DIR="${DATASET_DIR:-${REPO_ROOT}/datasets/verus-spec-gym}"
JOBS_DIR="${JOBS_DIR:-${REPO_ROOT}/jobs_verus_spec_gym}"
JOB_NAME="${JOB_NAME:-sample_oai}"
N_TASKS="${N_TASKS:-1}"
N_CONCURRENT="${N_CONCURRENT:-1}"
TIMEOUT_MULTIPLIER="${TIMEOUT_MULTIPLIER:-2}"
OVERRIDE_CPUS="${OVERRIDE_CPUS:-4}"
PER_INSTANCE_COST_LIMIT="${PER_INSTANCE_COST_LIMIT:-2.5}"
TOTAL_COST_LIMIT="${TOTAL_COST_LIMIT:-2.5}"
PER_INSTANCE_CALL_LIMIT="${PER_INSTANCE_CALL_LIMIT:-400}"
DELETE_ENVIRONMENT="${DELETE_ENVIRONMENT:-true}"

# TODO: make sure openrouter key is set
if [[ "${MODEL_ID}" == openrouter/* ]]; then
  : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY must be set in the environment or ${REPO_ROOT}/.env}"
fi

if [[ ! -d "${DATASET_DIR}" ]]; then
  echo "Dataset directory not found: ${DATASET_DIR}" >&2
  echo "Run verus_spec_gym_specific_scripts/00_download_tasks_from_drive.py first." >&2
  exit 1
fi

delete_flag="--delete"
if [[ "${DELETE_ENVIRONMENT}" == "false" || "${DELETE_ENVIRONMENT}" == "0" ]]; then
  delete_flag="--no-delete"
fi

cd "${REPO_ROOT}"

echo "Running Verus-SpecGym sample job"
echo "  model: ${MODEL_ID}"
echo "  dataset: ${DATASET_DIR}"
echo "  jobs dir: ${JOBS_DIR}"
echo "  job name: ${JOB_NAME}"
echo "  n tasks: ${N_TASKS}"
echo "  concurrency: ${N_CONCURRENT}"

uv run harbor run \
  --path "${DATASET_DIR}" \
  --agent swe-agent \
  --model "${MODEL_ID}" \
  --jobs-dir "${JOBS_DIR}" \
  --job-name "${JOB_NAME}" \
  --n-tasks "${N_TASKS}" \
  --n-concurrent "${N_CONCURRENT}" \
  --timeout-multiplier "${TIMEOUT_MULTIPLIER}" \
  --override-cpus "${OVERRIDE_CPUS}" \
  --agent-kwarg "per_instance_cost_limit=${PER_INSTANCE_COST_LIMIT}" \
  --agent-kwarg "total_cost_limit=${TOTAL_COST_LIMIT}" \
  --agent-kwarg "per_instance_call_limit=${PER_INSTANCE_CALL_LIMIT}" \
  "${delete_flag}" \
  --yes

echo
echo "To summarize results:"
echo "  python3 verus_spec_gym_specific_scripts/02_calculate_results.py ${JOBS_DIR}/${JOB_NAME}"
