# Third-party model/runtime notices

Locdex does not claim ownership of its local models or llama.cpp runtime.

## Supported default: Qwen3-Coder

- Base model: `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- GGUF source: `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF`
- Locdex quant: `Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf`
- Approximate file size: 18.6 GB
- Base/GGUF model card license at integration time: Apache-2.0
- Locdex pins the published SHA-256 for this GGUF in `model_profiles.py` and verifies the downloaded bytes before use.

## Experimental option: Kimi-K3 distilled 9B

- Upstream distilled model: `khazarai/Qwen3.5-9B-Kimi-k3-Distilled`
- GGUF source: `mradermacher/Qwen3.5-9B-Kimi-k3-Distilled-GGUF`
- Locdex quant: Q4_K_M
- Approximate file size: 5.8 GB
- Model card license at integration time: Apache-2.0
- This model is marked experimental in Locdex until the project has its own repeatable repository-agent benchmark results.

For production releases, pin a reviewed Hugging Face revision and checksum for every supported model release. The current downloader records the resolved revision and observed SHA-256 in a per-model local manifest.

## Runtime

Locdex uses `llama-cpp-python`, Python bindings around llama.cpp, as the embedded GGUF inference runtime. Users do not need Ollama.

Locdex's setup command selects upstream prebuilt wheel repositories for CPU, CUDA, Metal, ROCm, HIP Radeon or Vulkan where applicable. It deliberately passes `--only-binary=:all:` so setup fails clearly when a matching wheel is unavailable instead of silently compiling native code on the user's machine.
