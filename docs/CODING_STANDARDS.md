# ABCI-MI Coding Standards & Implementation Guidelines

**Language Runtime:** Python 3.11+ / FastAPI / TypeScript (React 19 Frontend)  
**Document Version:** 2.0.0  
**Status:** Mandatory Engineering Standard

---

## 1. Core Principles

1. **REUSE > NEW CODE**: Never implement a duplicate function, utility, or class if one already exists in `app/core`, `app/infrastructure`, or `app/models`.
2. **SIMPLE > COMPLEX (KISS)**: Choose straightforward, direct logic over intricate meta-programming or deep inheritance trees.
3. **ONE CLEAR IMPLEMENTATION**: Avoid multiple ways to perform the same task across different modules.
4. **EXPLICIT > MAGIC**: Avoid hidden implicit side-effects, monkey patching, or global mutable state.
5. **MINIMAL ABSTRACTIONS**: Add abstractions only when there are at least two concrete consumers requiring polymorphic behavior.

---

## 2. Python & FastAPI Conventions

### 2.1 PEP 8 and Style Rules
- Max line length: 100 characters (enforced via Black/Ruff).
- Use 4 spaces for indentation; never tabs.
- Imports must be sorted into standard library, third-party, and local application blocks.

### 2.2 Strict Type Hints
All function signatures and class attributes **MUST** include complete type annotations. Untyped functions or returning raw untyped `dict` from business services are strictly prohibited.

```python
# GOOD: Fully typed signature and return type
async def get_meeting_summary(
    meeting_id: uuid.UUID,
    include_decisions: bool = True,
    session: AsyncSession = Depends(get_async_db),
) -> Optional[MeetingSummaryResponse]:
    ...

# BAD: Missing types and generic return
async def get_meeting_summary(meeting_id, include_decisions=True, session=None):
    ...
```

### 2.3 Async vs. Sync Discipline
- **I/O-Bound Operations**: Network calls, database queries, Redis caching, and file storage MUST be asynchronous (`async def`, `await`).
- **CPU-Bound / Heavy Sync Code**: Audio signal processing, local ML inference, or blocking CPU operations MUST be offloaded to worker threads or processes via `starlette.concurrency.run_in_threadpool` or background task queues.
- **NEVER Block the Async Event Loop**: Never use `time.sleep()`, synchronous `requests.get()`, or synchronous file I/O inside an `async def` function.

---

## 3. Pydantic v2 Schema Standards

- All schemas inherit from `app.schemas.base.CoreBaseModel`.
- Enable `from_attributes = True` for ORM-to-DTO conversion.
- Provide descriptive `Field(...)` definitions with constraints (`ge`, `le`, `min_length`, `max_length`).
- Validate incoming payloads strictly using `@field_validator` and `@model_validator(mode="after")`.

```python
from pydantic import Field, field_validator
from app.schemas.base import CoreBaseModel

class MeetingCreateRequest(CoreBaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Meeting title")
    language: str = Field("en", min_length=2, max_length=10, description="Primary language code")

    @field_validator("language")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        if v.lower() not in {"en", "hi", "ta", "te", "mr", "bn", "gu", "kn", "ml", "es", "fr", "de", "ja", "zh"}:
            raise ValueError(f"Unsupported language code '{v}'")
        return v.lower()
```

---

## 4. Frontend (TypeScript & React 19) Conventions

- Use functional React components with hooks.
- Strong typing on all props, states, and API responses.
- Tailwind CSS utility styling with zero inline style overrides.
- Icons imported exclusively from `lucide-react`.
