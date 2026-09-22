#!/usr/bin/env bash
# Phase-1 smoke test: register the two lab nodes and run a health check on each.
# Requires the lab to be up:  docker compose up -d --build
# Usage:  ./scripts/smoke_test.sh
set -euo pipefail

CP="${CP:-http://localhost:8200}"
API="$CP/api/v1"

# Load node credentials from .env if present (else fall back to compose defaults).
if [[ -f .env ]]; then
  set -a; # shellcheck disable=SC1091
  source .env; set +a
fi
HCMC_TOKEN="${HCMC_TOKEN:-hcmc-token}"
HCMC_SECRET="${HCMC_SECRET:-hcmc-secret}"
SG_TOKEN="${SG_TOKEN:-sg-token}"
SG_SECRET="${SG_SECRET:-sg-secret}"

py() { python3 -c "$1" "${@:2}"; }

echo "==> Waiting for control plane at $CP ..."
for _ in $(seq 1 30); do
  if curl -fsS "$CP/healthz" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "$CP/healthz" >/dev/null || { echo "control plane not reachable"; exit 1; }
echo "    control plane is up."

echo "==> Available adapters:"
curl -fsS "$API/nodes/adapters"; echo

register_node() {
  local name="$1" region="$2" endpoint="$3" token="$4" secret="$5"
  local body
  body=$(py '
import json,sys
name,region,endpoint,token,secret=sys.argv[1:6]
print(json.dumps({
  "name":name,"region":region,"endpoint":endpoint,
  "adapter_type":"shim","verify_tls":False,
  "credentials":{"token":token,"secret":secret},
}))' "$name" "$region" "$endpoint" "$token" "$secret")

  local resp code json id
  resp=$(curl -sS -o - -w '\n%{http_code}' -H 'Content-Type: application/json' \
         -d "$body" "$API/nodes")
  code=$(printf '%s' "$resp" | tail -n1)
  json=$(printf '%s' "$resp" | sed '$d')

  if [[ "$code" == "201" ]]; then
    id=$(printf '%s' "$json" | py 'import json,sys;print(json.load(sys.stdin)["id"])')
    echo "    registered $name -> $id" >&2
  elif [[ "$code" == "409" ]]; then
    id=$(curl -fsS "$API/nodes" | py "import json,sys;print(next(n['id'] for n in json.load(sys.stdin) if n['name']=='$name'))")
    echo "    $name already registered -> $id" >&2
  else
    echo "    FAILED to register $name (HTTP $code): $json" >&2; exit 1
  fi
  printf '%s' "$id"
}

echo "==> Registering nodes ..."
HCMC_ID=$(register_node "hcmc-1" "HCMC" "http://node-hcmc:9700" "$HCMC_TOKEN" "$HCMC_SECRET")
SG_ID=$(register_node   "sg-1"   "SG"   "http://node-sg:9700"   "$SG_TOKEN"   "$SG_SECRET")

check_node() {
  local id="$1"
  curl -fsS -X POST "$API/nodes/$id/check" | py '
import json,sys
d=json.load(sys.stdin)
print("    status=%-10s latency=%sms  detail=%s  error=%s" % (d["status"], d.get("latency_ms"), d.get("detail"), d.get("error")))'
}

echo "==> Health check: hcmc-1"
check_node "$HCMC_ID"
echo "==> Health check: sg-1"
check_node "$SG_ID"

echo "==> Registry snapshot:"
curl -fsS "$API/nodes" | py '
import json,sys
for n in json.load(sys.stdin):
    print("    %-6s %-10s %-6s status=%-10s latency=%sms" % (n["region"], n["name"], n["adapter_type"], n["status"], n.get("last_latency_ms")))'

echo "==> Smoke test complete."
