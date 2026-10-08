# REAL live processing

## Architecture decision

Run the browser and API on the laptop and keep model inference in a separate,
long-running CUDA worker. The same worker can run on another GPU host without
moving the API. PostgreSQL owns queued jobs, leases, actual model output and
completion state. Redis remains the existing notification path; it is not the
durable work queue. Multiple workers claim independent jobs using PostgreSQL
`FOR UPDATE SKIP LOCKED`. Run only one worker process per GPU.

The browser sends actual mono PCM WAV in 8-second windows with a 3-second
overlap (5-second step). Each accepted chunk and job are committed together.
Identical resubmissions return the existing chunk; changed content or timestamps
for an existing sequence are rejected. The API validates SHA-256, duration,
sequence and coverage. At six outstanding chunks it returns HTTP 429. The UI
stops capture if uploads fall behind and retains unsent audio in the current
tab for explicit retry. Closing the tab loses audio not yet accepted by the API.

MOSS produces provisional captions on the worker. Chunk speaker labels are
explicitly provisional. Stop queues finalization and leaves the session in
`stopping` until every chunk has succeeded and the existing ACE pipeline has
committed the transcript. Finalization assembles the actual WAV, reuses persisted
MOSS output, reconciles speakers/timestamps and applies the existing overlap
algorithm, then runs PyAnnote, Sarvam, ACE, Blackboard and SKW. Qdrant and Redis
keep their existing paths. A transcript is final only after persistence/readback.

Failed/expired jobs are not automatically replayed. Inspect the saved result
journal and the job's error before an explicit recovery; CUDA OOM must not
repeat unchanged work. Job lease tokens reject late completion. This is not an
exactly-once guarantee for every downstream ACE side effect. The worker preserves
provider output in the database and `AUDIO_STORAGE_PATH/live-results`.

## Start locally on Windows

From the repository root, use separate terminals:

```powershell
& .\backend\scripts\run_live.ps1 -Role api
& .\backend\scripts\run_live.ps1 -Role worker
npm run dev
```

The launcher checks existing interpreters and installs nothing. The repository
`.venv` lacked the model dependencies; the original Python 3.11 installation
listed in `.venv/pyvenv.cfg` has the previously validated CUDA/model packages.
Override explicitly with `-Python` or `ABCI_PYTHON` if needed. REAL mode, offline
HF access and non-debug SQL logging are set by the launcher. Keep
`OPENMOSS_DEVICE=cuda` and the existing model/cache/infrastructure configuration.
Relative audio paths now resolve from the repository root regardless of CWD.

Migrations `0010_live_inference_jobs`, `0011_batch_inference_jobs` and
`0012_nullable_query_confidence` have been applied to the configured database.
For another database, use its existing Alembic deployment procedure to apply
these additive revisions; do not recreate populated tables. Newly created
live tables and the job table have RLS enabled and are accessed through the backend
database role, not a browser Supabase client.

Open http://localhost:3000. The original full sidebar/layout now uses the real
API for all eleven tabs. Supply an existing authorized access token; the server
returns its actual account and tenant. Tokens stay in browser memory. The
production entry point does not import the old prototype data/screens.

A local operator with existing database/signing configuration can obtain a
60-minute token for an existing meeting host in a private terminal:

```powershell
python backend/scripts/issue_ui_token.py --meeting-id YOUR_EXISTING_MEETING_UUID
```

Do not paste that token into chat, logs or source files. This utility preserves
the user's stored role; it does not create accounts or grant administrator access.
The former password endpoint is unavailable in REAL mode because the repository
has no implemented password verification flow.

For hidden background processes that survive closing a terminal:

```powershell
& .\backend\scripts\start_workspace.ps1 -WithWorker
```

The launcher reuses existing listeners/workers and saves process/log evidence.
Uploaded meetings enqueue durable `batch` jobs. The UI exposes actual queued,
running, completed and failed states. Cancelling applies only to queued jobs;
completed transcripts cannot accidentally be processed again through this UI.
Only live chunks retain MOSS between jobs. Deferred stages release completed
MOSS/PyAnnote/Sarvam caches to reduce simultaneous VRAM use. This cleanup has an
import/syntax check; post-change inference memory behavior remains unmeasured.

The UI displays actual provider/authorization limitations: REAL translations
currently return 503 (no registered real translation provider), semantic summary
is absent for the saved short meeting, and admin views require an actual admin.
Benchmark execution remains in the existing CLI behind its validation gates.
Rendering a tab is not evidence that its absent model capability is implemented.

## Place the worker on another GPU host

Use the same source and migration, existing compatible dependencies and valid
cached models. Configure the worker with the same PostgreSQL/Redis/Qdrant services
and the existing provider settings. Set `LIVE_WORKER_API_URL` to the reachable
HTTPS API URL ending `/api/v1`, and set the same private `LIVE_WORKER_TOKEN` on API
and worker. This read-only credential allows the worker to retrieve chunk audio;
the worker verifies each downloaded file against the persisted SHA-256. Do not
expose an unprotected laptop API to the internet. A private HTTPS network/reverse
proxy and its access must already be provisioned.

Run `python -m app.services.live_inference_worker --kind chunk` for live captions
and a worker on a **different GPU** with `--kind finalize` for deferred enrichment.
`--kind all` runs both sequentially on one GPU; a finalization job can delay new
live captions on that configuration. `--session-id UUID --once` processes at most
one matching job and exits nonzero for failure. No mock or CPU fallback is allowed.

No remote GPU endpoint or hosting account was provisioned in this task. Kaggle's
interactive notebook session is not assumed to be an always-on production worker.

## Measured validation and limits

Run `live_worker_20261002` used the existing real 10-second excerpt, with windows
0–8 and 5–10 seconds. Both MOSS calls completed on CUDA; the second reused the
loaded model. All 13 ACE tasks completed, including real PyAnnote; PostgreSQL
committed four transcript segments and a canonical transcript. A separate Python
process read back matching text. The authenticated API returned those four rows.
SKW recorded successful database/vector readback and Redis publication.

First chunk: 59.1283 seconds including model setup, 7.0998 seconds generation.
Second chunk: 2.8098 seconds total, 2.8093 seconds generation, RTF 0.562 for its
5-second duration. These two windows do **not** prove sustained real-time speed.
For continuous 8/3 windows, processing must keep up with arrivals every 5 seconds;
the observed first window's generation alone exceeded that interval. Warm startup,
a larger GPU and an actual sustained stream measurement remain necessary.

The final transcript preserves uncertain output. MOSS and PyAnnote disagree on
some speaker turns. Two alternate turns were excluded by the existing overlap
boundary policy; zero removals were classified as text duplicates. Neither
speaker accuracy, lossless reconstruction nor zero duplication is claimed.
New decision tracing exposes these separate cases without changing transcript
selection. No benchmark, long recording or dataset download was performed.

Evidence: `e2e_validation/runs/live_worker_20261002`. Browser microphone capture,
remote audio transfer, worker crash recovery and sustained-load behavior are not
verified by the successful short backend/API run. Authentication and other
prototype-wide security findings in the reading ledger still require follow-up
before public exposure.

## 2026-10-05 implementation update

The original UI now includes Projects, with project creation/editing, meeting
associations and cross-meeting views. Action items can be added, edited, completed
or cancelled. Translation controls show actual source text, target text,
provenance and regeneration history. Generated confidence is unknown unless a
provider actually supplies it; user-entered action items carry no model score.

Apply additive migrations through `0014_translation_confidence` before starting
the updated API. Migration 0013 adds nullable password enrollment columns without
assigning passwords or tenants to existing users. Connect once using an existing
authorized token, then open Account → Set or change sign-in password. Subsequent
sign-in uses email/password. The password is salted and hashed; the server loads
the current account role and rejects inactive accounts. Sessions remain in browser
memory. Password changes require the old password after initial enrollment;
existing signed sessions last until their normal expiry. The password request
limit is per API process; distributed rate limiting remains a deployment concern.

### REAL text provider

The existing meeting-understanding and translation interfaces now support
Gemini over HTTPS. No additional model download or SDK is required. Set privately
in `backend/.env`:

```dotenv
TEXT_AI_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=<your private credential>
```

The API key must not be committed. The checked model was available to the local
configured account; model catalogue access alone is not inference verification.
Generate intelligence from the saved transcript queues an `intelligence` job in
the existing PostgreSQL worker queue. The worker calls the existing understanding
engine, validates citation quotes, then writes through BlackboardSKWClient. It
does not run audio inference. Inspect actual job errors under execution nodes.
Text limits fail explicitly without truncating the transcript. No mock provider
is used when Gemini fails. Generated content is an interpretation requiring review.

Verified priority runs: `text_priority_20261005T180129Z` generated one cited
summary, committed it and read it back from PostgreSQL/Qdrant, with summary API
200. `translation_priority_20261005T180447Z` returned 201 and persisted three Hindi
translations from the same saved real transcript. This is not verification of
every supported language or long-meeting summarization. The initial text job
produced zero semantic items; its evidence is retained, and the extraction
contract now requires a grounded summary for nonempty source text.

The API lifecycle starts a Redis listener to persist scoped domain notifications.
Unavailable Redis is logged as FALLBACK with retries; Pub/Sub has no historical
delivery guarantee. Private notifications use only the recipient channel. Tenant
administrators cannot inspect another tenant's user directory or projects.
Existing external meeting adapters still simulate remote operations; they now
fail explicitly in REAL mode. Real Zoom/Teams/Meet OAuth and webhook adapters
remain an implementation/deployment gap, not a verified integration.

### 2026-10-06 operational changes
- Optional configured REAL API keys must bind to AUTH_API_KEY_USER_ID and AUTH_API_KEY_TENANT_ID for an existing active account with tenant membership. The account's current role is used. Leave keys disabled when using JWT/password login; no generic admin key principal is created.
- Reports support printable UTF-8 HTML. Open the downloaded HTML and use browser Print to PDF for scripts unsupported by the native PDF renderer. Unrepresentable PDF characters now fail explicitly instead of becoming question marks. Existing report artifacts are retained.
- Q&A supports meeting/project scope, source citations, history pagination and explicit regeneration. Query completion events follow PostgreSQL commit. Unknown confidence stays null and generated answers require review.
- Meeting/project/Q&A visibility now respects the existing host/participant/admin access rule in addition to tenant scope. Configured text jobs fail explicitly if their extraction version changed after enqueue.
- SKW metadata is persisted under provenance.knowledge_metadata; no new column/migration required. Historical metadata can only be restored from matching actual Qdrant records with repair_saved_knowledge_metadata.py.
- Current validation blocker: Supabase direct DNS failure and IPv4 pooler TCP timeout on 5432/6543. Configuration was not changed to an unverified endpoint. Restore network/project access before restarting the backend or running database checks. See e2e_validation/CHECKPOINT.md for the exact next gate.
