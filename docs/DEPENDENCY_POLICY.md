# ABCI-MI Dependency Management Policy

**Document Version:** 1.0.0  
**Status:** Mandatory Engineering Standard

---

## 1. Core Principles: Minimal Dependencies & Reuse First

Every external dependency introduced into ABCI-MI adds maintenance overhead, potential security vulnerabilities, build complexity, and memory footprint. Therefore:

```
REUSE EXISTING CODE > STANDARD LIBRARY > APPROVED EXISTING DEPENDENCY > NEW DEPENDENCY
```

---

## 2. Dependency Evaluation & Adoption Protocol

Before proposing or adding ANY new external package to `backend/requirements.txt`:

### Step 1: Check Existing Codebase
Can the required functionality be achieved using:
- Python Standard Library (`pathlib`, `json`, `hashlib`, `asyncio`, `typing`, `uuid`, `re`)?
- Existing project modules (`app/core`, `app/infrastructure`, `app/services`)?
- Already installed third-party libraries (e.g., `pydantic`, `sqlalchemy`, `httpx`, `redis`, `qdrant-client`)?

### Step 2: Formal Justification
If a new dependency is required, the developer must justify:
1. **Problem Statement**: What exact capability is missing?
2. **Alternative Analysis**: Why cannot standard Python or existing dependencies fulfill this need?
3. **Maintenance & Health**: Is the package actively maintained, backed by a credible community, and verified for Python 3.11+?
4. **License Compatibility**: Is the license permissive (e.g., MIT, Apache 2.0, BSD)? (GPL/AGPL dependencies are prohibited).

### Step 3: Architecture Review Approval
The dependency must be reviewed and approved prior to updating `requirements.txt`.

---

## 3. Duplicate Library Prohibition

Having multiple libraries that serve overlapping purposes is strictly forbidden. The approved standard packages are:

| Capability | Approved Standard Package | Prohibited Duplicate Packages |
| :--- | :--- | :--- |
| **HTTP Client** | `httpx` (async/sync support) | `requests`, `aiohttp`, `urllib3` |
| **Data Validation & DTOs** | `pydantic` v2 | `marshmallow`, `attrs`, `dataclasses-json` |
| **Database ORM & Migrations**| `SQLAlchemy` (2.0+) + `alembic` | `tortoise-orm`, `peewee`, `databases` |
| **Redis Cache / PubSub** | `redis` (asyncio client) | `aioredis` (deprecated legacy), `redis-py` duplicate |
| **Vector Database Client** | `qdrant-client` | `chromadb`, `pinecone-client`, `weaviate-client` |
| **Testing Framework** | `pytest` + `pytest-asyncio` | `unittest` runner, `nose2` |
| **Mocking** | `unittest.mock` / `pytest-mock` | `responses`, `httpretty` |
| **Date/Time Handling** | Standard `datetime` with UTC | `arrow`, `moment`, `pendulum` (unless heavy timezone arithmetic is justified) |

---

## 4. Version Pinning & Lockfile Management

1. **Exact Version Pinning**: All production dependencies listed in `backend/requirements.txt` MUST be pinned to exact semantic versions (e.g., `fastapi==0.115.6`).
2. **Range Constraints for Dev Tools**: Development tooling (e.g., linters, formatters) must also use fixed versions to ensure deterministic CI builds.
3. **Periodic Upgrade & Vulnerability Audits**: Dependencies must be audited quarterly using `pip-audit` to detect outdated packages or security CVEs.
