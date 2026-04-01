# Drift Guard Phase 1-3 Code Review Report

Date: 2026-03-24
Scope: current repository state against `README.md` Phases 1-3
Review mode: parallel architecture, security, ingestion/extraction, and testing review passes
Overall verdict: Request changes

## Executive Summary

The codebase has a reasonable Phase 1 shape and the Phase 3 extraction modules are in place, but it is not ready to be treated as complete through Phase 3.

The main blockers are:

1. Phase 2 Git sync is not actually implemented at the API boundary.
2. Document identity is keyed only by filename, which will merge unrelated runbooks once Git sync is used.
3. The upload flow is not atomic, so failures can leave partially persisted state.
4. Tests are too shallow and too weakly isolated to catch regressions in the versioning and extraction flow.

## Severity Summary

| Severity | Count | Notes |
| --- | --- | --- |
| High | 4 | Phase-completion blockers |
| Medium | 8 | Correctness, data-model, and extraction reliability issues |
| Low | 2 | Documentation and developer-experience drift |
| Forward-looking hardening risks | 4 | Real risks, but mostly aligned to later roadmap phases |

## High Findings

### H1. Git source sync is not implemented

- Location: `app/api/v1/sources.py:49-50`
- Impact: Phase 2 says Git source sync is supported, but `/v1/sources/{source_id}/sync` always returns a placeholder `202` response and never validates the source, invokes `GitIngestor`, creates `DocumentVersion` rows, or runs extraction.
- Why this matters: this is a direct roadmap mismatch, so Phase 2 cannot be considered complete.

### H2. Documents are keyed only by filename

- Location: `app/api/v1/documents.py:31-39`
- Related model constraint: `app/models/document.py:12-17`
- Impact: uploads dedupe on `Document.title == file.filename`. Two different runbooks with the same basename from different repos or folders will be merged into one document history.
- Why this matters: once Git sync exists, common names like `README.md` or `runbook.md` will corrupt version history and entity attribution.

### H3. Upload/version/entity persistence is not atomic

- Location: `app/api/v1/documents.py:38-42`, `app/api/v1/documents.py:51-64`, `app/api/v1/documents.py:77-86`
- Session dependency: `app/database.py:15-17`
- Impact: the handler commits the `Document`, then the `DocumentVersion`, then updates `latest_version_id`, then commits entities. A failure after an early commit leaves durable partial state behind.
- Why this matters: a 500 during extraction can leave a versioned document without the entity rows that later phases depend on.

### H4. Test coverage does not protect the core Phase 2/3 behavior

- Locations: `tests/integration/test_documents.py:5-42`, `tests/conftest.py:10-13`
- Impact: integration tests mostly assert status codes and top-level keys; they do not verify version increments, duplicate upload no-op behavior, normalized content, entity extraction, entity persistence, or deleted-document visibility. The autouse fixture disposes the engine but does not rebuild schema or isolate DB state.
- Why this matters: the current suite can stay green while the main ingestion and extraction behavior regresses.

## Medium Findings

### M1. Git ingestion only scans one directory level and has brittle URL normalization

- Location: `app/services/ingestion/git_ingestor.py:16-28`
- Impact: `repo.get_contents(...)` is only iterated once, so nested runbooks are skipped. URL normalization is also a plain string replacement, so trailing slashes or `.git` suffixes produce invalid repo names.
- Result: even after wiring sync, common repo layouts like `docs/runbooks/**.md` will be ingested incompletely.

### M2. Soft-deleted documents remain listable and fetchable

- Location: `app/api/v1/documents.py:96-103`, `app/api/v1/documents.py:119-122`, `app/api/v1/documents.py:129-138`
- Impact: `DELETE` only flips `is_deleted`, but normal list and get paths still return those records.
- Result: soft-delete semantics are inconsistent and clients can continue seeing removed documents as active records.

### M3. URL extractor stores trailing punctuation

- Location: `app/services/extraction/url_extractor.py:3-6`
- Impact: `https?://[^\s]+` captures prose/Markdown punctuation such as `)` and `.`
- Result: malformed URL entities will later create false evidence or drift failures.

### M4. Owner extractor creates email false positives

- Location: `app/services/extraction/owner_extractor.py:3-6`
- Impact: any `@token` is treated as an owner, so strings like `alice@example.com` yield `@example`.
- Result: ordinary email text becomes bogus owner entities.

### M5. IAM role extractor is not restricted to IAM roles

- Location: `app/services/extraction/iam_role_extractor.py:3-6`
- Impact: the pattern accepts non-role IAM ARNs such as policies and even allows an empty account id with `[0-9]*`.
- Result: Phase 3 stores invalid `iam_role` entities.

### M6. Command extractor misses common prompt-prefixed commands

- Location: `app/services/extraction/command_extractor.py:7-25`
- Impact: lines like `$ kubectl get pods` are skipped because the multiline pattern expects the command to start immediately after leading whitespace.
- Result: common runbook command examples are not extracted.

### M7. Cluster extractor can truncate longer cluster names

- Location: `app/services/extraction/cluster_extractor.py:3-6`
- Impact: the regex matches prefixes such as `prod-us-east-1` inside longer names like `prod-us-east-1-blue`.
- Result: different clusters can collapse to the same stored entity value.

### M8. Core version pointer and rollback path are weak at the schema level

- Missing foreign key: `app/models/document.py:16-17`, `alembic/versions/04c74d378803_create_all_tables.py:43-56`
- Invalid downgrade order: `alembic/versions/04c74d378803_create_all_tables.py:108-113`
- Impact: `latest_version_id` is not DB-enforced, and rollback order will fail once foreign keys matter.
- Result: the Phase 1 data model is weaker than the application logic assumes.

## Low Findings

### L1. `.env.example` is incomplete for the current settings model

- Settings requirement: `app/config.py:8-13`
- Example file: `.env.example:1-4`
- Impact: `Settings` requires `github_token`, but `.env.example` does not define it.
- Result: a fresh setup from the example file will not match the current app config contract.

### L2. README is materially out of date

- Outdated status section: `README.md:188-209`
- Incorrect startup command: `README.md:295-300`
- Missing referenced docs: `README.md:312-315`
- Impact: the README still says the repo lacks app structure, models, migrations, routers, and tests, and points to `.\main.py` plus missing planning files.
- Result: project documentation currently describes an older scaffold, not the repository being reviewed.

## Forward-Looking Hardening Risks

These are real issues, but they are not the strongest signal for a strict �through Phase 3� completion review because the roadmap places hardening later.

### F1. No authentication or authorization on write/read endpoints

- Locations: `app/main.py:10-14`, `app/api/v1/documents.py:21-138`, `app/api/v1/sources.py:11-50`
- Risk: any reachable caller can upload, list, fetch, create sources, or soft-delete documents.
- Roadmap context: `README.md:281-287` places API auth in Phase 9.

### F2. Upload handling is unbounded and trusts UTF-8 input

- Location: `app/api/v1/documents.py:23-28`
- Risk: `await file.read()` loads the whole file into memory, and `decode("utf-8")` can raise a 500 on malformed input.

### F3. SQL echo logging is always enabled

- Location: `app/database.py:5-6`
- Risk: query logging can expose raw runbook content and source configuration values in logs.

### F4. Source configuration is stored as arbitrary JSON

- Locations: `app/schemas/source.py:6-9`, `app/api/v1/sources.py:16-20`, `app/models/source.py:15`
- Risk: this is the natural place to store tokens and other secrets, but the data is not structurally validated, redacted, or encrypted at rest.

## Strengths

- The `Document` / `DocumentVersion` split is the right foundation for auditable versioned ingestion.
- `Entity.document_version_id` preserves version-scoped extraction correctly.
- `EntityExtractor` is modular and keeps per-entity extraction logic separated cleanly.
- `app/api`, `app/models`, `app/schemas`, and `app/services` follow a clear backend structure for later phases.
- `SourceResponse` intentionally omits `config`, which at least avoids echoing source secrets back through the API.

## Verification Notes

- `coderabbit` was not installed, so the CodeRabbit-specific review path from the `code-review` skill could not be executed.
- `pytest`, `ruff`, and `mypy` could not be completed in this environment because the checked-in `.venv` hit Windows access-denied / permission errors when loading installed packages.
- `python -m compileall app tests` completed successfully, so there is no obvious syntax break in the reviewed files.
- Findings above are based on static inspection plus four parallel review passes focused on architecture, security, ingestion/extraction, and testing.

## Recommended Next Actions

1. Implement real source sync before claiming Phase 2 complete.
2. Add a stable document identity model, at minimum `source_id + path` for Git-backed docs.
3. Make upload/version/entity creation transactional.
4. Expand tests around duplicate uploads, entity persistence, deleted-document visibility, and Git ingestion recursion.
5. Tighten the extractor regexes with edge-case tests before building Phase 4 evidence collection on top of them.