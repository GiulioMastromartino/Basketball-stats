"""
Core package initializer.
Exposes the Mail extension instance for use throughout the application.

The Mail instance is a thin subclass that bounds SMTP socket I/O with
``MAIL_TIMEOUT`` — see :class:`BoundedSMTPConnection` for why.
"""

import smtplib

from flask import current_app
from flask_mail import Connection
from flask_mail import Mail as _FlaskMail


class BoundedSMTPConnection(Connection):
    """Flask-Mail connection that bounds SMTP socket I/O with ``MAIL_TIMEOUT``.

    Flask-Mail builds ``smtplib.SMTP(server, port)`` without a timeout, so a
    cold or black-holed SMTP host leaves the calling thread blocked in
    connect for as long as the OS TCP retries take (minutes). The game-save
    request runs its whole notification fan-out inline, so one hung SMTP
    handshake stalls the save until gunicorn's worker timeout kills it.

    This subclass threads the configured timeout into smtplib; everything
    else (TLS, auth, debug level) is inherited from ``Connection``.
    """

    def configure_host(self) -> smtplib.SMTP:
        timeout = current_app.config.get("MAIL_TIMEOUT") or None
        if self.mail.use_ssl:
            self.host = smtplib.SMTP_SSL(
                self.mail.server, self.mail.port, timeout=timeout
            )
        else:
            self.host = smtplib.SMTP(
                self.mail.server, self.mail.port, timeout=timeout
            )
        self.host.set_debuglevel(int(self.mail.debug))

        if self.mail.use_tls:
            self.host.starttls()

        if self.mail.username and self.mail.password:
            self.host.login(self.mail.username, self.mail.password)

        return self.host


class Mail(_FlaskMail):
    """Flask-Mail that hands out :class:`BoundedSMTPConnection` instances."""

    def connect(self) -> Connection:
        app = getattr(self, "app", None) or current_app
        state = app.extensions.get("mail")
        if state is None:
            raise RuntimeError(
                "The current application was not configured with Flask-Mail"
            )
        return BoundedSMTPConnection(state)


mail = Mail()
