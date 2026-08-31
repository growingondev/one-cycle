#!/bin/sh
set -eu

: "${LLM_MODEL_PATH:?LLM_MODEL_PATH is required}"
: "${LLM_MODEL_ALIAS:?LLM_MODEL_ALIAS is required}"
: "${LLM_HOST:?LLM_HOST is required}"
: "${LLM_PORT:?LLM_PORT is required}"
: "${LLM_CTX_SIZE:?LLM_CTX_SIZE is required}"
: "${LLM_GPU_LAYERS:?LLM_GPU_LAYERS is required}"
: "${LLM_PARALLEL:?LLM_PARALLEL is required}"
: "${LLM_THREADS:?LLM_THREADS is required}"
: "${LLM_THREADS_BATCH:?LLM_THREADS_BATCH is required}"
: "${LLM_REASONING:?LLM_REASONING is required}"

if [ ! -f "${LLM_MODEL_PATH}" ]; then
    echo "LLM model file does not exist: ${LLM_MODEL_PATH}" >&2
    exit 1
fi

set -- \
    llama-server \
    --model "${LLM_MODEL_PATH}" \
    --alias "${LLM_MODEL_ALIAS}" \
    --host "${LLM_HOST}" \
    --port "${LLM_PORT}" \
    --ctx-size "${LLM_CTX_SIZE}" \
    --n-gpu-layers "${LLM_GPU_LAYERS}" \
    --parallel "${LLM_PARALLEL}" \
    --threads "${LLM_THREADS}" \
    --threads-batch "${LLM_THREADS_BATCH}" \
    --reasoning "${LLM_REASONING}" \
    --no-ui

exec "$@"
