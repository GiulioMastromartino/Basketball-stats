# Archive — frozen history, do not treat as current docs

These files are preserved design notes, plans, and migration logs. They are
**not** part of the published site nav (`mkdocs.yml`) and many contradict the
current implementation. Source of truth is `docs/index.md`,
`docs/user-guide/*`, and `docs/technical/*`.

Known-stale examples (not exhaustive):

- `POSTGRES_MIGRATION.md` / `POSTGRES_BOOTSTRAP.md` / `IMPLEMENTATION_STATUS.md` —
  predate the current scheme (`db.create_all()` on boot + `core/db_migrations`
  auto-migrate; `migrations/versions/` intentionally empty, `legacy_migrations/`
  frozen read-only).
- `PLAYS_SETUP.md` / `PLAYS_QUICK_START.md` / `feature_plays.md` /
  `PLAYS_BASED_IMPLEMENTATION_PLAN.md` — predate the current playbook
  (Offense/Defense/Special types seeded, plays user-created; no 65+ bundle).
- `PDF_EXPORTS_GUIDE.md` / `PDF_FEATURE_SUMMARY.md` / `PDF_INTEGRATION_TODO.md` —
  superseded by `docs/user-guide/pdf-exports.md`.
- `DEPLOYMENT_GUIDE.md` — superseded by `docs/technical/deployment.md`
  (dev: db/web/scraper/cloudflared; prod: + redis/evolution/migrator/web-1/2/3/nginx/observability).
- `evolution-integration-plan.md` / `openwa-integration-plan.md` — historical;
  current runbook is the WhatsApp section of `docs/technical/deployment.md`
  (Evolution API v2.3.7 sidecar named `evolution`).
- `TESTING_REPORT.md` / `FIXES_APPLIED.md` / `CSRF_FIX.md` /
  `ROUTE_INVENTORY.md` / `COMMIT_MESSAGE.md` / `LineupImprovemt.md` /
  `play-selector-implementation.md` — point-in-time notes, not guides.
