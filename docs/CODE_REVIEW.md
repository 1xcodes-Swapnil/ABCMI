# ABCI-MI Code Review & Quality Assurance Standard

**Document Version:** 1.0.0  
**Status:** Mandatory Engineering Gate

---

## 1. Purpose & Core Philosophy

Code review is a strict quality gate ensuring that every contribution is maintainable, secure, performant, and aligned with ABCI-MI architecture. Every pull request or phase change must pass this checklist before merging or progressing.

---

## 2. Mandatory Code Review Checklist

### 2.1 Duplication & Component Reuse (MANDATORY RULE)
- [ ] **Existing Code Check**: Did the author check if a function, class, utility, or schema already exists?
- [ ] **No Duplicate Helpers**: Are utility functions (e.g., date parsing, string sanitization, UUID handling) centralized rather than reimplemented locally?
- [ ] **No Duplicate Database Models**: Are existing mixins (`BaseModel`, `UUIDPrimaryKeyMixin`, `TimestampMixin`) used?
- [ ] **No Duplicate Schemas**: Are existing response envelopes (`StandardResponse[T]`, `ErrorResponse`) reused?

### 2.2 Unnecessary Code & Dead Code Elimination
- [ ] **No Speculative Code (YAGNI)**: Are there functions, parameters, or classes added "just in case" for future phases that are not needed now?
- [ ] **No Dead Code**: Are all imported modules, variables, and internal functions actually used?
- [ ] **No Leftover Debuggers / Prints**: Are all `print()` calls, commented-out code blocks, and debugging breakpoints completely removed?

### 2.3 Architecture & Layering Verification
- [ ] **Unidirectional Dependency**: Does the dependency flow inward (API -> Service -> Repository -> Model/Infrastructure)?
- [ ] **No ORM in API Routers**: Are endpoints delegating all business logic and queries to services/repositories?
- [ ] **No Circular Imports**: Are modules cleanly organized without circular reference workarounds?

### 2.4 Security & Data Protection
- [ ] **Input Validation**: Are all API parameters and request bodies strictly typed and validated with Pydantic?
- [ ] **SQL Injection Prevention**: Are all database queries parameterized via SQLAlchemy ORM (no raw string concatenation)?
- [ ] **Secrets & PII Protection**: Are sensitive values (passwords, tokens, keys) excluded from logs and error responses?
- [ ] **Path Traversal Protection**: Are file upload paths sanitized and checked against path traversal attacks (`../`)?

### 2.5 Performance & Asynchronous Discipline
- [ ] **Non-Blocking Event Loop**: Are all I/O operations (DB, Redis, Qdrant, HTTP, disk) properly awaited using `async`?
- [ ] **Threadpool Delegation for CPU Tasks**: Are heavy computational algorithms run in thread pools or background queues?
- [ ] **Efficient Database Queries**: Are queries avoiding N+1 patterns (e.g., using `selectinload` or `joinedload` where appropriate)?
- [ ] **Connection Lifecycle**: Are database sessions and Redis/Qdrant connections cleanly acquired and returned to pools?

### 2.6 Error Handling & Observability
- [ ] **Domain Exceptions**: Are errors raised as subclasses of `AppException` with meaningful error codes?
- [ ] **Structured Logging**: Are log statements created using `get_logger(__name__)` with contextual data?
- [ ] **Graceful Degradation**: Does the service handle infrastructure unavailability gracefully without crashing the server?

### 2.7 Test Coverage & Validation
- [ ] **Unit Tests Included**: Are unit tests provided for all new business logic paths and edge cases?
- [ ] **Integration Tests Included**: Are API endpoints and database operations validated with async tests?
- [ ] **Zero Regressions**: Does the entire existing test suite pass?

---

## 3. Code Review Sign-Off Criteria

A change can only be approved if **100% of the checklist items are satisfied**. Any violation of the Mandatory Reuse Rule or Layering Boundary requires immediate refactoring before acceptance.
