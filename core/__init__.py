"""
Core package initializer.
Exposes the Mail extension instance for use throughout the application.
"""

from flask_mail import Mail

mail = Mail()
