# CPU-only LocdexBench image; no model weights or held-out graders are copied.
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /models /workspace \
    && git config --system --add safe.directory /workspace
WORKDIR /opt/locdex
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
RUN python -m pip install --no-cache-dir \
    --only-binary=llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
    llama-cpp-python
RUN locdex --version && python -c "import llama_cpp" && locdex runtime verify
# At execution time, the runner sets network=none, a non-root UID, read-only root,
# /tmp tmpfs, resource ceilings, and only the explicitly authorized mounts.
