# Git Flow

Start new work on a temporary `codex/<issue-id>-<slug>` branch from the current
GitHub `main`. Open a pull request against `main` for review. For an existing
stack, target the active milestone branch named in its governing issue.

Do not merge product implementation work directly to main. Every product change
needs an issue branch, review pass, validation evidence, and handoff comment.

Do not rewrite shared history. Do not force-push shared branches.

Issue branches should be deleted after merge unless a handoff explicitly keeps
one around for a follow-up.
