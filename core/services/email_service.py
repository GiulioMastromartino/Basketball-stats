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
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    
    if not sender:
        current_app.logger.error("MAIL_DEFAULT_SENDER is not set!")
        return False
        
    body = f"Your verification code is: {otp_code}\n\nThis code expires in 5 minutes."
    
    msg = Message(subject, sender=sender, recipients=[to_email])
    msg.body = body
    
    try:
        current_app.logger.info(f"Attempting to send OTP email from {sender} to {to_email}")
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
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    
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
            msg.attach(
                filename,
                "application/pdf",
                file_bytes
            )

    try:
        # Sending synchronously to ensure delivery before response, 
        # or you can spawn a thread if performance is critical.
        mail.send(msg)
        current_app.logger.info(f"Game notification sent to {len(recipients)} recipients.")
    except Exception as e:
        current_app.logger.error(f"Game notification failed: {e}")
