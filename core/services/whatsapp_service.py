"""WhatsApp transport over Evolution API v2 (Baileys provider).

Replaces the former OpenWA sidecar. Same public function signatures, so
routes and notification dispatch are untouched — only the HTTP layer
changed::

    POST {EVOLUTION_API_URL}/message/sendText/{instance}   {"number", "text"}
    POST {EVOLUTION_API_URL}/message/sendMedia/{instance}  {"number", "mediatype", ...}
    GET  {EVOLUTION_API_URL}/instance/connectionState/{instance}

Auth is the global key in the ``apikey`` header. ``number`` is digits with
country code (no ``+``) for DMs, or a full group JID (``...@g.us``) for
groups. Evolution answers 201 on accepted sends.

Instance bootstrap (one time, see docs/archive/evolution-integration-plan.md):
``POST /instance/create`` {instanceName, qrcode: true,
integration: "WHATSAPP-BAILEYS"} → scan QR → state ``open``.
"""

import base64

import httpx
from flask import current_app


def _base_url() -> str:
    return (current_app.config.get("EVOLUTION_API_URL") or "").rstrip("/")


def _api_key() -> str:
    return current_app.config.get("EVOLUTION_API_KEY") or ""


def _instance() -> str:
    return current_app.config.get("EVOLUTION_INSTANCE") or "basketball-bot"


def _client():
    return httpx.Client(
        base_url=_base_url(),
        headers={"apikey": _api_key()},
        timeout=10,
    )


def _configured() -> bool:
    return bool(_base_url() and _api_key())


def _mask(dest: str) -> str:
    """Mask a phone/JID for logs (GDPR: no raw recipient ids on disk)."""
    text = str(dest or "")
    if "@" in text:
        local, _, domain = text.partition("@")
        if len(local) > 6:
            return f"{local[:4]}…{local[-2:]}@{domain}"
        return f"…@{domain}"
    if len(text) > 5:
        return f"{text[:3]}…{text[-2:]}"
    return "…"


def _to_number(phone_or_jid: str) -> str:
    """Normalize a destination: group JIDs pass through, phones → digits."""
    text = (phone_or_jid or "").strip()
    if not text:
        current_app.logger.error("_to_number called with empty/None value")
        return ""
    if "@g.us" in text or "@s.whatsapp.net" in text or "@lid" in text:
        return text
    return "".join(ch for ch in text if ch.isdigit()).lstrip("+")


def _post(path: str, payload: dict, label: str = "") -> bool:
    if not _configured():
        current_app.logger.warning(
            "Evolution API not configured — skipping send to %s",
            _mask(label) or path,
        )
        return False
    try:
        with _client() as c:
            r = c.post(path, json=payload)
            r.raise_for_status()
            current_app.logger.info("WhatsApp sent to %s",
                                    _mask(label) or path)
            return True
    except httpx.HTTPError as e:
        current_app.logger.error("WhatsApp send failed to %s: %s",
                                 _mask(label) or path, e)
        return False


def get_connection_state() -> str:
    """Instance state: open | connecting | close | unknown.

    ``unknown`` covers unconfigured transport and any error — callers use
    it for health probes, never for control flow.
    """
    if not _configured():
        return "unknown"
    try:
        with _client() as c:
            r = c.get(f"/instance/connectionState/{_instance()}")
            r.raise_for_status()
            return (
                (r.json().get("instance") or {}).get("state") or "unknown"
            )
    except Exception as e:
        current_app.logger.error(f"WhatsApp connection-state check failed: {e}")
        return "unknown"


def send_text_message(chat_id: str, text: str, label: str = "") -> bool:
    """Send an arbitrary text to a number or group JID. Never raises."""
    to = _to_number(chat_id)
    if not to:
        return False
    try:
        return _post(f"/message/sendText/{_instance()}",
                     {"number": to, "text": text}, label=label or to)
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.error(f"WhatsApp text send failed: {exc}")
        return False


def send_document(to: str, *, filename: str, mimetype: str,
                 media_base64: bytes | str, caption: str = "") -> bool:
    """Send a file (e.g. the halftime PDF) with an optional caption.

    ``media_base64`` is raw bytes or a base64 string. Never raises.
    """
    dest = _to_number(to)
    if not dest:
        return False
    if isinstance(media_base64, (bytes, bytearray)):
        media_base64 = base64.b64encode(bytes(media_base64)).decode("ascii")
    try:
        return _post(
            f"/message/sendMedia/{_instance()}",
            {"number": dest, "mediatype": "document",
             "mimetype": mimetype, "media": media_base64,
             "fileName": filename, "caption": caption},
            label=dest,
        )
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.error(f"WhatsApp document send failed: {exc}")
        return False


def send_game_notification(phones: list, game, pdf_attachment=None) -> None:
    text = (
        f"🏀 *New Game Added*\n"
        f"Opponent: {game.opponent}\n"
        f"Date: {game.date}\n"
        f"Result: {game.result} ({game.score_display})\n"
        f"Type: {game.game_type}\n\n"
        f"Log in to view full details."
    )
    for phone in phones:
        if not phone:
            continue
        send_text_message(phone, text, label=phone)


def send_game_notification_to_group(group_wa_id: str, game) -> bool:
    text = (
        f"🏀 *New Game Added*\n"
        f"Opponent: {game.opponent}\n"
        f"Date: {game.date}\n"
        f"Result: {game.result} ({game.score_display})\n"
        f"Type: {game.game_type}\n\n"
        f"Log in to view full details."
    )
    return send_text_message(group_wa_id, text, label=f"group:{group_wa_id}")


def send_player_performance_whatsapp(
    player_phone: str, player_name: str, game, game_stats: dict, season_avg: dict
) -> bool:
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
    return send_text_message(player_phone, text, label=player_phone)


def send_otp_whatsapp(phone: str, otp_code: str) -> bool:
    if not phone:
        current_app.logger.warning("No WhatsApp phone for OTP delivery")
        return False
    text = (
        f"🔐 *Basketball Stats Login*\n"
        f"Your verification code is: *{otp_code}*\n\n"
        f"This code expires in 5 minutes."
    )
    return send_text_message(phone, text, label=phone)
