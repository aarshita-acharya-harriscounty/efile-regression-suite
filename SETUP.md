# One-time setup — self-hosted runner + branch protection

**Deferred for now (2026-10-14).** Until section 1 is done, `.github/workflows/regression.yml`
exists but has no runner to execute it — pushes and PRs will show the check as permanently
queued, not passing or failing. That's expected, not a bug. **In the meantime, the local
pre-push hook (see `README.md` "Enable the pre-push gate") is what actually enforces
TESTING_RULES.md rule 10** — it runs the full suite before anything leaves this machine,
no GitHub infra required. Do sections 1-2 below whenever ready; nothing about them is urgent.

Both steps below are manual, one-time, and done from the GitHub web UI / this machine. Neither
is something that can be scripted from here without repo-admin credentials.

## 1. Register this machine as a self-hosted runner

GitHub's own cloud runners cannot reach `SVTUSLAWBASESQL` or Tyler's internal Design
endpoints, so CI has to run on a machine that already has that access — this one.

1. On GitHub: repo **Settings → Actions → Runners → New self-hosted runner**, choose Windows.
2. Follow the generated download/config commands exactly as shown (they embed a one-time
   registration token) — install into a separate folder, e.g. `C:\actions-runner\`, not
   inside this repo.
3. Run `config.cmd` with the URL/token it gives you, then either:
   - `run.cmd` to run it in the foreground for a quick test, or
   - `svc install` + `svc start` to run it as a Windows service so CI keeps working even
     after you log out (recommended, since CI runs on every PR, per `TESTING_RULES.md`
     rule 10).
4. Confirm it shows "Idle" under Settings → Actions → Runners before relying on it.

**Caveat you already know:** CI only runs while this machine is on and the runner service is
running. If it's off, PRs sit at "pending," not "failed" — nothing merges silently without
the check having actually run, but a stuck PR with no obvious reason is the symptom to
recognize.

## 2. Require the check before merge

1. Repo **Settings → Branches → Add branch protection rule**, pattern `main`.
2. Enable **"Require status checks to pass before merging"**, then search for and select
   `regression-suite` (the job name in `.github/workflows/regression.yml`) once it's run at
   least once (GitHub only lists checks that have executed before).
3. Also enable **"Require a pull request before merging"** so nothing lands on `main`
   without going through the check at all.
4. Leave **"Include administrators"** checked — the rule should apply to you too, not just
   hypothetical other contributors.
