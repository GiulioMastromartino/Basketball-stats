# OpenWA Integration Plan — Basketball Stats

Complete end-to-end guide for integrating OpenWA (WhatsApp Gateway) into the Basketball Stats Flask application running on Ubuntu Server, with per-user channel selection between email and WhatsApp (individual or group).

---

## Overview

The integration adds OpenWA as a Docker sidecar service inside the existing `docker-compose.prod.yml` stack. A new `notification_service.py` dispatcher wraps the existing `email_service.py` and a new `whatsapp_service.py`, routing each notification through email, personal WhatsApp, a WhatsApp group, or any combination — based on a per-user/per-player preference stored in PostgreSQL.

**Affected files summary:**

| File | Action |
|---|---|
| `docker-compose.prod.yml` | Add `openwa` service + volumes |
| `.env.prod` / `.env.example` | Add 3 OpenWA env vars |
| `config.py` | Read new env vars |
| `core/models.py` | Add `WhatsAppGroup` model + columns on `User`/`Player` + `Team.whatsapp_groups` relationship |
| `init_db.py` | Add `add_notification_columns()` migration function |
| `scripts/migrate.py` | Call `add_notification_columns()` in the migration sequence |
| `core/services/whatsapp_service.py` | New — OpenWA adapter |
| `core/services/notification_service.py` | New — dispatcher |
| `core/services/email_service.py` | No changes required |
| `web/routes/main.py` | Refactor `_notify_users_game_saved()` to pass model instances through `notification_service` |
| `web/routes/auth.py` | Swap OTP import to `notify_otp`; add group management route |
| `web/templates/auth/admin.html` | Add channel preference form; add WhatsApp Groups nav link |
| `web/templates/admin/whatsapp_groups.html` | New — group management UI |
| `requirements.txt` | Add `httpx` |

---

## Part 1 — Docker Setup

### 1.1 Ubuntu Server Prerequisites

OpenWA runs Chromium headless internally. On a server without a display, two things are critical: enough shared memory (`shm_size`) and the `SYS_ADMIN` capability for the Chromium sandbox.

Verify Docker and Compose versions on the server:

```bash
docker --version        # >= 24.0 recommended
docker compose version  # >= 2.20 recommended
```

Install `httpx` in the app container (required by `whatsapp_service.py`):

```bash
# Add to requirements.txt
httpx==0.27.0
```

### 1.2 `docker-compose.prod.yml` — add OpenWA service

Insert the following block after the `redis:` service definition. It joins the existing `backend` network, so all three `web_*` replicas can reach it at `http://openwa:3000` without any port exposure to the host.

```yaml
  # ── OpenWA WhatsApp Gateway ──────────────────────────────────────────────
  openwa:
    image: ghcr.io/rmyndharis/openwa:latest
    restart: unless-stopped
    shm_size: '256mb'        # Chromium crashes with the default 64 MB on headless servers
    cap_add:
      - SYS_ADMIN            # Required for Chromium sandbox inside Docker
    environment:
      API_KEY: ${OPENWA_API_KEY}
    volumes:
      - openwa_data:/app/.wwebjs_auth    # persists WA session — survives restarts
      - openwa_cache:/app/.wwebjs_cache
    networks:
      - backend
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s      # Chromium needs ~30-60 s to boot on first run
```

Add to the `volumes:` block at the bottom of the file:

```yaml
  openwa_data:
  openwa_cache:
```

Add `openwa` as a dependency to each `web_*` replica so they wait for the health check:

```yaml
  web_1:
    depends_on:
      migrator:
        condition: service_completed_successfully
      openwa:
        condition: service_healthy   # add this line
```

Repeat for `web_2` and `web_3`.

> **Note:** The `migrator` service does NOT need `openwa` — it only runs DB migrations and never sends messages.

### 1.3 First-Run: QR Code Pairing

On first startup, OpenWA needs a WhatsApp account to be paired by scanning a QR code. Since the server is headless, retrieve the QR from your Mac via the server's local IP (or Tailscale IP).

**Step 1 — temporarily expose port 3000** (remove after pairing):

```yaml
  openwa:
    ports:
      - "3000:3000"   # LAN-accessible — remove after QR scan
```

**Step 2 — start only OpenWA first:**

```bash
docker compose -f docker-compose.prod.yml up -d openwa
```

**Step 3 — from your Mac, poll until the session is ready to scan:**

```bash
SERVER=192.168.x.x        # or 100.x.x.x for Tailscale
KEY=your-openwa-api-key

# Create and start the session
curl -s -X POST http://$SERVER:3000/api/sessions \
  -H "x-api-key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "basketball-bot", "start": true}'

# Poll status (~10-15 s until SCAN_QR_CODE)
watch -n 3 "curl -s http://$SERVER:3000/api/sessions/basketball-bot \
  -H 'x-api-key: $KEY' | jq .status"

# Once status == "SCAN_QR_CODE" — fetch QR as PNG and open
curl -s http://$SERVER:3000/api/sessions/basketball-bot/qr \
  -H "x-api-key: $KEY" -o /tmp/wa_qr.png && open /tmp/wa_qr.png
```

Scan with WhatsApp on the paired phone. Status will change to `WORKING`.

**Step 4 — remove the `ports:` block** from `openwa` in `docker-compose.prod.yml`, then redeploy:

```bash
docker compose -f docker-compose.prod.yml up -d
```

The session persists in the `openwa_data` volume. Re-pairing is only needed if the session is invalidated (phone inactive 14+ days, manual logout, or WhatsApp ban).

> **Important:** Use a dedicated secondary number, not your personal WhatsApp. This avoids accidental bans and keeps the bot account isolated.

### 1.4 Discover Group IDs

If sending to WhatsApp groups, the group's internal ID must be fetched once and stored in the DB.

```bash
# List all chats — filter for groups (@g.us suffix)
curl -s http://$SERVER:3000/api/sessions/basketball-bot/chats \
  -H "x-api-key: $KEY" \
  | jq '.[] | select(.id | endswith("@g.us")) | {id, name}'
```

Example output:

```json
{ "id": "120363025321123456@g.us", "name": "Team Ostia 🏀" }
```

Save the `id` value — it is entered into the admin UI in Part 4.

---

## Part 2 — Environment & Config

### 2.1 `.env.prod` additions

```bash
# OpenWA WhatsApp Gateway
OPENWA_API_URL=http://openwa:3000/api
OPENWA_API_KEY=change-me-strong-random-key-here
OPENWA_SESSION_ID=basketball-bot
```

Mirror the same keys in `.env.example` with placeholder values.

### 2.2 `config.py` additions

Add inside the `Config` class:

```python
OPENWA_API_URL    = os.environ.get("OPENWA_API_URL", "")
OPENWA_API_KEY    = os.environ.get("OPENWA_API_KEY", "")
OPENWA_SESSION_ID = os.environ.get("OPENWA_SESSION_ID", "basketball-bot")
```

---

## Part 3 — Database Migrations

The project uses `scripts/migrate.py` as its production migration entry point (via the `migrator` Docker service). The migration is a two-step process:

1. **Add the `WhatsAppGroup` model** to `core/models.py` so `db.create_all()` can create the table.
2. **Add an `add_notification_columns()` function** to `init_db.py` (following the existing `add_missing_columns` pattern) and call it from `scripts/migrate.py`.

### 3.1 `core/models.py` — add `WhatsAppGroup` model and columns

Add new columns to the `User` model (after line 70, `otp_expiry`):

```python
    notification_channel = db.Column(
        db.String(20), nullable=False, default="email",
        server_default="email"
    )
    whatsapp_phone = db.Column(db.String(20), nullable=True)
```

Add new columns to the `Player` model (after line 413, `active`):

```python
    notification_channel = db.Column(
        db.String(20), nullable=False, default="email",
        server_default="email"
    )
    whatsapp_phone = db.Column(db.String(20), nullable=True)
```

Add the WhatsAppGroup model **before the `Player` model** (or anywhere in the file):

```python
class WhatsAppGroup(db.Model):
    __tablename__ = "whatsapp_groups"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    group_name = db.Column(db.String(100), nullable=False)
    group_wa_id = db.Column(db.String(50), nullable=False)   # e.g. 120363XXX@g.us
    active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    team = db.relationship("Team", backref=db.backref("whatsapp_groups", lazy=True))
```

After adding the `Team` class (which already exists), **add the relationship** on the Team model. The Team model currently has no relationships beyond `players` and `games`. Add this inside the `Team` class (after `__table_args__` on line 30):

```python
    whatsapp_groups = db.relationship("WhatsAppGroup", backref="team_ref", lazy=True)
```

> **Alternative:** Since we defined the `team` backref on `WhatsAppGroup`, the `Team` model already gets `whatsapp_groups` through that backref. No explicit relationship is needed on `Team` — just ensure the `WhatsAppGroup` model is defined before it's used.

### 3.2 `init_db.py` — add migration function

Create a new file `init_db.py` (if it doesn't exist already) or append to the existing one. Follow the existing pattern used in `add_missing_columns`:

```python
def add_notification_columns(app):
    """Add notification channel columns to users and players tables.

    Safe to re-run — uses IF NOT EXISTS style checks.
    """
    from core.models import db
    from sqlalchemy import inspect, text

    engine = db.engine

    # ── users table ──────────────────────────────────────────────────────
    inspector = inspect(engine)
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "notification_channel" not in user_cols:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN notification_channel VARCHAR(20)
                    NOT NULL DEFAULT 'email'
            """))
            conn.commit()
    if "whatsapp_phone" not in user_cols:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN whatsapp_phone VARCHAR(20) DEFAULT NULL
            """))
            conn.commit()

    # ── players table ────────────────────────────────────────────────────
    player_cols = {c["name"] for c in inspector.get_columns("players")}
    if "notification_channel" not in player_cols:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE players
                ADD COLUMN notification_channel VARCHAR(20)
                    NOT NULL DEFAULT 'email'
            """))
            conn.commit()
    if "whatsapp_phone" not in player_cols:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE players
                ADD COLUMN whatsapp_phone VARCHAR(20) DEFAULT NULL
            """))
            conn.commit()

    # ── whatsapp_groups table — created by db.create_all() via the model ──
    # No RAW SQL needed — the WhatsAppGroup model handles it.
```

### 3.3 `scripts/migrate.py` — call the new function

In the `run()` function, after the existing `add_missing_columns(app)` call (around line 63), add:

```python
        print("[migrate] Adding notification columns...")
        try:
            add_notification_columns(app)
            print("[migrate] Notification columns added successfully.")
        except Exception as e:
            print(f"[migrate] Warning: add_notification_columns failed: {e}")
```

Import at the top:

```python
from init_db import add_missing_columns, add_notification_columns
```

**Channel option semantics:**

| Value | Email | Personal WA | Group WA |
|---|---|---|---|
| `email` | ✅ | ❌ | ❌ |
| `whatsapp` | ❌ | ✅ | ❌ |
| `whatsapp_group` | ❌ | ❌ | ✅ |
| `both` | ✅ | ✅ | ❌ |
| `all` | ✅ | ✅ | ✅ |

> `VARCHAR(20)` is used (not 15) because `whatsapp_group` is 14 characters — `VARCHAR(15)` would work but is uncomfortably tight.

**Global toggle vs per-user preference interaction:**

The existing system has global toggles (`notify_game_added`, `send_player_reports`, `attach_game_pdf`) in the `system_settings` table. The per-user `notification_channel` selects **how** to deliver, but the global toggles control **whether** to deliver at all. The logic in `_notify_users_game_saved()` checks the global toggle first, then routes through the notification_service for channel selection.

---

## Part 4 — Python Services

### 4.1 `core/services/whatsapp_service.py` (new file)

Mirrors `email_service.py` function signatures exactly so the dispatcher can call either transparently.

```python
import httpx
from flask import current_app


# ── Internal helpers ─────────────────────────────────────────────────────────

def _client():
    return httpx.Client(
        base_url=current_app.config["OPENWA_API_URL"],
        headers={"x-api-key": current_app.config["OPENWA_API_KEY"]},
        timeout=10,
    )


def _session() -> str:
    return current_app.config["OPENWA_SESSION_ID"]


def _chat_id(phone: str) -> str:
    """Individual: strip + and spaces, append @c.us"""
    return f"{phone.lstrip('+').replace(' ', '')}@c.us"


def _group_chat_id(group_wa_id: str) -> str:
    """Group ID already includes @g.us as stored in DB."""
    return group_wa_id


def _send(chat_id: str, text: str, label: str = "") -> bool:
    try:
        with _client() as c:
            r = c.post(
                f"/sessions/{_session()}/messages/text",
                json={"chatId": chat_id, "contentText": text},
            )
            r.raise_for_status()
            current_app.logger.info(f"WhatsApp sent to {label or chat_id}")
            return True
    except httpx.HTTPError as e:
        current_app.logger.error(f"WhatsApp send failed to {label or chat_id}: {e}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def send_game_notification(phones: list, game, pdf_attachment=None) -> None:
    """Mirrors email_service.send_game_notification(). pdf_attachment ignored."""
    text = (
        f"🏀 *New Game Added*\n"
        f"Opponent: {game.opponent}\n"
        f"Date: {game.date}\n"
        f"Result: {game.result} ({game.score_display})\n"
        f"Type: {game.game_type}\n\n"
        f"Log in to view full details."
    )
    for phone in phones:
        _send(_chat_id(phone), text, label=phone)


def send_game_notification_to_group(group_wa_id: str, game) -> bool:
    text = (
        f"🏀 *New Game Added*\n"
        f"Opponent: {game.opponent}\n"
        f"Date: {game.date}\n"
        f"Result: {game.result} ({game.score_display})\n"
        f"Type: {game.game_type}\n\n"
        f"Log in to view full details."
    )
    return _send(_group_chat_id(group_wa_id), text, label=f"group:{group_wa_id}")


def send_player_performance_whatsapp(
    player_phone: str, player_name: str, game, game_stats: dict, season_avg: dict
) -> bool:
    """Mirrors email_service.send_player_performance_email()."""
    if not player_phone:
        current_app.logger.warning(f"No WhatsApp phone for player {player_name}")
        return False

    def diff(a, b):
        return f"{(a - b):+.1f}"

    def pct(v):
        return f"{v:.1f}%"

    g, s = game_stats, season_avg
    text = (
        f"📊 *Performance Report*\n"
        f"{player_name} vs {game.opponent} ({game.date})\n"
        f"Result: {game.result}\n\n"
        f"*This Game*\n"
        f"PTS {g.get('points',0)} | REB {g.get('reb',0)} | "
        f"AST {g.get('ast',0)} | STL {g.get('stl',0)} | BLK {g.get('blk',0)}\n"
        f"FG {pct(g.get('fg_percent',0))} | "
        f"3PT {pct(g.get('tp_percent',0))} | "
        f"FT {pct(g.get('ft_percent',0))}\n\n"
        f"*vs Season Avg*\n"
        f"PTS {diff(g.get('points',0), s.get('points',0))} | "
        f"REB {diff(g.get('reb',0), s.get('reb',0))} | "
        f"AST {diff(g.get('ast',0), s.get('ast',0))}\n"
        f"FG% {diff(g.get('fg_percent',0), s.get('fg_percent',0))} | "
        f"3PT% {diff(g.get('tp_percent',0), s.get('tp_percent',0))}"
    )
    return _send(_chat_id(player_phone), text, label=player_phone)


def send_otp_whatsapp(phone: str, otp_code: str) -> bool:
    """Mirrors email_service.send_otp_email()."""
    text = (
        f"🔐 *Basketball Stats Login*\n"
        f"Your verification code is: *{otp_code}*\n\n"
        f"This code expires in 5 minutes."
    )
    return _send(_chat_id(phone), text, label=phone)
```

### 4.2 `core/services/notification_service.py` (new file)

The single call point. Callers import from here instead of directly from `email_service`.

```python
from core.services import email_service, whatsapp_service


def _channel(recipient) -> str:
    """Resolve channel from model instance or plain string."""
    if isinstance(recipient, str):
        return "email"
    return getattr(recipient, "notification_channel", "email")


# ── Public API ────────────────────────────────────────────────────────────────

def notify_game(recipients, game, pdf_attachment=None, team=None) -> None:
    """
    Drop-in replacement for email_service.send_game_notification().

    recipients : list of User/Player model instances (NOT email strings)
                 Each instance must have .notification_channel, .email,
                 and optionally .whatsapp_phone attributes.
    team       : Team model instance (needed to resolve group IDs).
                 Must have .whatsapp_groups relationship loaded.
    """
    emails, phones, groups_notified = [], [], set()

    for r in recipients:
        ch = _channel(r)
        if ch in ("email", "both", "all") and getattr(r, "email", None):
            emails.append(r.email)
        if ch in ("whatsapp", "both", "all") and getattr(r, "whatsapp_phone", None):
            phones.append(r.whatsapp_phone)
        if ch in ("whatsapp_group", "all") and team:
            for group in team.whatsapp_groups:
                if group.active:
                    groups_notified.add(group.group_wa_id)

    if emails:
        email_service.send_game_notification(emails, game, pdf_attachment)
    if phones:
        whatsapp_service.send_game_notification(phones, game)
    for group_id in groups_notified:   # send once per group, not once per recipient
        whatsapp_service.send_game_notification_to_group(group_id, game)


def notify_player_performance(
    recipient, player_name: str, game, game_stats: dict, season_avg: dict
) -> bool:
    """
    Drop-in for email_service.send_player_performance_email().

    recipient : User or Player model instance
    """
    ch = _channel(recipient)
    results = []
    if ch in ("email", "both", "all"):
        results.append(email_service.send_player_performance_email(
            getattr(recipient, "email", None),
            player_name, game, game_stats, season_avg,
        ))
    if ch in ("whatsapp", "both", "all"):
        results.append(whatsapp_service.send_player_performance_whatsapp(
            getattr(recipient, "whatsapp_phone", None),
            player_name, game, game_stats, season_avg,
        ))
    return all(results) if results else False


def notify_otp(
    recipient_email: str, otp_code: str, whatsapp_phone: str = None
) -> bool:
    """
    OTP routing: WhatsApp if phone is provided, email otherwise.
    Does not send both — OTP should arrive on one channel only.
    """
    if whatsapp_phone:
        return whatsapp_service.send_otp_whatsapp(whatsapp_phone, otp_code)
    return email_service.send_otp_email(recipient_email, otp_code)
```

### 4.3 `core/services/__init__.py` — no changes needed

The current `__init__.py` exports specific classes:

```python
from .analytics_service import AnalyticsService
from .game_service import create_game_from_live_data, validate_play_id
```

The new `whatsapp_service.py` and `notification_service.py` files will be importable directly without modifying `__init__.py`. All callers should use explicit imports:

```python
# Correct — no __init__.py change required
from core.services.notification_service import notify_game
from core.services.whatsapp_service import send_otp_whatsapp
```

### 4.4 Update call sites — full refactoring

#### 4.4.1 `web/routes/main.py` — `_notify_users_game_saved()` rewrite

This is the most critical change. The current function passes email **strings** to `send_game_notification`, and sends player performance emails directly via raw `mail.send()`. Both must be refactored to pass model instances through `notification_service`.

Replace the import at line 68:

```python
# Before
from core.services.email_service import send_game_notification

# After
from core.services.notification_service import notify_game, notify_player_performance
```

Replace the entire `_notify_users_game_saved()` function (lines 245-341):

```python
def _notify_users_game_saved(game: Game):
    """Notify users/players that a game was saved, routing through notification_service."""
    try:
        # ── Game-addition notifications to users ──────────────────────────
        enabled = SystemSetting.get_value("notify_game_added", default="false")
        if enabled == "true":
            non_gm_users = User.query.filter(User.id.notin_(
                db.session.query(OrganizationMembership.user_id).filter_by(is_gm=True)
            )).all()

            if non_gm_users:
                pdf_attachment = None
                attach_pdf = SystemSetting.get_value("attach_game_pdf", default="false")
                if attach_pdf == "true":
                    try:
                        from core.pdf_exports import PlaysBasedPDFGenerator
                        generator = PlaysBasedPDFGenerator()
                        pdf_buffer = generator.generate_game_report_pdf(game.id)

                        pdf_bytes = pdf_buffer.getvalue()
                        filename = f"Game_Report_{game.opponent.replace(' ', '_')}_{game.date}.pdf"

                        if pdf_bytes:
                            pdf_attachment = (filename, pdf_bytes)
                    except Exception as e:
                        current_app.logger.error(
                            f"Failed to generate professional game PDF for email (Game ID {game.id}): {e}"
                        )

                # Pass User model instances + team for group routing
                notify_game(non_gm_users, game, pdf_attachment=pdf_attachment, team=game.team)

        # ── Player performance reports ────────────────────────────────────
        send_player_reports = SystemSetting.get_value(
            "send_player_reports", default="true"
        )
        if send_player_reports == "true":
            from core.services.report_service import generate_player_quarter_pdf_bytes

            players = Player.query.filter_by(active=True).all()
            for player in players:
                game_stat = PlayerStat.query.filter_by(
                    game_id=game.id, player_name=player.name
                ).first()

                if not game_stat:
                    continue

                # Build game_stats dict from the PlayerStat row
                game_stats = {
                    "points": game_stat.points,
                    "reb": game_stat.reb,
                    "oreb": game_stat.oreb,
                    "dreb": game_stat.dreb,
                    "ast": game_stat.ast,
                    "stl": game_stat.stl,
                    "blk": game_stat.blk,
                    "tov": game_stat.tov,
                    "fgm": game_stat.fgm,
                    "fga": game_stat.fga,
                    "fg_percent": game_stat.fg_percent,
                    "tpm": game_stat.tpm,
                    "tpa": game_stat.tpa,
                    "tp_percent": game_stat.tp_percent,
                    "ftm": game_stat.ftm,
                    "fta": game_stat.fta,
                    "ft_percent": game_stat.ft_percent,
                }

                season_avg = _calculate_player_season_averages(player.name, game.id)

                # Route through notification_service (respects channel preference)
                notify_player_performance(
                    player, player.name, game, game_stats, season_avg
                )

    except Exception as e:
        current_app.logger.error(
            f"Failed to send game notification (Game ID {getattr(game, 'id', None)}): {e}"
        )
```

Note: The player performance report PDF attachment is now **not attached via WhatsApp** (WhatsApp text-only). If the channel is `email` or `both`, `email_service.send_player_performance_email()` handles it. For WhatsApp channels, the text-only `send_player_performance_whatsapp` is used. If you need PDF attachments on WhatsApp, that requires additional OpenWA media support (out of scope for this plan).

#### 4.4.2 `web/routes/auth.py` — OTP routing

```python
# Before: line 25
from core.services.email_service import send_otp_email

# After
from core.services.notification_service import notify_otp
```

Update the call site at line 83:

```python
# Before
send_otp_email(user.email, otp_code)

# After
notify_otp(
    user.email, otp_code,
    whatsapp_phone=getattr(user, "whatsapp_phone", None)
)
```

---

## Part 5 — Web UI

### 5.1 User notification preferences (settings page)

Add to the existing user settings template. The route should be registered on `auth_bp` in `web/routes/auth.py`:

```python
@auth_bp.route("/settings/notifications", methods=["POST"])
@login_required
def update_notification_settings():
    channel = request.form.get("notification_channel", "email")
    phone   = request.form.get("whatsapp_phone", "").strip() or None
    user = User.query.get(current_user.id)
    user.notification_channel = channel
    user.whatsapp_phone = phone
    db.session.commit()
    flash("Notification preferences saved.", "success")
    return redirect(url_for("main.admin_panel", section="settings"))
```

Template snippet to add inside the Settings tab of `web/templates/auth/admin.html` (after the existing notification toggles, before the `<hr>` at line 213 `Futures` section):

```html
                                <hr>
                                <h6 class="mb-2">My Notification Preferences</h6>
                                <form method="POST" action="{{ url_for('auth.update_notification_settings') }}">
                                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                                    <div class="mb-3">
                                        <label for="notification_channel" class="form-label">Delivery Channel</label>
                                        <select id="notification_channel" name="notification_channel" class="form-select">
                                            <option value="email"
                                                {% if current_user.notification_channel == 'email' %}selected{% endif %}>
                                                Email only</option>
                                            <option value="whatsapp"
                                                {% if current_user.notification_channel == 'whatsapp' %}selected{% endif %}>
                                                WhatsApp (personal) only</option>
                                            <option value="whatsapp_group"
                                                {% if current_user.notification_channel == 'whatsapp_group' %}selected{% endif %}>
                                                WhatsApp group only</option>
                                            <option value="both"
                                                {% if current_user.notification_channel == 'both' %}selected{% endif %}>
                                                Email + personal WhatsApp</option>
                                            <option value="all"
                                                {% if current_user.notification_channel == 'all' %}selected{% endif %}>
                                                All channels</option>
                                        </select>
                                    </div>

                                    <div class="mb-3" id="phone-field">
                                        <label for="whatsapp_phone" class="form-label">
                                            WhatsApp Phone
                                            <small class="text-muted">(international format, e.g. +393331234567)</small>
                                        </label>
                                        <input type="tel" id="whatsapp_phone" name="whatsapp_phone"
                                               class="form-control"
                                               value="{{ current_user.whatsapp_phone or '' }}"
                                               placeholder="+39...">
                                    </div>

                                    <button type="submit" class="btn btn-primary">Save preferences</button>
                                </form>

                                <script>
                                const sel = document.getElementById('notification_channel');
                                const phoneField = document.getElementById('phone-field');
                                function togglePhone() {
                                    phoneField.style.display = sel.value === 'email' ? 'none' : '';
                                }
                                if (sel) { sel.addEventListener('change', togglePhone); togglePhone(); }
                                </script>
```

### 5.2 Admin group management

Add a new route in `web/routes/auth.py`:

```python
@auth_bp.route("/admin/teams/<int:team_id>/whatsapp-groups", methods=["GET", "POST"])
@login_required
@gm_required
def manage_whatsapp_groups(team_id):
    team = Team.query.get_or_404(team_id)
    # Ensure user has access to this team's org
    if team.organization_id != current_user.organization_id:
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            group = WhatsAppGroup(
                team_id=team_id,
                group_name=request.form["group_name"],
                group_wa_id=request.form["group_wa_id"].strip(),
            )
            db.session.add(group)
        elif action == "toggle":
            group = WhatsAppGroup.query.get_or_404(request.form["group_id"])
            group.active = not group.active
        elif action == "delete":
            group = WhatsAppGroup.query.get_or_404(request.form["group_id"])
            db.session.delete(group)
        db.session.commit()
        return redirect(url_for("auth.manage_whatsapp_groups", team_id=team_id))

    groups = WhatsAppGroup.query.filter_by(team_id=team_id).order_by(WhatsAppGroup.created_at).all()
    return render_template("admin/whatsapp_groups.html", groups=groups, team=team)
```

Add a navigation link in `web/templates/auth/admin.html` — inside the Settings tab panel, or as a standalone tab. Recommended: add a 4th tab by modifying the nav-tabs section:

```html
    <ul class="nav nav-tabs mb-4" role="tablist">
        <li class="nav-item" role="presentation">
            <a class="nav-link {% if section == 'users' %}active{% endif %}"
               href="{{ url_for('main.admin_panel', section='users') }}">
                <i class="fas fa-users"></i> Users
            </a>
        </li>
        <li class="nav-item" role="presentation">
            <a class="nav-link {% if section == 'players' %}active{% endif %}"
               href="{{ url_for('main.admin_panel', section='players') }}">
                <i class="fas fa-user-friends"></i> Players
            </a>
        </li>
        <li class="nav-item" role="presentation">
            <a class="nav-link {% if section == 'settings' %}active{% endif %}"
               href="{{ url_for('main.admin_panel', section='settings') }}">
                <i class="fas fa-cog"></i> Settings
            </a>
        </li>
        <li class="nav-item" role="presentation">
            <a class="nav-link"
               href="{{ url_for('auth.manage_whatsapp_groups', team_id=session.get('current_team_id', 1)) }}">
                <i class="fab fa-whatsapp"></i> WhatsApp Groups
            </a>
        </li>
    </ul>
```

New template `web/templates/admin/whatsapp_groups.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="container mt-4">
    <h2>WhatsApp Groups — {{ team.name }}</h2>

    <table class="table">
        <thead>
            <tr>
                <th>Name</th>
                <th>Group ID (@g.us)</th>
                <th>Active</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for g in groups %}
            <tr>
                <td>{{ g.group_name }}</td>
                <td><code>{{ g.group_wa_id }}</code></td>
                <td>{{ '✅' if g.active else '⏸' }}</td>
                <td>
                    <form method="POST" style="display:inline">
                        <input type="hidden" name="action" value="toggle">
                        <input type="hidden" name="group_id" value="{{ g.id }}">
                        <button class="btn btn-sm btn-secondary">
                            {{ 'Pause' if g.active else 'Activate' }}
                        </button>
                    </form>
                    <form method="POST" style="display:inline"
                          onsubmit="return confirm('Delete this group?')">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="group_id" value="{{ g.id }}">
                        <button class="btn btn-sm btn-danger">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <h3>Add Group</h3>
    <p>
        Find the group ID by running:<br>
        <code>curl -s http://SERVER:3000/api/sessions/basketball-bot/chats
        -H "x-api-key: KEY" | jq '.[] | select(.id | endswith("@g.us")) | {id, name}'</code>
    </p>
    <form method="POST">
        <input type="hidden" name="action" value="add">
        <input type="text" name="group_name"  placeholder="Group name"         required>
        <input type="text" name="group_wa_id" placeholder="120363XXX@g.us"     required>
        <button type="submit" class="btn btn-primary">Add</button>
    </form>

    <a href="{{ url_for('main.admin_panel', section='settings') }}" class="btn btn-outline-secondary mt-3">
        ← Back to Admin
    </a>
</div>
{% endblock %}
```

---

## Part 6 — Deployment Checklist

Execute in order on the Ubuntu server:

```bash
# 1. Pull latest code
git pull origin main

# 2. Add OPENWA_* vars to .env.prod

# 3. Run DB migration (creates columns + whatsapp_groups table)
docker compose -f docker-compose.prod.yml run --rm migrator

# 4. Temporarily expose port 3000 in docker-compose.prod.yml for QR pairing
#    (edit ports: - "3000:3000" under openwa:)

# 5. Build and start OpenWA first
docker compose -f docker-compose.prod.yml up -d openwa

# 6. From Mac — pair the session (see Part 1.3)

# 7. Remove port 3000 exposure from docker-compose.prod.yml

# 8. Full stack redeploy
docker compose -f docker-compose.prod.yml up -d --build

# 9. Verify OpenWA health
docker compose -f docker-compose.prod.yml ps openwa
# Expected: healthy

# 10. Register WhatsApp groups via the admin UI at /admin/teams/<id>/whatsapp-groups

# 11. Test: send a manual notification
docker compose -f docker-compose.prod.yml exec web_1 \
  python -c "
from run import app
from core.services.whatsapp_service import _send, _chat_id
with app.app_context():
    ok = _send(_chat_id('393XXXXXXXXX'), 'Test from Basketball Stats ✅')
    print('OK' if ok else 'FAILED')
"
```

> **Key difference from original plan:** Step 3 now runs `docker compose ... run --rm migrator` (the existing migrator service) instead of a standalone script. The migration logic is embedded in `scripts/migrate.py` + `init_db.py`, following the project's established pattern.

---

## Part 7 — Session Maintenance

| Scenario | Action |
|---|---|
| Normal restart | Session auto-resumes from `openwa_data` volume — no action needed |
| Phone inactive 14+ days | Re-run QR pairing (Part 1.3) |
| WhatsApp session ban | Switch to a different phone number, re-pair |
| Volume deleted | Full re-pair required |

To check session status at any time from the server (no port exposure needed):

```bash
docker compose -f docker-compose.prod.yml exec openwa \
  wget -qO- http://localhost:3000/api/sessions/basketball-bot \
  | python3 -m json.tool | grep status
```

---

## Part 8 — Architecture Diagram

```
┌────────────────────────────────────────────────────────────┐
│                    Docker backend network                   │
│                                                            │
│  ┌──────────┐   notify_game()   ┌─────────────────────┐   │
│  │  web_1   │ ─────────────────►│ notification_service │   │
│  │  web_2   │                   └──────────┬──────────┘   │
│  │  web_3   │                              │               │
│  └──────────┘               ┌─────────────┴──────────┐    │
│                              │                        │    │
│                    ┌─────────▼──────┐   ┌────────────▼──┐ │
│                    │ email_service  │   │whatsapp_service│ │
│                    │ (flask-mail)   │   │  (httpx)       │ │
│                    └───────────────-┘   └────────┬───────┘ │
│                                                  │         │
│                                         ┌────────▼───────┐ │
│                                         │    openwa      │ │
│                                         │ :3000 (intern) │ │
│                                         └────────┬───────┘ │
└──────────────────────────────────────────────────┼─────────┘
                                                    │
                                             ┌──────▼──────┐
                                             │  WhatsApp   │
                                             │  (personal  │
                                             │  or group)  │
                                             └─────────────┘
```

---

## Appendix — Migration of existing callers

| File | Current import | Replace with |
|---|---|---|
| `web/routes/main.py` (line 68) | `from core.services.email_service import send_game_notification` | `from core.services.notification_service import notify_game, notify_player_performance` |
| `web/routes/auth.py` (line 25) | `from core.services.email_service import send_otp_email` | `from core.services.notification_service import notify_otp` |
| Any other file | `send_game_notification(emails, ...)` | `notify_game(user_instances, ..., team=game.team)` (pass model instances, not strings) |
| Any other file | `send_player_performance_email(...)` | `notify_player_performance(recipient_instance, ...)` |
| Any other file | `send_otp_email(email, code)` | `notify_otp(email, code, whatsapp_phone=...)` |
