# AGENTS

## Branching

Before implementing a new feature or change, check whether the current
branch is related to the work being asked for. If the branch looks
unrelated (e.g. its name or history is about something else), do NOT start
coding on it — ask to create a new branch from `origin/main` first, and
continue the work there.

## Merging

Main uses squash merges: each PR lands as one commit on main regardless of
how many commits the branch has. That is not a "one commit per PR" style —
feel free to commit per logical step on the branch; they all get squashed
into the PR's single main commit on merge.
