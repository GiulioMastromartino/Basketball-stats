import httpx
from flask import current_app


def _client():
    return httpx.Client(
        base_url=current_app.config["OPENWA_API_URL"],
        headers={"x-api-key": current_app.config["OPENWA_API_KEY"]},
        timeout=10,
    )


def _session() -> str:
    return current_app.config["OPENWA_SESSION_ID"]


def _chat_id(phone: str) -> str:
    return f"{phone.lstrip('+').replace(' ', '')}@c.us"


def _group_chat_id(group_wa_id: str) -> str:
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
    text = (
        f"🔐 *Basketball Stats Login*\n"
        f"Your verification code is: *{otp_code}*\n\n"
        f"This code expires in 5 minutes."
    )
    return _send(_chat_id(phone), text, label=phone)
