# Environment Example Synchronization Design

## Goal

Keep `conf/cloud.example.env` and `conf/local.example.env` structurally synchronized with the ignored real configuration files while ensuring that secrets, credentials, and machine-specific paths never enter Git history.

## Source Of Truth

`conf/cloud.env` and `conf/local.env` remain the local reference configurations. They stay ignored by Git. A tracked script, `scripts/sync_env_examples.py`, reads those files and writes the corresponding tracked example files.

The generator preserves comments, blank lines, assignment order, variable names, and safe portable values. It does not modify either real source file.

## Sanitization Rules

The generator parses assignments as structured name/value records. It does not perform blind text replacement.

- Names containing `KEY`, `SECRET`, or `PASSWORD` receive an empty value. Names containing `TOKEN` also receive an empty value except the explicitly numeric `YTS_AUTH_ACCESS_TOKEN_TTL_SECONDS` and `YTS_GATEWAY_TEXT_MAX_TOKENS` fields.
- `YTS_DATABASE_URL` and PostgreSQL DSN values receive explicit scheme-preserving placeholder values without real usernames, passwords, hosts, or database names.
- Known local model fields receive these project-relative values:
  - `YTS_LLAMA_SERVER_BIN=desktop/vendor/llama.cpp/build/bin/llama-server`
  - `YTS_LLAMA_MODEL=desktop/vendor/llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf`
  - `YTS_IMAGEGEN_BIN=desktop/vendor/stable-diffusion.cpp/build/bin/sd`
  - `YTS_IMAGEGEN_DIFFUSION_MODEL=desktop/vendor/sd-models/flux1-schnell-q4_k.gguf`
  - `YTS_IMAGEGEN_VAE=desktop/vendor/sd-models/ae-f16.gguf`
  - `YTS_IMAGEGEN_CLIP_L=desktop/vendor/sd-models/clip_l-q8_0.gguf`
  - `YTS_IMAGEGEN_T5XXL=desktop/vendor/sd-models/t5xxl_q4_k.gguf`
- Other machine-specific absolute paths receive an explicit `/path/to/...` placeholder.
- Safe booleans, numeric limits, model identifiers, provider names, relative paths, URLs without credentials, comments, blank lines, and field order are preserved.
- A value classified as sensitive but not covered by a deterministic sanitization rule causes generation to fail before replacing either example file.

Both example outputs are prepared in memory first. Files are replaced only after parsing and sanitization of both profiles succeeds, preventing a partial cloud/local update.

## Workflow

Before committing a real configuration schema or safe default change, run:

```bash
./.tools/uv/uv run python scripts/sync_env_examples.py
```

Review the resulting diff and commit only the example files. Real `.env` files remain ignored.

The README documents this command and the rule that example changes are generated from the local real configurations rather than edited independently.

## Verification

Unit tests use temporary source files with synthetic credentials and paths to verify:

- comments, blank lines, field order, and safe values are preserved;
- API keys, JWT secrets, tokens, database credentials, and DSNs are removed;
- known local model paths become portable examples;
- unknown sensitive values fail explicitly;
- failure in either profile leaves both existing example files unchanged.

Repository contract tests verify:

- both tracked example files exist;
- real `conf/cloud.env` and `conf/local.env` remain ignored;
- committed examples contain no non-empty secret fields, credential-bearing URLs, or undocumented absolute machine paths;
- each example is accepted by the existing environment-file parser.

Full pytest, Ruff, and `git diff --check` verification must pass before integration.
