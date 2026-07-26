# Resume Intelligence

## Runtime contract

`ResumeVersion.resume_json` is the only resume-content source of truth. It is
validated against the vendored JSON Resume 1.3.1 snapshot before every immutable
version is created. `ResumeDraft` is mutable and guarded by `If-Match`; interviews,
job matching, shares and exports always bind an immutable version.

Content and presentation are versioned independently:

- `ResumeVersion`: canonical content, parent, schema/hash, language and source.
- `ResumeDesignRevision`: one of six server-owned templates and validated design
  parameters.
- `ResumeEvidenceLink`: JSON Pointer to a confirmed `CareerFact` snapshot.
- `ResumeArtifact`: idempotent PDF, PNG preview, DOCX or JSON output.
- `ResumeShareLink`: hashed token, frozen content/design revisions, redaction
  policy and access ledger.

New runtime APIs live below `/api/v2/`. Legacy v1 writes are adapters during the
flagged rollout and no longer write the old relationship tables.

## Rendering boundary

PDF and preview both use RenderCV 2.8/Typst on the `resume.render` quorum queue.
RenderCV is installed into `/opt/rendercv`, isolated from Docling's dependency
set. The required Typst package is fetched while building the image; runtime
rendering disables HTTP proxies and uses the prebuilt read-only cache.

The production render worker uses a read-only root filesystem, a bounded tmpfs,
dropped capabilities, process/memory/CPU limits and task deadlines. Uploaded
avatars are decoded, size checked, EXIF-oriented, resized and re-encoded as PNG
before they can enter a render. User text rejects raw Typst commands, images,
HTML and active URL schemes.

Share downloads never reuse the owner's artifact. They render from a distinct,
field-redacted snapshot and a resume-scoped cache key.

## Operations

Apply and verify:

```bash
python manage.py migrate
python manage.py migrate_resume_intelligence
python manage.py migrate_resume_intelligence --check-only
python manage.py check
```

The `/api/admin/v1/resume-config/` control plane manages enabled templates,
the deployed renderer version, ATS rules version, render timeout and maximum
canonical payload size. Every write requires `Idempotency-Key` and
`operation_reason`; the response and before/after snapshots are audited.
Administrators do not receive user resume content from this endpoint.

Roll out `resume-studio-v2` by internal users, then 5%, 25% and 100%. Rollback
switches the frontend/adapter flag only; it does not delete canonical versions,
drafts, assets, artifacts or legacy read data.

## Verification

Minimum release checks:

```bash
python manage.py makemigrations --check --dry-run
python manage.py test resumes staff_admin
npm --prefix ../ai-interview-frontend run build
npm --prefix ../ai-interview-admin run build
docker compose -f ../docker-compose.yml config --quiet
docker compose -f ../docker-compose.yml \
  -f ../docker-compose.production-resilience.yml config --quiet
```

Before production rollout, also run the full backend suite with the Agent
PostgreSQL checkpoint database available, build the backend image to verify the
offline RenderCV cache, and execute the six-template golden render matrix.
