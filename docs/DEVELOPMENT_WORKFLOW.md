# ABCI-MI Development Workflow & Engineering Lifecycle

**Document Version:** 2.0.0  
**Status:** Mandatory Process Standard

---

## 1. The 8-Stage Development Lifecycle

Every feature, enhancement, or phase implementation MUST adhere strictly to the following 8-stage lifecycle:

```
┌───────────────┐     ┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│ 1.REQUIREMENT │ ──► │  2. DESIGN   │ ──► │  3. REVIEW   │ ──► │ 4. IMPLEMENT  │
└───────────────┘     └──────────────┘     └──────────────┘     └───────┬───────┘
                                                                        │
┌───────────────┐     ┌──────────────┐     ┌──────────────┐             │
│  8. COMMIT    │ ◄── │ 7. REFACTOR  │ ◄── │6. CODE REVIEW│ ◄── 5. TEST ◄┘
└───────────────┘     └──────────────┘     └──────────────┘
```

---

## 2. Stage Breakdown & Execution Rules

### Stage 1: REQUIREMENT
- Identify the explicit requirement ID from `REQUIREMENTS_TRACEABILITY.md` (e.g. `REQ-SKW-01`, `REQ-ACE-01`, `REQ-QRY-01`).
- Establish the strict functional boundaries of the task.
- Explicitly disallow out-of-scope or speculative feature additions.

### Stage 2: DESIGN
- **Inspect existing codebase first**: Check `app/models`, `app/schemas`, `app/repositories`, `app/services`, and `app/infrastructure` for reusable components.
- Formulate concrete data contracts (Pydantic schemas, ORM models, Service interfaces).
- Verify unidirectional dependency flow and absence of circular imports.

### Stage 3: REVIEW (Design Gate)
- Ensure design complies with `ARCHITECTURE.md` and `API_GUIDELINES.md`.
- Confirm that no duplicate libraries, unnecessary tables, or redundant classes are introduced.

### Stage 4: IMPLEMENT
- Write the minimum clean, robust code needed to satisfy the requirement.
- Follow `CODING_STANDARDS.md` (type hints, async discipline, Pydantic validation, explicit error handling).
- Keep functions small, single-responsibility, and readable.

### Stage 5: TEST
- Implement unit tests for domain business logic in `tests/`.
- Implement integration/API tests verifying status codes, schema validation, and database operations.
- Execute the test suite using `pytest` and verify that all tests pass without regressions.

### Stage 6: CODE REVIEW
- Execute the mandatory `CODE_REVIEW.md` checklist:
  - Eliminate duplicate logic.
  - Remove dead code or unused imports.
  - Audit security, permissions, and input sanitization.
  - Audit performance and async safety.

### Stage 7: REFACTOR
- Clean up any code smells or suboptimal patterns identified in review.
- Re-run the full test suite to guarantee zero regression.

### Stage 8: COMMIT
- Verify all documentation (`ARCHITECTURE.md`, `REQUIREMENTS_TRACEABILITY.md`, `DECISIONS.md`) is updated in sync with code modifications.
