---
name: sync-compat-branch
description: Transfer committed python-vk-bot changes from main to compat/py39 while preserving Python 3.9 support. Use after a main-branch commit or when asked to carry selected commits into the compatibility branch.
---

# Transfer changes to the compatibility branch

Use this skill in the source repository. Default direction: `main` → `compat/py39`.
Use different branches only when the user explicitly specifies them.

## Establish the scope

1. Read [AGENTS.md](../../AGENTS.md), the applicable active task record and the
   target branch's [compatibility guide](../../docs/development/python-compatibility.md).
   Verify Git status, branch refs and worktrees before relying on recorded state.
2. Identify the exact source commits from the current task or user request. Inspect
   their diffs and prerequisite commits. Do not transfer all divergent history by
   default. For a merge commit, establish the intended parent and change scope
   before choosing how to apply it.
3. Check whether each change is already present using ancestry, cherry-pick source
   references, patch equivalence and target code as appropriate. Adapted backports
   may have different patches; avoid applying the same behavior twice.
4. Follow the repository's multi-file and test approval gates. Existing approval
   covers the same authorized scope; do not request it again. Additional changes
   needed for compatibility must satisfy the applicable gates. Approval to commit
   source code alone does not approve newly adapted tests.

## Apply the changes

1. Use a clean target checkout. If the current checkout contains unrelated changes,
   use a suitable worktree without disturbing them. Do not automatically stash,
   reset or discard work, or force-checkout a branch used by another worktree.
   If no safe checkout is available, record and report the blocker.
2. Prefer `git cherry-pick -x <source-commit>` when the whole commit fits the target
   and approved scope. Apply prerequisite commits in order. Otherwise transfer
   the relevant changes selectively and adapt them, recording the source SHA in
   the eventual commit body and task record. Resolve conflicts from the intended
   behavior and target requirements rather than choosing one side wholesale.
3. Preserve the target branch's supported Python versions. Review syntax, evaluated
   annotations, standard-library APIs and dependency support, including timeout
   handling on Python 3.9/3.10. Keep runtime behavior, cancellation and cleanup
   equivalent to the approved source change.
4. Transfer shared README text and package descriptions while retaining target
   installation commands, compatibility badges, `requires-python`, classifiers,
   Ruff/ty targets and conditional dependencies. Read their current values; do not
   replace the target's `pyproject.toml` or `uv.lock` with the source files wholesale.
   Regenerate the lockfile with `uv lock` after dependency metadata changes.
5. Keep release versions and dates specific to the target branch. Update its
   changelog for user-visible changes under the repository rules; do not assign a
   new version/date or copy a source release heading without authorization.
6. Explain any source-only changes that do not apply to the compatibility branch.
   If additional approval is needed, finish independent authorized work, record
   what remains and request only the missing approval with a concrete proposal.

## Verify and finish

1. Run focused checks and all configured checks required by `AGENTS.md` on Python
   3.14, using the target branch's environment and extras. With a maintained lockfile,
   verify `uv sync --locked --all-extras`.
2. For changes to runtime code, dependencies or tests, also run the syntax and runtime
   compatibility scripts described in the target's
   [verification guide](../../docs/development/verification.md). Syntax checks alone
   do not establish runtime support. Report unavailable interpreters and failures;
   do not claim unverified versions passed. Documentation-only transfers do not
   require rerunning the interpreter matrix.
3. Review the final target diff and staged changes. Complete the authorized local
   transfer with a commit following the repository's commit rules and preserving
   source commit references. Include only the intended transfer. If checks fail,
   fix issues within scope or leave a resumable record of the blocker.
4. Report source and target branches, source-to-target commit mapping, adaptations,
   exclusions and each check's result. Update the task record and archive it when
   complete. Do not push, tag, publish or transfer changes back to `main` unless
   separately authorized.
