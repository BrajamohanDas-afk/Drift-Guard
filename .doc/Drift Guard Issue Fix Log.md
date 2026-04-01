# Drift Guard Issue Fix Log

This file records the issues from `.doc/phase-1-3-code-review-report.md`, what was changed to fix them, where the changes were made, how the fixes were verified, and the key code blocks that were introduced or updated.

## Scope

Issues covered here:

- `H1` through `H4`
- `M1` through `M8`
- `L1` and `L2`
- `F1` through `F4`

## H1. Git Source Sync Is Not Implemented

### Problem

`POST /v1/sources/{source_id}/sync` returned a placeholder response and never performed a real sync.

### Files Changed

- `app/api/v1/sources.py`
- `app/services/ingestion/document_ingestion_service.py`
- `tests/integration/test_sources.py`

### Fix

- Replaced the placeholder sync route with real source loading and validation.
- Wired Git file ingestion through a shared `upsert_document()` service.
- Stored sync results and updated `last_synced_at`.

### Key Code

```python
@router.post("/{source_id}/sync", status_code=202)
async def sync_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.type != "git":
        raise HTTPException(status_code=400, detail="Only git sources can be synced")

    config = source.config or {}
    repo_url = config.get("repo_url")
    token = settings.github_token
    branch = config.get("branch", "main")
    path_filter = config.get("path_filter")

    git_ingestor = GitIngestor(
        repo_url=repo_url,
        token=token,
        branch=branch,
        path_filter=path_filter,
    )
    files = git_ingestor.fetch_markdown_files()
```

### Verification

- `uv run pytest tests/integration/test_sources.py -v`
- Sync test passed and confirmed the endpoint performs ingestion.

## H2. Documents Are Keyed Only By Filename

### Problem

Source-backed documents would merge incorrectly when two different files shared the same basename.

### Files Changed

- `app/services/ingestion/document_ingestion_service.py`
- `app/models/document.py`
- `alembic/versions/3ac45cd3e0fe_add_path_to_documents.py`
- `tests/integration/test_sources.py`

### Fix

- Added a shared `find_existing_document()` helper.
- Made source-backed document identity use `source_id + path`.
- Kept direct uploads source-less and matched separately.
- Added `documents.path` plus a partial unique index on `source_id + path`.

### Key Code

```python
async def find_existing_document(
    db: AsyncSession,
    *,
    title: str,
    source_id: uuid.UUID | None,
    path: str | None,
) -> Document | None:
    query = select(Document).where(Document.is_deleted == False)

    if source_id is None:
        query = query.where(
            Document.title == title,
            Document.source_id.is_(None),
        )
    else:
        if not path:
            raise ValueError("path is required for source-backed documents")
        query = query.where(
            Document.source_id == source_id,
            Document.path == path,
        )
```

```python
op.add_column('documents', sa.Column('path', sa.Text(), nullable=True))
op.create_index(
    'ix_documents_source_path_active',
    'documents',
    ['source_id', 'path'],
    unique=True,
    postgresql_where=sa.text(
        'source_id IS NOT NULL AND path IS NOT NULL AND is_deleted = false'
    ),
)
```

### Verification

- `uv run pytest tests/integration/test_sources.py -v`
- Verified two `runbook.md` files in different repo paths remain separate.

## H3. Upload/Version/Entity Persistence Is Not Atomic

### Problem

The upload path used multiple commits, so partial writes could be left behind if something failed mid-ingest.

### Files Changed

- `app/api/v1/documents.py`

### Fix

- Switched upload flow to `flush()` while building state.
- Committed only once after document, version, and entities were prepared.
- Added rollback in the exception path.

### Key Code

```python
        version = DocumentVersion(
            document_id=doc.id,
            raw_content=raw_text,
            normalized_content=ingestor.normalize(raw_text),
            content_hash=content_hash,
            version_number=1 if latest_version is None else latest_version.version_number + 1,
        )
        db.add(version)
        await db.flush()

        doc.latest_version_id = version.id

        for entity_data in extractor.extract(extraction_text):
            ...
            db.add(Entity(...))

        await db.commit()
        await db.refresh(doc)
        return doc

    except Exception:
        await db.rollback()
        raise
```

### Verification

- Covered through `tests/integration/test_documents.py`
- Verified upload path still creates version and entities correctly.

## H4. Test Coverage Does Not Protect Core Behavior

### Problem

Integration tests were shallow and DB state was not isolated, so regressions in upload, versioning, and extraction could slip through.

### Files Changed

- `tests/conftest.py`
- `tests/integration/test_documents.py`
- `tests/integration/test_sources.py`
- `pyproject.toml`

### Fix

- Added DB truncation before and after tests.
- Fixed async loop scope mismatch in pytest config.
- Added tests for:
  - entity persistence
  - normalized content
  - duplicate upload no-op
  - version increment on changed content
  - deleted-document visibility
  - source sync identity behavior

### Key Code

```python
TRUNCATE_SQL = """
TRUNCATE TABLE
    entities,
    document_versions,
    documents,
    sources,
    alerts,
    runbook_scores,
    audit_jobs
RESTART IDENTITY CASCADE
"""

@pytest.fixture(autouse=True)
async def reset_db_state():
    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()

    yield

    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()

    await engine.dispose()
```

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
asyncio_default_fixture_loop_scope = "function"
asyncio_default_test_loop_scope = "function"
filterwarnings = ["ignore::DeprecationWarning"]
```

### Verification

- `uv run pytest tests/integration/test_documents.py tests/integration/test_sources.py -v`
- All targeted tests passed.

## M1. Git Ingestion Only Scans One Directory Level And URL Parsing Is Brittle

### Problem

Nested Markdown files were skipped and GitHub repo URL normalization was fragile.

### Files Changed

- `app/services/ingestion/git_ingestor.py`
- `tests/unit/test_git_ingestor.py`
- `tests/integration/test_sources.py`

### Fix

- Added `_normalize_repo_name()` with support for:
  - full `https://github.com/...`
  - trailing slash
  - `.git` suffix
  - `git@github.com:owner/repo`
- Added recursive `_collect_markdown_files()`.

### Key Code

```python
def _normalize_repo_name(self) -> str:
    repo_url = self.repo_url.strip()

    if repo_url.startswith("git@github.com:"):
        repo_name = repo_url.removeprefix("git@github.com:")
    else:
        parsed = urlparse(repo_url)
        if parsed.scheme and parsed.netloc:
            if parsed.netloc != "github.com":
                raise ValueError("repo_url must point to github.com")
            repo_name = parsed.path
        else:
            repo_name = repo_url

    repo_name = repo_name.strip("/")
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
```

```python
def _collect_markdown_files(self, repo, path: str) -> list[dict]:
    contents = repo.get_contents(path, ref=self.branch)
    if not isinstance(contents, list):
        contents = [contents]

    files: list[dict] = []

    for item in contents:
        if item.type == "dir":
            files.extend(self._collect_markdown_files(repo, item.path))
            continue
```

### Verification

- `uv run pytest tests/unit/test_git_ingestor.py tests/integration/test_sources.py -v`
- Both tests passed.

## M2. Soft-Deleted Documents Remain Listable And Fetchable

### Problem

Deleted documents still appeared in normal list and fetch responses.

### Files Changed

- `app/api/v1/documents.py`
- `tests/integration/test_documents.py`

### Fix

- Filtered list query by `is_deleted == False`
- Returned `404` for deleted documents in `GET /v1/documents/{id}`

### Key Code

```python
result = await db.execute(
    select(Document)
    .where(Document.is_deleted == False)
    .offset((page - 1) * per_page)
    .limit(per_page)
)
```

```python
doc = await db.get(Document, document_id)
if not doc or doc.is_deleted:
    raise HTTPException(status_code=404, detail="Document not found")
```

### Verification

- `test_deleted_document_is_hidden_from_get_and_list`

## M3. URL Extractor Stores Trailing Punctuation

### Problem

URLs like `https://example.com/runbook.` included trailing punctuation in the stored entity.

### Files Changed

- `app/services/extraction/url_extractor.py`
- `tests/unit/test_extractors.py`
- `tests/integration/test_documents.py`

### Fix

- Broadened initial URL match
- Stripped trailing punctuation after matching

### Key Code

```python
def extract_urls(text: str) -> list[str]:
    raw = re.findall(r'https?://[^\s<>"\')\]]+', text)
    cleaned = [url.rstrip('.,;:!?)>') for url in raw]
    return cleaned
```

### Verification

- Document integration test expects `https://example.com/runbook`

## M4. Owner Extractor Creates Email False Positives

### Problem

Emails such as `alice@example.com` could produce bogus owner entities.

### Files Changed

- `app/services/extraction/owner_extractor.py`

### Fix

- Added lookbehind/lookahead constraints so `@owner` tokens are not extracted out of emails.

### Key Code

```python
pattern = r'(?<![a-zA-Z0-9._%+-])@[a-zA-Z0-9_]+(?!\.[a-zA-Z])|team-[a-zA-Z0-9_-]+'
```

## M5. IAM Role Extractor Is Not Restricted To IAM Roles

### Problem

The previous regex accepted invalid IAM ARNs and non-role values.

### Files Changed

- `app/services/extraction/iam_role_extractor.py`
- `tests/unit/test_extractors.py`

### Fix

- Restricted the match to 12-digit accounts and `role/...` ARNs only.

### Key Code

```python
pattern = r'arn:aws:iam::[0-9]{12}:role/[a-zA-Z0-9+=,.@_/-]+'
```

## M6. Command Extractor Misses Prompt-Prefixed Commands

### Problem

Lines like `$ kubectl get pods` were not extracted.

### Files Changed

- `app/services/extraction/command_extractor.py`
- `tests/unit/test_extractors.py`

### Fix

- Allowed optional shell prompt prefix in the line-based command regex.

### Key Code

```python
LINE_COMMAND_PATTERN = re.compile(
    r"^\s*(?:\$\s*)?((?:kubectl|helm|docker|aws|bash|sh|python|curl)\b.*)$",
    re.MULTILINE,
)
```

## M7. Cluster Extractor Can Truncate Longer Cluster Names

### Problem

Longer cluster names like `prod-us-east-1-blue` were truncated.

### Files Changed

- `app/services/extraction/cluster_extractor.py`
- `tests/unit/test_extractors.py`

### Fix

- Extended the regex to allow suffix segments after the region block.

### Key Code

```python
pattern = r'(?:prod|staging|dev)-[a-z]+-[a-z]+-[0-9]+(?:-[a-z0-9]+)*'
```

## M8. Core Version Pointer And Rollback Path Are Weak At The Schema Level

### Problem

- `latest_version_id` had no DB foreign key
- base migration downgrade order was invalid once FK relationships mattered

### Files Changed

- `app/models/document.py`
- `alembic/versions/04c74d378803_create_all_tables.py`
- `alembic/versions/9d2d6d6a4c3b_add_latest_version_fk_to_documents.py`

### Fix

- Added `ForeignKey("document_versions.id")` to `latest_version_id`
- Added migration to create the FK
- Corrected base migration downgrade order

### Key Code

```python
latest_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    ForeignKey("document_versions.id"),
    nullable=True,
)
```

```python
op.create_foreign_key(
    "fk_documents_latest_version_id_document_versions",
    "documents",
    "document_versions",
    ["latest_version_id"],
    ["id"],
)
```

### Verification

- `docker compose exec app uv run alembic upgrade head`

## L1. `.env.example` Is Incomplete

### Problem

The example env file was missing current required settings.

### Files Changed

- `.env.example`

### Fix

- Added:
  - `GITHUB_TOKEN`
  - `SQL_ECHO`
  - `API_KEY`

### Key Code

```env
GITHUB_TOKEN=your-github-token-here
SQL_ECHO=false
API_KEY=change-me
```

## L2. README Is Materially Out Of Date

### Problem

The old README still described the repo as an early scaffold and pointed to outdated startup steps.

### Files Changed

- `README.md`

### Fix

- Replaced the old README fully
- Standardized naming to `Drift Guard`
- Documented:
  - what the project is
  - the problem it solves
  - how it helps
  - Docker-first run flow
  - migrations and tests

### Verification

- Manual read-through against current repo structure and run flow

## F1. No Authentication Or Authorization On API Endpoints

### Problem

Any reachable caller could use read/write routes.

### Files Changed

- `app/config.py`
- `app/dependencies/auth.py`
- `app/api/v1/documents.py`
- `app/api/v1/sources.py`
- `.env.example`

### Fix

- Added `API_KEY` setting
- Added `require_api_key()` dependency
- Applied API key auth to documents and sources routers

### Key Code

```python
async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
```

```python
router = APIRouter(dependencies=[Depends(require_api_key)])
```

### Verification

- Missing key on `GET /v1/documents` returned `401`
- Valid key path was exercised during later source creation checks

## F2. Upload Handling Is Unbounded And Trusts UTF-8 Input

### Problem

Upload route read arbitrary file size into memory and raised `500` on invalid UTF-8.

### Files Changed

- `app/api/v1/documents.py`
- `tests/integration/test_documents.py`

### Fix

- Added max file size limit of 1 MiB
- Added clean `400` for invalid UTF-8
- Added clean `413` for oversized uploads

### Key Code

```python
MAX_UPLOAD_BYTES = 1024 * 1024

content = await file.read(MAX_UPLOAD_BYTES + 1)
if len(content) > MAX_UPLOAD_BYTES:
    raise HTTPException(
        status_code=413,
        detail="Uploaded file is too large",
    )
try:
    raw_text = content.decode("utf-8")
except UnicodeDecodeError as exc:
    raise HTTPException(
        status_code=400,
        detail="Uploaded file must be valid UTF-8 Markdown text",
    ) from exc
```

### Verification

- `test_upload_rejects_invalid_utf8`
- `test_upload_rejects_oversized_file`

## F3. SQL Echo Logging Is Always Enabled

### Problem

SQL logging could expose document content and source details in logs.

### Files Changed

- `app/config.py`
- `app/database.py`
- `.env.example`

### Fix

- Added configurable `sql_echo: bool = False`
- Wired engine echo to `settings.sql_echo`
- Added `SQL_ECHO=false` to env example

### Key Code

```python
engine = create_async_engine(settings.database_url, echo=settings.sql_echo)
```

## F4. Source Configuration Is Stored As Arbitrary JSON

### Problem

Source config accepted arbitrary JSON and allowed request payloads to carry Git token values.

### Files Changed

- `app/schemas/source.py`
- `app/api/v1/sources.py`

### Fix

- Added typed `GitSourceConfig`
- Restricted `SourceCreate.type` to `"git"`
- Required a structured `config`
- Removed token from request/body contract
- Read Git token only from `settings.github_token`

### Key Code

```python
class GitSourceConfig(BaseModel):
    repo_url: str
    branch: str = "main"
    path_filter: Optional[str] = None

class SourceCreate(BaseModel):
    name: str
    type: Literal["git"]
    config: GitSourceConfig
```

```python
source = Source(
    name=source_data.name,
    type=source_data.type,
    config=source_data.config.model_dump(exclude_none=True),
)
```

```python
token = settings.github_token
```

### Verification

- Valid request accepted when run against local host-mode app on port `8001`
- Invalid request rejected with validation error:

```json
{"detail":[{"type":"missing","loc":["body","config","repo_url"],"msg":"Field required","input":{"random_key":"wrong"}}]}
```

## Verification Summary

Main verification commands used during the fixes:

```powershell
uv run pytest tests/integration/test_documents.py tests/integration/test_sources.py -v
uv run pytest tests/unit/test_git_ingestor.py tests/integration/test_sources.py -v
docker compose exec app uv run alembic upgrade head
```

Additional manual verification:

- `GET /health`
- API key negative check on `/v1/documents`
- typed source creation payload on `/v1/sources`
- invalid source config rejection on `/v1/sources`

## Note On Docker Build Reliability

During later verification, Docker image rebuilds intermittently failed while downloading `uv` during:

```dockerfile
RUN pip install uv && uv sync --no-dev --frozen
```

That timeout is a build/network issue and is separate from the application fixes listed above.

## Suggested Git Commit Message

```text
fix: close phase 1-3 review findings and harden ingestion/auth paths
```

Alternative longer message:

```text
fix: implement source sync, stabilize document identity, strengthen tests, and harden API/config handling
```