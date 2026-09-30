from flask_mail import Message
from flask import current_app
from core import mail
import html
import smtplib
import sys


def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
            current_app.logger.info(f"Email sent to {msg.recipients}")
        except Exception as e:
            current_app.logger.error(f"Failed to send email: {e}")


def send_otp_email(to_email, otp_code):
    """Sends a 6-digit OTP code to the user."""
    subject = "Your Login Verification Code"
    sender = current_app.config.get("MAIL_DEFAULT_SENDER")

    if not sender:
        current_app.logger.error("MAIL_DEFAULT_SENDER is not set!")
        return False

    body = f"Your verification code is: {otp_code}\n\nThis code expires in 5 minutes."

    msg = Message(subject, sender=sender, recipients=[to_email])
    msg.body = body

    try:
        current_app.logger.info(
            f"Attempting to send OTP email from {sender} to {to_email}"
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"OTP Email Failed: {e}")
        return False


def send_game_notification(recipients, game, pdf_attachment=None):
    """
    Sends a new game notification to a list of recipients.

    :param recipients: List of email strings
    :param game: Game model instance
    :param pdf_attachment: Tuple (filename, bytes) or None
    """
    if not recipients:
        return

    subject = f"New Game Added: {game.opponent} ({game.result})"
    sender = current_app.config.get("MAIL_DEFAULT_SENDER")

    if not sender:
        current_app.logger.error("MAIL_DEFAULT_SENDER is not set!")
        return

    body = f"""
    A new game has been added to the tracker.
    
    Opponent: {game.opponent}
    Date: {game.date}
    Result: {game.result} ({game.score_display})
    Type: {game.game_type}
    
    Log in to view full details.
    """

    msg = Message(subject, sender=sender, bcc=recipients)
    msg.body = body

    if pdf_attachment:
        filename, file_bytes = pdf_attachment
        if filename and file_bytes:
            msg.attach(filename, "application/pdf", file_bytes)

    try:
        # Sending synchronously to ensure delivery before response,
        # or you can spawn a thread if performance is critical.
        mail.send(msg)
        current_app.logger.info(
            f"Game notification sent to {len(recipients)} recipients."
        )
    except Exception as e:
        current_app.logger.error(f"Game notification failed: {e}")


def _single_line(value):
    """Flatten a value to one clean line for use in plain-text email.

    Strips CR/LF and other control characters so untrusted text (a username,
    an org name) cannot inject extra headers or break the body layout.
    Returns an empty string for None.
    """
    if not value:
        return ""
    return "".join(
        ch for ch in str(value)
        if ch.isprintable() or ch == " "
    ).strip()


def _invite_html(username, login_url, org_name=None):
    """Branded HTML alternative for the invite, matching the app shell.

    Dark header (#0b0e12) with the HoopsLab wordmark, cream body (#f3efe6),
    orange CTA (#ff4d00, the --hs-accent) and teal accent (#2ec4b6,
    --hs-cool). Table layout + inline styles only, so it renders in
    Gmail/Outlook/Apple Mail without external CSS or fonts.
    """
    safe_user = html.escape(username or "there")
    safe_url = html.escape(login_url or "", quote=True)
    safe_org = html.escape(org_name) if org_name else None
    org_row = (
        f"""<p style="margin:0 0 12px;font-size:14px;color:#4f4a43;">
          You've been added to <strong>{safe_org}</strong>.</p>"""
        if safe_org else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:0;background:#12161d;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">
  Your HoopsLab account is ready — sign in with WorkOS, no password needed.
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#12161d;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;border-radius:14px;overflow:hidden;">
<tr><td style="background:#0b0e12;padding:28px 32px;text-align:center;border-bottom:3px solid #ff4d00;">
<p style="margin:0;font-family:Arial,sans-serif;font-size:26px;font-weight:bold;letter-spacing:1px;color:#ffffff;">&#127936; Hoops<span style="color:#2ec4b6;">Lab</span></p>
<p style="margin:8px 0 0;font-family:Arial,sans-serif;font-size:12px;letter-spacing:2px;color:#8b93a1;">STATS THAT FEEL LIKE FILM SESSION</p>
</td></tr>
<tr><td style="background:#f3efe6;padding:32px;font-family:Arial,sans-serif;color:#1a1714;">
<h1 style="margin:0 0 8px;font-size:22px;">Hi {safe_user}, you're invited.</h1>
{org_row}
<p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#4f4a43;">
Your account is ready. Sign in directly with WorkOS — no password needed.</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 20px;"><tr><td align="center" style="border-radius:10px;background:#ff4d00;">
<a href="{safe_url}" style="display:inline-block;padding:14px 36px;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;">Sign in with WorkOS</a>
</td></tr></table>
<p style="margin:0 0 8px;font-size:12px;color:#4f4a43;">Button not working? Paste this link into your browser:</p>
<p style="margin:0 0 20px;font-size:12px;word-break:break-all;"><a href="{safe_url}" style="color:#2ec4b6;">{safe_url}</a></p>
<p style="margin:0;font-size:12px;color:#4f4a43;">Tip: on the sign-in page choose <strong>Single Sign-On</strong>.</p>
</td></tr>
<tr><td style="background:#0b0e12;padding:16px 32px;text-align:center;">
<p style="margin:0;font-family:Arial,sans-serif;font-size:11px;letter-spacing:1px;color:#8b93a1;">HOOPSLAB &middot; BASKETBALL STATS</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def send_invite_email(to_email, username, login_url, org_name=None):
    """Invite a new member with a direct WorkOS login link.

    Best-effort: returns True on success, False when mail is unconfigured
    or sending fails. Never raises — the invite itself must not fail
    because email did.
    """
    sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    if not sender:
        current_app.logger.warning(
            f"Invite email to {to_email} skipped: MAIL_DEFAULT_SENDER not set"
        )
        return False
    if not to_email or not login_url:
        return False

    # Plain text must not carry CR/LF: an org or username containing them
    # would let a caller inject extra headers or break the body layout. HTML
    # escaping is wrong here (it would show a literal "&amp;" to the reader),
    # so control characters are stripped instead.
    safe_user_txt = _single_line(username)
    org_line = f" You've been added to {_single_line(org_name)}." if org_name else ""
    subject = "You're invited — sign in to HoopsLab"
    body = f"""Hi {safe_user_txt},{org_line}

Your account is ready. Sign in directly with WorkOS (no password needed):

{_single_line(login_url)}

If the link above doesn't work, open the app and choose Single Sign-On.

— HoopsLab
"""

    msg = Message(subject, sender=sender, recipients=[to_email])
    msg.body = body
    msg.html = _invite_html(username, login_url, org_name)

    try:
        mail.send(msg)
        current_app.logger.info(f"Invite email sent to {to_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send invite email to {to_email}: {e}")
        return False


def send_player_performance_email(
    player_email, player_name, game, game_stats, season_avg
):
    """
    Sends a player performance report comparing game stats to season averages.

    :param player_email: Player's email address
    :param player_name: Player's name
    :param game: Game model instance
    :param game_stats: Dict containing game statistics
    :param season_avg: Dict containing season average statistics
    :return: True on success, False on failure
    """
    if not player_email:
        current_app.logger.warning(f"No email provided for player {player_name}")
        return False

    sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    if not sender:
        current_app.logger.error("MAIL_DEFAULT_SENDER is not set!")
        return False

    subject = f"Performance Report: {player_name} vs {game.opponent} ({game.date})"

    # Calculate differences
    def calc_diff(current, average):
        if average == 0:
            return current
        return current - average

    # Format percentages
    def format_pct(value):
        return f"{value:.1f}%" if value is not None else "0.0%"

    body = f"""
Player Performance Report
========================

Player: {player_name}
Game: {game.opponent} ({game.date})
Result: {game.result} ({game.team_score}-{game.opponent_score})

GAME STATISTICS:
----------------
Points: {game_stats.get("points", 0)}
Rebounds: {game_stats.get("reb", 0)} (Off: {game_stats.get("oreb", 0)}, Def: {game_stats.get("dreb", 0)})
Assists: {game_stats.get("ast", 0)}
Steals: {game_stats.get("stl", 0)}
Blocks: {game_stats.get("blk", 0)}
Turnovers: {game_stats.get("tov", 0)}
Field Goals: {game_stats.get("fgm", 0)}/{game_stats.get("fga", 0)} ({format_pct(game_stats.get("fg_percent", 0))})
Three Pointers: {game_stats.get("tpm", 0)}/{game_stats.get("tpa", 0)} ({format_pct(game_stats.get("tp_percent", 0))})
Free Throws: {game_stats.get("ftm", 0)}/{game_stats.get("fta", 0)} ({format_pct(game_stats.get("ft_percent", 0))})

SEASON AVERAGES:
----------------
Points: {season_avg.get("points", 0):.1f}
Rebounds: {season_avg.get("reb", 0):.1f} (Off: {season_avg.get("oreb", 0):.1f}, Def: {season_avg.get("dreb", 0):.1f})
Assists: {season_avg.get("ast", 0):.1f}
Steals: {season_avg.get("stl", 0):.1f}
Blocks: {season_avg.get("blk", 0):.1f}
Turnovers: {season_avg.get("tov", 0):.1f}
Field Goals: {season_avg.get("fgm", 0):.1f}/{season_avg.get("fga", 0):.1f} ({format_pct(season_avg.get("fg_percent", 0))})
Three Pointers: {season_avg.get("tpm", 0):.1f}/{season_avg.get("tpa", 0):.1f} ({format_pct(season_avg.get("tp_percent", 0))})
Free Throws: {season_avg.get("ftm", 0):.1f}/{season_avg.get("fta", 0):.1f} ({format_pct(season_avg.get("ft_percent", 0))})

DIFFERENCE (Game - Season Avg):
------------------------------
Points: {calc_diff(game_stats.get("points", 0), season_avg.get("points", 0)):+.1f}
Rebounds: {calc_diff(game_stats.get("reb", 0), season_avg.get("reb", 0)):+.1f}
Assists: {calc_diff(game_stats.get("ast", 0), season_avg.get("ast", 0)):+.1f}
Steals: {calc_diff(game_stats.get("stl", 0), season_avg.get("stl", 0)):+.1f}
Blocks: {calc_diff(game_stats.get("blk", 0), season_avg.get("blk", 0)):+.1f}
Turnovers: {calc_diff(game_stats.get("tov", 0), season_avg.get("tov", 0)):+.1f}
FG%: {calc_diff(game_stats.get("fg_percent", 0), season_avg.get("fg_percent", 0)):+.1f}%
3PT%: {calc_diff(game_stats.get("tp_percent", 0), season_avg.get("tp_percent", 0)):+.1f}%
FT%: {calc_diff(game_stats.get("ft_percent", 0), season_avg.get("ft_percent", 0)):+.1f}%

Keep up the great work!
"""

    msg = Message(subject, sender=sender, recipients=[player_email])
    msg.body = body

    try:
        mail.send(msg)
        current_app.logger.info(f"Player performance email sent to {player_email}")
        return True
    except Exception as e:
        current_app.logger.error(
            f"Failed to send player performance email to {player_email}: {e}"
        )
        return False
