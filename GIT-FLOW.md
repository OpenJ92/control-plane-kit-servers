# Git Flow

Branches:

- `main`: reviewed foundation and product work.
- `develop`: available for release-flow staging once the repository has package
  and CI policy.
- `codex/<issue-id>-<slug>`: issue implementation branches.

Pull requests target the active milestone branch or main as directed by the
issue. During #649-#653, PRs target `main` unless a later policy issue creates a
dedicated roadmap branch inside this repository.

Do not merge product implementation work directly to main. Every product change
needs an issue branch, review pass, validation evidence, and handoff comment.

Do not rewrite `main` or `develop`. Do not force-push shared branches.

Issue branches should be deleted after merge unless a handoff explicitly keeps
one around for a follow-up.
