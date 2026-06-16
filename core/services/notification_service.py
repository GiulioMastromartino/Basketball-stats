from core.services import email_service, whatsapp_service


def _channel(recipient) -> str:
    if isinstance(recipient, str):
        return "email"
    return getattr(recipient, "notification_channel", "email")


def notify_game(recipients, game, pdf_attachment=None, team=None) -> None:
    emails, phones, groups_notified = [], [], set()

    for r in recipients:
        ch = _channel(r)
        if ch in ("email", "both", "all") and getattr(r, "email", None):
            emails.append(r.email)
        if ch in ("whatsapp", "both", "all") and getattr(r, "whatsapp_phone", None):
            phones.append(r.whatsapp_phone)
        if ch in ("whatsapp_group", "all") and team:
            for group in getattr(team, "whatsapp_groups", []):
                if group.active:
                    groups_notified.add(group.group_wa_id)

    if emails:
        email_service.send_game_notification(emails, game, pdf_attachment)
    if phones:
        whatsapp_service.send_game_notification(phones, game)
    for group_id in groups_notified:
        whatsapp_service.send_game_notification_to_group(group_id, game)


def notify_player_performance(
    recipient, player_name: str, game, game_stats: dict, season_avg: dict
) -> bool:
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
    if whatsapp_phone:
        return whatsapp_service.send_otp_whatsapp(whatsapp_phone, otp_code)
    return email_service.send_otp_email(recipient_email, otp_code)
