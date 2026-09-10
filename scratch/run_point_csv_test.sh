#!/usr/bin/env bash
set -e

PORT=9285
google-chrome --headless --remote-debugging-port=$PORT --no-sandbox --disable-gpu about:blank &
CHROME_PID=$!

cleanup() {
  kill $CHROME_PID 2>/dev/null || true
}
trap cleanup EXIT

for i in {1..30}; do
  if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null; then
    break
  fi
  sleep 0.1
done

CDP_PORT=$PORT node scratch/test_point_csv_cleaning_e2e.mjs
