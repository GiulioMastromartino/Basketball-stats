# Evolution API Integration — Basketball Stats

WhatsApp delivery via self-hosted `evoapicloud/evolution-api:v2.3.7`
(Baileys provider). Replaces the former OpenWA sidecar (see
`openwa-integration-plan.md`, deprecated). Free: Apache-2.0 community tier,
no per-message fees on the Baileys provider; v2.3.7 predates the (free)
license-activation requirement, so no phone-home.

## Parts

### 1. Stack (`docker-compose.prod.yml`)

- `evolution` service, image **pinned** to `v2.3.7` (never `:latest`):
  `SERVER_URL=http://evolution:8080`,
  `AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}`,
  `DATABASE_PROVIDER=postgresql`,
  `DATABASE_CONNECTION_URI=postgresql://${DB_USER}:${DB_PASSWORD}@db/${DB_NAME}?schema=evolution_api`
  (shares the app Postgres server; Prisma stays in its own schema).
- App env (`EVOLUTION_API_URL=http://evolution:8080`,
  `EVOLUTION_API_KEY=…`, `EVOLUTION_INSTANCE=basketball-bot`).
- No browser needed (WebSocket, not Puppeteer) — no `shm_size`/`SYS_ADMIN`.

### 1.1 One-time database bootstrap

```bash
docker compose -f docker-compose.prod.yml up -d db evolution
docker compose -f docker-compose.prod.yml exec evolution npm run db:deploy
```

### 1.2 Instance bootstrap (one time per number)

```bash
API=http://<host>:8081  # temporarily published port, see 1.3
KEY=$EVOLUTION_API_KEY
curl -X POST $API/instance/create \
  -H "apikey: $KEY" -H "Content-Type: application/json" \
  -d '{"instanceName":"basketball-bot","qrcode":true,"integration":"WHATSAPP-BAILEYS"}'
# → returns base64 QR; scan with the CLUB number
# (Settings → Linked Devices). Never a personal SIM.
curl -H "apikey: $KEY" $API/instance/connectionState/basketball-bot
# → {"instance":{"instanceName":"basketball-bot","state":"open"}}
```

### 1.3 Pairing without exposing the port publicly

Temporarily add `ports: ["127.0.0.1:8081:8080"]` to the `evolution`
service, `up -d evolution`, then SSH-tunnel from the Mac
(`ssh -L 8081:localhost:8081 <server>`) and run the 1.2 commands against
`http://localhost:8081`. Remove the port mapping and redeploy after
`state: open`. `scripts/deploy.sh` verifies the state on every deploy.

### 2. App transport (`core/services/whatsapp_service.py`)

Single adapter; routes dispatch through `notification_service.py`
unchanged. Endpoint map:

| App function | Evolution call |
|---|---|
| `send_text_message` | `POST /message/sendText/{instance}` `{"number","text"}` |
| `send_document` (halftime PDF) | `POST /message/sendMedia/{instance}` `{"number","mediatype":"document",…}` |
| `get_connection_state` | `GET /instance/connectionState/{instance}` → `open` |

`number` = digits with country code (no `+`) for DMs, full `…@g.us`
JID for groups (stored in `whatsapp_groups.group_wa_id`). Sends return
201; failures log and return `False` (never raise).

### 3. Ops

- Health: `GET /health/sync` reports `whatsapp: open|…` (informational);
  per-championship detail stays at `/analytics/championship/sync-health`.
- Ban hygiene: dedicated club number, a few messages per game max,
  OTP always has the email fallback (`notify_otp`), session persists in
  Postgres (survives restarts without re-pairing).
- Upgrade policy: pin every image bump; v2.4.0+ adds (free) license
  activation + 30-min heartbeat — evaluate before adopting.
