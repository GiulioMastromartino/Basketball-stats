# Sharing & Post-Game Comms

Get the result out of the app: expiring public links, 1080×1080 social cards, one-tap message templates, and timestamped video exports.

---

## Public Share Links

Every game and player page has a **Share** box (expiry dropdown + Share button + Copy). It calls:

```
POST /share     {"target_type": "game"|"player", "target_id": <int>, "expires_in_days": 7}
```

- `expires_in_days`: 1–30, default `7` (`DEFAULT_EXPIRY_DAYS` / `MAX_EXPIRY_DAYS` in `web/routes/share.py`).
- Response: `{"id", "token", "url", "target_type", "target_id", "expires_at"}`.
- Creating links is GM/coach-only (`403` for auditors).

The link opens a **public, login-free JSON view**:

```
GET /s/<token>        404 when unknown, expired, or revoked
```

Revoke anytime (GM/coach-only):

```
DELETE /share/<id>
```

---

## Social PNG Cards

1080×1080 graphics rendered server-side with Pillow — sized for WhatsApp and socials, generated alongside the PDFs:

| Card | Endpoint |
|------|----------|
| Final-score card | `GET /share/cards/game/<game_id>` |
| Player-of-the-game card (best scoring game) | `GET /share/cards/player/<player_id>` |

Targets are scoped to your team (`404` for other teams' games/players).

---

## Post-Game Message Templates

`{{merge_tag}}` templates for staff, parents, and fans (`core/comms_templates.py`). Rendering is pure string substitution — unknown tags are left in place so a typo stays visible instead of silently dropping.

```
POST /share/comms-preview
{"template": "postgame_whatsapp"|"postgame_email_subject"|"postgame_email_body"|"parent_digest",
 "game_id": <int>}
```

| Template | Shape |
|----------|-------|
| `postgame_whatsapp` | `🏀 *{{team}} {{result}} {{opponent}} ({{score}})*` + date, top scorer, hub pointer |
| `postgame_email_subject` | `[{{team}}] {{result}} vs {{opponent}} ({{score}})` |
| `postgame_email_body` | Full final + top scorer + hub pointer, signed HoopsLab |
| `parent_digest` | Weekly digest: games, W-L, top scorer PPG |

Known tags: `team`, `opponent`, `score`, `result`, `date`, `top_scorer`, `top_points`, `games_played`, `wins`, `losses`.

---

## Halftime One-Tap Share

From the `/live-v2` console, **✉ HT SHARE** posts the live state to:

```
POST /reports/live/halftime-share
```

Same payload as `POST /reports/live/halftime-pdf`, plus `group_id` (a `WhatsAppGroup` id for the session team) or `phone`. It texts the staff WhatsApp group via the Evolution API gateway (optional `pdf_base64` + `pdf_filename` attaches the rendered halftime PDF). With no destination it returns the text for manual copy (`{"sent": false, …}`) — the page never breaks. Auditors get `403`. Without a configured/paired gateway, sends log a warning and return `false` (OTP falls back to email when no phone is on file). See [Live Game Tracking](live-game.md) and the WhatsApp runbook in [Deployment](../technical/deployment.md).

---

## Video Timestamp Export

No video is hosted here — this is the timestamped event log you sync against clips in Veo/Pixellot, matched by quarter + game clock:

```
GET /api/v1/games/<game_id>/video-export?format=json    (default)
GET /api/v1/games/<game_id>/video-export?format=csv
```

Rows carry `quarter`, `game_seconds`, `timestamp`, `type`, `player`, `points`, `x`/`y`, `detail`, ordered by quarter then clock, covering both `GameEvent` and `ShotEvent` rows.

---

## Related

- [PDF Exports](pdf-exports.md) — cards are generated alongside these reports
- [Live Game Tracking](live-game.md) — halftime share flow
- [API Reference](../technical/api.md) — full endpoint reference
