# Full-application Kaggle REAL notebook

Upload `ABCI_MI_Full_Application_Kaggle_REAL.ipynb` to Kaggle. Enable GPU and
Internet, attach the actual complete audio, and run all cells.

Configure Kaggle Secrets (or environment variables):

- `HF_TOKEN`: authorized access to the required gated models.
- `DATABASE_URL_ASYNC`: reachable existing PostgreSQL database, using
  `postgresql+asyncpg://...`, with the repository schema and authorized user.
- `REDIS_URL`: reachable existing Redis instance.
- `QDRANT_URL` and, when required, `QDRANT_API_KEY`: existing reachable Qdrant.
- Optional `ABCI_USER_ID`, `ABCI_TENANT_ID`: existing authorized identity.
- Optional `ABCI_AUDIO_PATH`: exact mounted input when multiple recordings exist.

Laptop localhost endpoints cannot be used from Kaggle. The notebook does not
create substitute services, users, transcripts or embeddings. Attach a cached
Hugging Face `hub` tree as an input to reuse model snapshots. Only missing required
artifacts are provisioned; the size/reuse plan is printed before provisioning.

The notebook embeds 181 current backend files with a SHA-256 manifest, preserving
the existing CLI, providers and production architecture. It performs a real
10-second provider smoke, then a chunk-size probe. Only an observed CUDA OOM
permits a distinct smaller probe. Full production always receives the complete
original audio file. Results and identifiers are recorded under a unique working
directory; evidence archives include raw provider results, CLI/ACE/events,
PostgreSQL/Qdrant fresh-process read-back and chunk journals.

The existing overlap module requires a separation provider when real simultaneous
speech is detected. This provider is currently unconfigured. Such a run must
report BLOCKED; the notebook does not bypass or fabricate separation.

## Validation status

Built on 2026-10-02. All 10 code cells and embedded Python sources compile.
Archive/file hashes match the current source, and private credential exclusion
checks pass. Standard nbformat schema validation was unavailable in the builder
interpreter. No GPU inference, model download, service call or Kaggle execution
was performed for this artifact validation. Full-application execution, resume,
transcription accuracy and semantic accuracy remain NOT VERIFIED.

Build: `python backend/scripts/build_kaggle_notebook.py`.
Cheap artifact check: `python backend/scripts/validate_kaggle_notebook.py`.
