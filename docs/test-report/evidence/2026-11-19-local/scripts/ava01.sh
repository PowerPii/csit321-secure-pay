#!/bin/bash
# M-AVA-01 on the disposable local stack: 5 hard crashes of the gateway under steady traffic.
set -u
cd /home/user/csit321-secure-pay
export NO_PROXY="$NO_PROXY,.localhost,gateway.localhost" no_proxy="$no_proxy,.localhost,gateway.localhost"
P="docker compose -p nfr -f deploy/compose.yaml -f /tmp/claude-0/override.yaml"
OUT=/tmp/claude-0/ev/ava01
mkdir -p $OUT
q() { $P exec -T db psql -U postgres -d "$1" -At -c "$2"; }
echo "before gateway_authorise_ops=$(q gateway "SELECT count(*) FROM payments_operation WHERE type='authorise'") sim_authorise_ops=$(q simulator "SELECT count(*) FROM operations_operation WHERE type='authorise'")" > $OUT/kills.txt
/tmp/claude-0/venv-it/bin/python tests/load/checkout_load.py --gateway https://gateway.localhost --key-file deploy/secrets/securepay_api_key \
  --ca-bundle /tmp/claude-0/caddy-root.crt --rate 2 --seconds 540 --out $OUT/load.json > $OUT/load.txt 2>&1 &
LOAD=$!
for i in 1 2 3 4 5; do
  sleep 90
  pid=$(docker inspect -f '{{.State.Pid}}' "$($P ps -q gateway)")
  t0=$(date +%s.%N); kill -9 "$pid"
  echo "kill $i at $(date -u +%T) pid=$pid" >> $OUT/kills.txt
  sleep 0.2
  until curl -fsS --cacert /tmp/claude-0/caddy-root.crt https://gateway.localhost/readyz >/dev/null 2>&1; do sleep 0.25; done
  t1=$(date +%s.%N)
  echo "  back after $(python3 -c "print(round($t1-$t0,1))") s; restarts=$(docker inspect -f '{{.RestartCount}}' "$($P ps -q gateway)")" >> $OUT/kills.txt
done
wait $LOAD
echo "load exit $?" >> $OUT/kills.txt
echo DONE >> $OUT/kills.txt
