from flask_mail import Message
from flask import current_app
from core import mail

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
    sender = current_app.config['MAIL_DEFAULT_SENDER']
    
    # Simple text body for testing
    body = f"Your verification code is: {otp_code}\n\nThis code expires in 5 minutes."
    
    msg = Message(subject, sender=sender, recipients=[to_email])
    msg.body = body
    
    # Send immediately (synchronous) for the first smoke test to see errors
    # Later, switch to threading for performance
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"SMTP Error: {e}")
        return False
