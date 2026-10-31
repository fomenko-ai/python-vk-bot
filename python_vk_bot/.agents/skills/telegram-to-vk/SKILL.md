---
name: telegram-to-vk
description: Migrate python-telegram-bot applications to VK community bots with python-vk-bot, preserving business logic while adapting handlers, state, messaging and delivery to supported VK interfaces.
---

# Migrate a Telegram bot to VK

Work in the user's bot project. Read its `AGENTS.md` and approval rules before changing files.
Do not modify python-vk-bot itself unless explicitly requested.

1. Inspect the source project's installed/locked python-telegram-bot version, initialization,
   configuration, handlers, filters, conversations, context/state, scheduled jobs, media,
   error handling, integrations and business services. Do not assume the source uses current PTB.
2. Inspect the installed or checked-out python-vk-bot version and its public interfaces.
   Read [the migration mapping](references/migration-mapping.md), then verify each relevant
   mapping against that version's sources. The reference is a baseline, not permission to
   invent classes, methods, filters or features.
3. Build a source-to-target inventory with supported equivalents, behavior differences,
   unsupported functionality and manual configuration. Verify version-dependent VK claims
   against current official documentation; cite sources and label uncertainties. Distinguish
   the library's missing wrapper from a capability absent on the platform.
4. Propose a migration that keeps platform-independent business logic and adapts the actual
   Telegram integration points. Address peers/users/communities, message IDs, commands,
   keyboards, button events, media, editing/deletion, permissions, limits, state and delivery.
   Avoid speculative shared-platform abstractions; migration is more than import replacement.
5. Obtain required approval for the migration, affected files and intentional behavior changes.
   Follow local approval gates; test changes require approval of the corresponding main code
   and separate test-edit authorization. Never silently remove unsupported functionality.
6. Implement the approved scope with supported interfaces, explicit configuration and safe
   token handling. Preserve async behavior, cancellation and owned-resource cleanup. Keep
   Long Poll and Callback HTTP delivery distinct from interactive message-event handling.
7. Verify initialization, commands/messages, button events, state, errors and graceful shutdown
   as applicable. Run existing checks; use mocked VK responses for automated verification.
   Do not require live credentials or send messages as part of ordinary verification.

Report original components, implemented VK replacements, unsupported functionality,
behavior differences, required manual configuration and verification results. Explain
what remains blocked or unverified. Identical behavior across platforms is not guaranteed.
