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
    
    # Send immediately (synchronous) for the first smoke test to see errors
    try:
        current_app.logger.info(f"Attempting to send OTP email from {sender} to {to_email} via {current_app.config.get('MAIL_SERVER')}")
        mail.send(msg)
        current_app.logger.info("Email sent successfully via Flask-Mail")
        return True
    except smtplib.SMTPAuthenticationError:
        current_app.logger.error("SMTP Authentication Error. Check your MAIL_USERNAME/PASSWORD.")
        return False
    except Exception as e:
        current_app.logger.error(f"SMTP Error ({type(e).__name__}): {e}")
        # Explicit print to stderr for container logs
        print(f"SMTP FAILED: {e}", file=sys.stderr)
        return False
