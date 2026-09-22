# Contributing to Pritunl Fleet

Thanks for your interest! This project is a control plane for **Pritunl OSS**,
and its whole design is built around one extension point — the `NodeAdapter` —
so contributions are especially welcome there.

## Development setup

```bash
git clone https://github.com/nguyencongnamit/pritunl-fleet.git
cd pritunl-fleet
cp .env.example .env
docker compose up -d --build     # control plane + Postgres + 2 mock nodes
./scripts/smoke_test.sh          # end-to-end check
```

- Backend: FastAPI in `control-plane/app` (Python 3.11+).
- Frontend: React + Vite + Tailwind in `frontend`.
- Shared HMAC + mock node: `pritunl-shim/`.

Run the backend locally without Docker:

```bash
cd control-plane && pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8200
```

Frontend dev server (proxies `/api` to the backend):

```bash
cd frontend && npm install && npm run dev
```

## Code style & checks

- Python: `ruff check` (config in `pyproject.toml`). Keep functions async where
  they touch a node adapter.
- TypeScript/React: keep components small; `npm run build` must pass.
- Please run these before opening a PR; CI runs them on every push and PR.

## Adding a NodeAdapter

The `NodeAdapter` ABC lives in `control-plane/app/adapters/base.py`. To add one:

1. Subclass `NodeAdapter`, set `adapter_type`, implement `health()` (required)
   and whatever read/mutation methods your access method supports (the rest stay
   `NotImplementedError` and surface as HTTP 501).
2. Register it in `adapters/factory.py`.
3. Document its **least-privilege** requirement and credential shape at the top
   of the file (see the `shim`, `mongo`, and `ssh` adapters for the pattern).

## Pull requests

- Branch from `main`, keep PRs focused, and describe the change + how you tested.
- Add/adjust tests where it makes sense; don't reformat files you didn't touch.
- Mutating features **must** write to the audit log and respect RBAC.

## Security

Never include real credentials in code, tests, issues, or PRs. Report
vulnerabilities privately — see [SECURITY.md](./SECURITY.md).

## Trademark

"Pritunl" is a trademark of its respective owner. This is an independent,
community project and is **not affiliated with or endorsed by** the Pritunl
project.
