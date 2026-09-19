#!/usr/bin/env bash
# Disposable GitHub CI container only. No application credentials are used.
set -euo pipefail
name=dudri-runtime-check
if docker inspect "$name" >/dev/null 2>&1; then
  echo 'The test container name is already in use.' >&2
  exit 1
fi
docker run -d --name "$name" --network host --memory=512m --cpus=0.1 --pids-limit=256 \
  -e DUDRI_SERVICE_ROLE=api \
  -e DUDRI_DATABASE_URL=postgresql://postgres:disposable_ci_fixture@127.0.0.1:5432/dudri_ci \
  -e DUDRI_APP_ORIGIN=https://app.example \
  -e DUDRI_SITE_ORIGIN=https://sites.example \
  -e DUDRI_CREDENTIAL_ENCRYPTION_KEY=fixture-only \
  -e DUDRI_SMTP_HOST=smtp.example.invalid \
  -e DUDRI_SMTP_SENDER=fixture@example.invalid \
  dudri-production
trap 'docker logs "$name"; docker rm -f "$name" >/dev/null' EXIT
ready=false
for attempt in {1..90}; do
  if curl -fsS http://127.0.0.1:10000/api/v1/health >/dev/null; then
    ready=true
    break
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$name")" != true ]; then
    exit 1
  fi
  sleep 1
done
test "$ready" = true
docker exec -i -w /app/backend "$name" python - <<'PY'
import httpx
from app.design_upload import reference_images

assert httpx.get('http://127.0.0.1:10000/api/v1/health').json()['database'] == 'ok'
assert httpx.get('http://127.0.0.1:10000/api/v1/me').status_code == 401
assert httpx.get('http://127.0.0.1:10000/api/v1/dev/accounts').status_code == 404
images = reference_images({'html': '<h1>Free runtime reference</h1>', 'css': 'body{font-family:sans-serif}', 'javascript': ''})
assert all(images[key].startswith('data:image/png;base64,') for key in ('reference_image', 'mobile_reference_image'))
assert httpx.get('http://127.0.0.1:10000/api/v1/health').json()['database'] == 'ok'
print('PASS: API, worker and two browser screenshots under 512 MB / 0.1 CPU; production auth boundary intact.')
PY
test "$(docker inspect -f '{{.State.OOMKilled}}' "$name")" = false
