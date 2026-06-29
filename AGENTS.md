# AGENTS.md — AutoTok
## 1. Purpose of this file
This file contains repository instructions for coding agents working on AutoTok.
AutoTok is a local-first, modular application that converts an approved source story into a short-form vertical video. A completed pipeline may:
1. ingest or accept story text;
2. normalize and transform the story into a narration script;
3. generate or import narration audio;
4. create synchronized subtitles;
5. select and trim an authorized background video;
6. compose a vertical video;
7. generate metadata such as a title, caption, and hashtags;
8. place the result into a human-review queue;
9. optionally publish through an official platform integration in a later phase.
This file defines repository-wide working rules.
---
## 2. Primary operating rule: work only within the requested phase
AutoTok is developed incrementally.
For every task:
- Read this file before changing code.
- Identify the phase explicitly named in the user's prompt.
- Inspect the current repository before proposing changes.
- Implement only the requested phase and the minimum supporting work necessary for that phase.
- Do not implement future phases preemptively.
- Do not add speculative integrations, infrastructure, abstractions, or dependencies merely because they may be useful later.
- It is acceptable to create extension points for known future needs, but they must remain small, documented, and justified by the current phase.
- Stop after the requested phase's acceptance criteria are satisfied.
- Do not begin the next phase without a new explicit prompt.
When a task appears to conflict with the current phase boundary:
1. preserve the current phase scope;
2. document the conflict or dependency;
3. implement the smallest safe interface or placeholder needed;
4. report what was deferred.
---
## 3. Agent autonomy
The agent may create, rename, move, or delete repository files when doing so is necessary to complete the requested phase correctly.
The agent may determine an appropriate project structure based on the existing repository and current phase.
The agent should:
- make reasonable engineering decisions without asking unnecessary questions;
- prefer a coherent implementation over a literal but fragile interpretation;
- preserve working behavior unless the task explicitly changes it;
- refactor existing code when required for correctness or maintainability;
- avoid broad rewrites when a focused change is sufficient;
- add supporting documentation, tests, migrations, configuration, and scripts when they are part of a complete implementation;
- explain material architectural decisions in the final report.
The agent must not:
- silently expand the product scope;
- invent credentials, secrets, account identifiers, API responses, or successful external operations;
- claim to have tested behavior that was not actually tested;
- claim that a third-party API supports a capability without verifying its official documentation when that capability is being implemented;
- upload, publish, schedule, or send content unless the user's phase prompt explicitly authorizes that action;
- weaken safety controls simply to make a test pass;
- delete user-created data or media unless explicitly instructed or unless the data is generated test output that is safe to replace.
---
## 4. Product principles
AutoTok should be:
### 4.1 Local-first
The core development workflow should run locally.
Cloud infrastructure must not be required for the initial pipeline unless a phase explicitly introduces it.
External services may be used behind provider interfaces, but local development should support mocks, fixtures, or manually supplied inputs.
### 4.2 Human-reviewed
Generated content should be reviewable before publication.
Until a publishing phase explicitly changes this behavior:
- final output is saved locally;
- generated metadata is saved locally;
- publishing is disabled;
- no automatic posting occurs;
- no platform credentials are required.
### 4.3 Modular
The system should permit replacement of major providers without rewriting the entire pipeline.
Potential replaceable components include:
- content-source adapters;
- script transformation providers;
- text-to-speech providers;
- transcription or alignment providers;
- subtitle renderers;
- gameplay/background-video selectors;
- video rendering engines;
- metadata generators;
- storage implementations;
- publishing adapters.
Do not over-engineer interfaces before at least one concrete implementation exists.
### 4.4 Deterministic where practical
Non-AI processing should be deterministic when provided the same inputs, configuration, and random seed.
Random media selection must support a seed for repeatable tests and debugging.
LLM- or TTS-dependent behavior should preserve request metadata sufficient to reproduce or investigate a run, without storing secrets.
### 4.5 Observable
Every pipeline run should produce clear, structured status information.
A developer should be able to determine:
- which step ran;
- what input artifact it consumed;
- what output artifact it created;
- how long the step took;
- whether it succeeded, failed, or was skipped;
- why a failure occurred;
- whether a retry is safe.
### 4.6 Safe and policy-conscious
Use only content and media that the user is authorized to use.
Do not implement:
- credential theft;
- CAPTCHA bypassing;
- bot-evasion behavior;
- unofficial account takeover flows;
- rate-limit evasion;
- mass account creation;
- scraping that ignores explicit access restrictions;
- watermark removal from third-party content;
- mechanisms intended to disguise stolen or unlicensed media;
- automatic publication that bypasses official platform controls.
Prefer official APIs, documented feeds, licensed assets, user-owned assets, public-domain assets, or explicit manual input.
---
## 5. Scope boundaries
### 5.1 In scope over the project lifecycle
AutoTok may eventually support:
- manually pasted stories;
- imported text files;
- approved Reddit or RSS ingestion;
- source metadata preservation;
- story filtering and scoring;
- duplicate detection;
- narration script transformation;
- configurable hooks and calls to action;
- multiple TTS providers;
- manually supplied narration audio;
- subtitle generation and timing;
- multiple subtitle themes;
- authorized gameplay/background-video libraries;
- vertical video composition;
- batch generation;
- job tracking;
- a local review interface;
- export packages;
- official publishing integrations;
- analytics ingestion through approved APIs;
- scheduling and operational monitoring.
### 5.2 Out of scope unless explicitly added later
Do not assume support for:
- fully autonomous content publication;
- engagement manipulation;
- automated comments or direct messages;
- follower automation;
- account farming;
- reposting copyrighted clips without authorization;
- voice cloning without documented permission;
- face cloning or impersonation;
- deceptive synthetic-media practices;
- scraping private, deleted, age-restricted, or access-controlled content;
- downloading media from arbitrary third-party platforms;
- browser automation intended to bypass an unavailable official API;
- monetization guarantees;
- legal conclusions about fair use or platform eligibility.
---
## 6. Phase-gated development model
Each implementation prompt should identify one phase.
The canonical roadmap is maintained in `docs/PHASES.md` after Phase 0 creates it. Until that file exists, use the phase plan supplied with the task.
Each phase should have:
- a goal;
- in-scope capabilities;
- explicit exclusions;
- deliverables;
- acceptance criteria;
- required tests;
- completion evidence;
- deferred work.
At the beginning of a phase:
1. inspect current code, configuration, documentation, and tests;
2. summarize the current state;
3. identify any mismatch between the repository and phase prompt;
4. create a concise implementation plan;
5. begin work unless a genuinely blocking decision requires user input.
At the end of a phase:
1. run the required checks;
2. review the diff;
3. verify acceptance criteria one by one;
4. update phase documentation;
5. report files changed;
6. report commands run and their outcomes;
7. identify deferred items;
8. stop.
Do not mark a phase complete when mandatory tests or acceptance criteria remain unresolved.
---
## 7. Recommended technical direction
These are defaults, not permission to implement future phases.
### 7.1 Language
Use Python 3.12 or a later version explicitly approved by the user.
Prefer modern Python features that remain clear and maintainable.
### 7.2 Packaging
Prefer `pyproject.toml` as the central project configuration.
Use a `src/` layout unless the existing repository has a justified alternative.
Keep runtime, development, and optional provider dependencies distinguishable.
Do not add a dependency when the standard library is sufficient and equally maintainable.
### 7.3 Command-line interface
The initial application should expose a clear CLI.
Prefer stable, composable commands over one large command with many unrelated flags.
Commands should:
- validate inputs before expensive work;
- return nonzero exit codes on failure;
- print useful human-readable summaries;
- support structured logging or JSON output where appropriate;
- never print secrets;
- avoid destructive defaults.
### 7.4 Configuration
Configuration precedence should be explicit and documented.
A preferred order is:
1. command-line arguments;
2. environment variables;
3. project configuration file;
4. safe built-in defaults.
Use environment variables for secrets.
Commit `.env.example`, not `.env`.
Validate configuration at startup and fail with actionable messages.
### 7.5 Storage
Use the filesystem for early-phase artifacts.
Use SQLite when persistent structured state becomes necessary.
Do not introduce PostgreSQL, Redis, message brokers, object storage, or distributed systems before a phase requires them.
### 7.6 Media processing
Prefer direct FFmpeg invocation for production media composition unless the current implementation demonstrates a better-supported alternative.
Wrap media commands behind Python functions or services that:
- construct arguments safely;
- avoid shell injection;
- capture stdout and stderr;
- enforce timeouts where appropriate;
- raise typed, actionable errors;
- preserve the exact command in debug logs with sensitive values redacted.
Do not assume codecs, fonts, filters, or hardware acceleration exist. Detect or validate prerequisites.
### 7.7 AI and external providers
All external AI providers must be accessed behind explicit adapters.
Provider interfaces should avoid leaking provider-specific response objects into domain logic.
Every external call should define:
- timeout behavior;
- retry behavior;
- rate-limit handling;
- error mapping;
- request identifiers when available;
- cost-relevant metadata when available;
- test doubles or mocks.
Do not make real paid API calls in automated tests.
### 7.8 Web interface
Do not create a web UI until its phase requests one.
When introduced, keep the UI focused on review and operations rather than duplicating business logic.
The backend must remain usable without the UI.
---
## 8. Architecture guidelines
### 8.1 Separate domain logic from infrastructure
Domain concepts should not depend directly on:
- HTTP libraries;
- FFmpeg subprocess details;
- database clients;
- web frameworks;
- provider SDK response types.
Infrastructure adapters may depend on domain interfaces.
### 8.2 Prefer pipeline stages with explicit artifacts
A pipeline stage should have a defined input and output.
Examples of possible artifacts include:
- source record;
- normalized story;
- narration script;
- narration audio;
- subtitle document;
- selected background segment;
- render specification;
- rendered video;
- publication package.
Artifacts should have stable identifiers and machine-readable metadata.
### 8.3 Preserve provenance
For every imported story, retain enough metadata to understand its origin, subject to privacy and platform rules.
Possible metadata:
- source type;
- source identifier;
- source URL when permitted;
- retrieval time;
- original title;
- author identifier only when appropriate;
- content hash;
- license or usage note;
- transformation history.
Do not expose personal information unnecessarily in generated output.
### 8.4 Idempotency
Pipeline steps should avoid duplicating work when safely rerun.
Where appropriate:
- derive stable artifact IDs;
- detect completed outputs;
- validate existing outputs before reuse;
- support a deliberate force-regenerate option;
- avoid overwriting unrelated files.
### 8.5 Error model
Define meaningful application exceptions rather than propagating low-level errors directly to users.
Distinguish:
- invalid user input;
- missing prerequisite;
- configuration error;
- provider authentication failure;
- provider rate limit;
- temporary provider failure;
- unsupported media;
- corrupted media;
- render failure;
- persistence failure;
- policy rejection;
- duplicate content.
Error messages should state what failed, likely cause, and a practical next step.
### 8.6 No premature microservices
Keep the application as a modular monolith until demonstrated scale or deployment requirements justify separation.
Background jobs may be represented by local task abstractions before introducing distributed queues.
---
## 9. Data and artifact conventions
### 9.1 Runtime directories
Generated artifacts must not be mixed with source code.
The final structure may evolve, but runtime data should generally be separated into areas such as:
- inputs;
- work/intermediate artifacts;
- outputs;
- logs;
- cache;
- local database;
- fixtures.
Generated folders should be ignored by Git except for small intentional fixtures and placeholder files.
### 9.2 Artifact manifests
A completed run should eventually have a manifest that records:
- run ID;
- creation time;
- pipeline version;
- source identity;
- configuration snapshot with secrets removed;
- random seed;
- stage statuses;
- input and output paths;
- durations;
- checksums where useful;
- provider and model identifiers where applicable;
- failure details;
- approval state;
- publication state.
Only implement manifest fields required by the current phase, while keeping the format extensible.
### 9.3 File naming
Use filesystem-safe names.
Do not rely on story titles alone for uniqueness.
Prefer identifiers plus a short readable slug.
Avoid timestamps as the only identifier.
### 9.4 Text encoding
Use UTF-8 throughout.
Normalize line endings where appropriate.
Preserve Unicode story content while sanitizing unsupported control characters.
### 9.5 Time
Store machine-readable timestamps in UTC.
Display local time only at presentation boundaries.
Use timezone-aware datetime objects.
---
## 10. Security requirements
### 17.1 Secrets
Never commit:
- API keys;
- access tokens;
- refresh tokens;
- cookies;
- passwords;
- private keys;
- service-account credentials;
- personally identifying test data.
Add relevant patterns to `.gitignore`.
Redact secrets from logs, exceptions, snapshots, and test fixtures.
### 17.2 Input handling
Treat all imported text, filenames, URLs, metadata, and provider responses as untrusted input.
Prevent:
- command injection;
- path traversal;
- unsafe deserialization;
- uncontrolled file writes;
- server-side request forgery when URL fetching is introduced;
- template injection;
- malformed subtitle injection;
- excessive file or response sizes.
### 17.3 Subprocesses
Pass subprocess arguments as arrays rather than shell strings.
Do not use `shell=True` without a documented, unavoidable reason and targeted tests.
### 17.4 Dependencies
Prefer maintained dependencies with clear licenses.
Pin or constrain versions using the project's selected dependency strategy.
Avoid adding large frameworks for minor conveniences.
Document system dependencies such as FFmpeg separately from Python dependencies.
### 17.5 Network behavior
External network access must be explicit.
Tests should not require unrestricted internet access.
Use timeouts on all network calls.
---
## 11. Privacy requirements
Minimize retained personal data.
Do not store unnecessary Reddit usernames, email addresses, IP addresses, cookies, or account details.
Provide a clear way to delete local generated runs and associated artifacts when persistent storage is introduced.
Do not send source text to an external AI provider without making that provider use explicit in configuration and documentation.
Fixtures must use synthetic content.
---
## 12. Coding standards
### 19.1 General
Write code for clarity first.
Use descriptive names.
Keep functions focused.
Prefer composition over deep inheritance.
Avoid hidden global mutable state.
Avoid circular imports.
Keep public interfaces small.
Remove dead code rather than commenting it out.
### 19.2 Typing
Type public functions, methods, and data structures.
Use strict or meaningfully strong type checking once configured.
Do not silence type errors broadly.
Explain narrow ignores.
### 19.3 Models
Use dataclasses or validated models consistently.
Do not pass loosely structured dictionaries across core boundaries when a stable domain model is warranted.
### 19.4 Documentation
Document public modules, interfaces, commands, and non-obvious algorithms.
Comments should explain why, not restate obvious code.
Update README and phase documentation when behavior or setup changes.
### 19.5 Logging
Use the standard logging system or the selected structured logging library.
Use appropriate levels.
Include run and job identifiers where available.
Do not use print statements for reusable library diagnostics.
CLI presentation output may use a dedicated console abstraction.
### 19.6 Exceptions
Do not catch broad exceptions merely to continue.
Preserve causal chains with exception chaining.
Map low-level exceptions at infrastructure boundaries.
### 19.7 Constants
Centralize configuration values.
Avoid unexplained magic numbers, particularly for media timing, encoding, layout, retries, and limits.
---
## 13. Testing standards
### 20.1 Test pyramid
Prioritize:
1. unit tests for domain logic;
2. integration tests for filesystem, database, and subprocess adapters;
3. a small number of end-to-end smoke tests.
### 20.2 Test isolation
Tests must not:
- require paid provider calls;
- publish content;
- depend on the user's real credentials;
- modify the user's actual media library;
- depend on test execution order;
- write outside temporary directories.
### 20.3 Media fixtures
Keep fixtures intentionally small.
Where possible, generate tiny synthetic media fixtures during tests.
Do not commit large gameplay files or full rendered videos.
### 20.4 Determinism
Control:
- random seeds;
- timestamps;
- provider responses;
- temporary paths;
- locale-sensitive output.
### 20.5 Assertions
Assert observable behavior, not implementation details.
For media integration tests, inspect outputs with a probe tool rather than relying only on file existence.
### 20.6 Regression tests
Every bug fix should include a regression test when practical.
### 20.7 Slow tests
Mark slow or system-dependent tests clearly.
Document prerequisite commands and expected skips.
---
## 14. Quality gates
Once the corresponding tools exist, a completed change should pass:
- formatting;
- linting;
- type checking;
- unit tests;
- relevant integration tests;
- security or dependency checks configured in the repository;
- documentation validation where configured.
Use the commands defined by the repository, not invented substitutes.
If a check cannot run:
- explain why;
- provide the exact attempted command;
- distinguish environment failure from code failure;
- do not report the phase as fully verified.
---
## 15. Dependency and environment management
Create reproducible setup instructions.
When adding a dependency:
1. justify its purpose;
2. check whether an existing dependency already solves the problem;
3. add it to the correct dependency group;
4. update lock or resolved dependency files when used;
5. add tests;
6. update setup documentation if system prerequisites change.
Do not install packages globally as part of project scripts.
Do not mutate the developer's machine outside the repository without explicit approval.
---
## 16. Git and change-management rules
Do not discard unrelated working-tree changes.
Inspect `git status` before broad edits.
Keep changes focused on the requested phase.
Do not rewrite Git history unless explicitly instructed.
Do not create commits unless the prompt asks for commits or repository convention clearly requires them.
Do not push branches or tags unless explicitly instructed.
Generated artifacts, secrets, caches, local databases, and large media should normally be ignored.
When renaming or reorganizing code, update imports, tests, documentation, and configuration together.
---
## 17. Documentation structure
After Phase 0, the repository should normally include documentation for:
- project overview;
- local setup;
- architecture;
- phase roadmap;
- current phase/status;
- configuration;
- commands;
- media-asset policy;
- provider integrations;
- troubleshooting;
- decisions that materially constrain future work.
Do not create documentation files with overlapping purposes.
Use architecture decision records only for consequential decisions with realistic alternatives.
---
## 18. Decision-making rules
Use the following preference order:
1. correctness;
2. safety and authorization;
3. phase scope;
4. testability;
5. maintainability;
6. observability;
7. performance;
8. convenience.
Optimize performance only after measuring a relevant bottleneck, except for obviously wasteful media operations.
When uncertain:
- inspect existing code and documentation;
- choose the smallest reversible design;
- record the assumption;
- avoid blocking on preferences that can be changed later.
Ask the user only when the decision is:
- irreversible;
- credential- or cost-sensitive;
- legally or policy sensitive;
- likely to invalidate significant work;
- impossible to infer from the repository and phase prompt.
---
## 19. Required workflow for each Codex task
### Step 1: Read
Read:
- this `AGENTS.md`;
- the phase prompt;
- relevant documentation;
- current code and tests;
- current Git status.
### Step 2: Restate scope internally
Identify:
- requested outcome;
- in-scope components;
- explicit exclusions;
- acceptance criteria;
- likely files affected;
- required verification.
### Step 3: Plan
For nontrivial tasks, produce a concise plan before editing.
Do not produce an enormous speculative plan.
### Step 4: Implement incrementally
Prefer small coherent changes.
Run focused tests during implementation.
Avoid accumulating a large untested diff.
### Step 5: Verify
Run all checks relevant to changed behavior.
Review error paths and cleanup behavior.
Inspect generated media metadata when media output is involved.
### Step 6: Review the diff
Look for:
- accidental scope expansion;
- secrets;
- dead code;
- weak error handling;
- missing tests;
- misleading documentation;
- unhandled failure states;
- unsafe subprocess or filesystem behavior;
- incompatible changes.
### Step 7: Report
The final response should include:
- concise summary;
- phase completed or current completion status;
- important design decisions;
- files created, modified, moved, or removed;
- commands and checks run;
- test results;
- manual verification steps;
- known limitations;
- deferred work;
- whether any credentials or external setup are still required.
Do not state merely that the work is done.
---
## 20. Definition of done
A phase or task is done only when:
- requested behavior exists;
- behavior is integrated with the current codebase;
- acceptance criteria are met;
- errors are actionable;
- tests cover important behavior;
- relevant checks pass;
- setup and usage documentation are accurate;
- generated files are placed correctly;
- secrets are not committed;
- future-phase work has not been implemented accidentally;
- the final report is honest about verification and limitations.
A prototype shortcut is acceptable only when the phase explicitly permits it and the shortcut is documented.
---
## 21. Initial phase roadmap
The detailed roadmap should be created in `docs/PHASES.md` during Phase 0. The intended sequence is:
- Phase 0 — Repository bootstrap, architecture, tooling, and documentation.
- Phase 1 — Manual story ingestion, canonical domain models, normalization, and CLI.
- Phase 2 — Script transformation, duration budgeting, privacy cleaning, and review artifacts.
- Phase 3 — Narration audio abstraction, manual-audio path, and first TTS provider.
- Phase 4 — Subtitle model, timing/alignment, exports, and subtitle validation.
- Phase 5 — Authorized background-media library, probing, cataloging, and clip selection.
- Phase 6 — Video composition, subtitle rendering, audio mixing, export, and output validation.
- Phase 7 — Approved Reddit/source ingestion, provenance, filtering, and rate-limit-safe retrieval.
- Phase 8 — Story scoring, deduplication, policy checks, and content-review gates.
- Phase 9 — Persistent jobs, resumable pipeline orchestration, batch generation, and manifests.
- Phase 10 — Local review dashboard, editing, approval states, and export workflow.
- Phase 11 — Official publishing adapter, dry runs, scheduling, idempotency, and publication status.
- Phase 12 — Production hardening, observability, deployment packaging, performance, and operational docs.
- Phase 13 — Optional analytics feedback, experiments, and advanced content templates.
Phases 11–13 are not part of the initial local MVP.
---
## 22. Final instruction
Build AutoTok as a sequence of reviewable, testable phases.
Use this file for durable standards.
Use the current phase prompt for detailed implementation requirements.
Do not attempt to finish the entire product in one task.
