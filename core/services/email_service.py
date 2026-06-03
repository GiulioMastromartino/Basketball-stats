from flask_mail import Message
from flask import current_app
from core import mail
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
