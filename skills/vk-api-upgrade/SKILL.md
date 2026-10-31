---
name: vk-api-upgrade
description: Verify VK API compatibility and plan or implement approved python-vk-bot upgrades when API versions, methods, models, events, Long Poll or Callback behavior change.
---

# VK API compatibility and upgrades

Use this skill in the python-vk-bot source repository. An audit can finish with a report;
an upgrade requires the applicable approvals before edits.

1. Read the repository's `AGENTS.md`, relevant decisions and active task record. Check Git
   status and current sources before relying on recorded state. Inventory configured API
   versions, method wrappers, request/response models, events, authentication, transport,
   Long Poll, Callback, tests and compatibility documentation.
2. Read [the compatibility checklist](references/compatibility-checklist.md) for the audit.
   Recheck the latest applicable version using official VK documentation on every audit or
   upgrade. Record the configured version, verified target, date, exact source URLs and
   uncertainties. A schema package version is not necessarily a VK API request version.
   If authoritative sources are inaccessible or conflicting, report that limitation rather
   than declaring a latest version or upgrading on a guess.
3. Compare only implemented coverage with the verified documentation. Separate confirmed
   incompatibilities, unaffected behavior, unsupported features and unverified assumptions.
   Do not invent methods, fields, event shapes, permissions or numeric rate limits.
4. Present findings, affected files, proposed changes, compatibility risks and needed tests.
   Follow `AGENTS.md` approval gates, including approval before changes spanning more than
   two files. Do not change production code before the required approval. Test edits require
   approval of the corresponding main-code changes and separate authorization to edit tests.
5. Implement only the approved upgrade. Preserve async execution, cancellation, resource
   ownership, credential redaction and VK delivery semantics. Avoid unnecessary breakage,
   but follow this project's rule against speculative compatibility layers.
   Change the configured API version only when evidence and implemented coverage justify it.
6. Run the narrowest relevant checks, then the configured project quality checks on Python
   3.14. Existing tests may run without permission to edit them. Never use live tokens for
   ordinary automated verification. Do not retry non-idempotent operations without safeguards.
7. For approved changes, update `docs/development/api-compatibility.md`, relevant API/README
   documentation and the appropriate `CHANGELOG.md` section. Record versions, sources, verification
   date and remaining uncertainties. Do not assign a release or claim unimplemented support.

Report current and verified target versions, sources, findings, proposed or implemented
changes, affected modules, each check's outcome and remaining risks. If approval is pending,
leave changes as proposals and record the next action according to repository rules.
