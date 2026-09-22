## What & why

Describe the change and the motivation.

## How tested

- [ ] `ruff check` + `python -m compileall` pass
- [ ] `npm run build` passes (if frontend touched)
- [ ] `docker compose up` + `./scripts/smoke_test.sh` (if runtime touched)

## Checklist

- [ ] Mutating actions write to the audit log and respect RBAC
- [ ] No secrets in code, tests, or fixtures
- [ ] Did not reformat unrelated files
- [ ] Docs updated if behavior changed
