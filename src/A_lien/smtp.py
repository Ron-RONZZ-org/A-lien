"""SMTP send engine for A-lien.

Provides email sending with attachments and signature support
using stdlib smtplib and email.mime.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Any

from A import tr_multi
from A.core.network import format_connection_error


class SMTPClient:
    """Low-level SMTP operations for sending email."""

    def __init__(self, host: str, port: int = 587, use_tls: bool = True):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self._conn: smtplib.SMTP | None = None

    def connect(self, username: str, password: str) -> None:
        """Connect, optionally upgrade to TLS, and login to SMTP server.

        Args:
            username: SMTP username (usually email)
            password: SMTP password

        Raises:
            ConnectionError: If connection, TLS upgrade, or login fails
        """
        try:
            self._conn = smtplib.SMTP(self.host, self.port, timeout=30)
            self._conn.ehlo()

            if self.use_tls:
                self._conn.starttls()
                self._conn.ehlo()

            self._conn.login(username, password)
        except smtplib.SMTPAuthenticationError as e:
            raise ConnectionError(
                tr_multi(
                    f"SMTP-aŭtentigo malsukcesis por {username}@{self.host}:{self.port} — {e}",
                    f"SMTP authentication failed for {username}@{self.host}:{self.port} — {e}",
                    f"Échec d'authentification SMTP pour {username}@{self.host}:{self.port} — {e}",
                )
            ) from e
        except (socket.gaierror, ConnectionRefusedError,
                TimeoutError, socket.timeout, ssl.SSLError, OSError) as e:
            raise ConnectionError(
                format_connection_error(e, self.host, self.port, "SMTP")
            ) from e
        except Exception as e:
            raise ConnectionError(
                tr_multi(
                    f"SMTP-konekto malsukcesis al {username}@{self.host}:{self.port} — {e}",
                    f"SMTP connection failed to {username}@{self.host}:{self.port} — {e}",
                    f"Échec de connexion SMTP vers {username}@{self.host}:{self.port} — {e}",
                )
            ) from e

    @property
    def conn(self) -> smtplib.SMTP:
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    def disconnect(self) -> None:
        """Close SMTP connection."""
        if self._conn:
            try:
                self._conn.quit()
            except Exception:  # noqa: S110 — cleanup, ignore errors
                pass
            self._conn = None

    def send_email(
        self,
        from_addr: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[str | Path] | None = None,
        html_body: str = "",
        priority: int = 5,
    ) -> None:
        """Send an email message.

        Args:
            from_addr: Sender email address
            to: List of primary recipients
            subject: Email subject
            body: Plain text body
            cc: Carbon copy recipients
            bcc: Blind carbon copy recipients
            attachments: List of file paths to attach
            html_body: Optional HTML body (alternative to plain text)
            priority: Priority level (1=highest, 5=lowest)

        Raises:
            ConnectionError: If sending fails
        """
        cc = cc or []
        bcc = bcc or []
        attachments = attachments or []

        all_recipients = to + cc + bcc

        if attachments or (html_body and body):
            msg = MIMEMultipart("alternative" if (html_body and body) else "mixed")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = ", ".join(to)

            if cc:
                msg["Cc"] = ", ".join(cc)

            if body:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            for path in attachments:
                self._attach_file(msg, path)
        else:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = ", ".join(to)
            if cc:
                msg["Cc"] = ", ".join(cc)

        # Set priority headers (1=highest, 5=lowest)
        if priority != 5:
            msg["X-Priority"] = str(priority)
            if priority <= 2:
                msg["X-MSMail-Priority"] = "High"
                msg["Importance"] = "High"
            elif priority >= 4:
                msg["X-MSMail-Priority"] = "Low"
                msg["Importance"] = "Low"
            else:
                msg["X-MSMail-Priority"] = "Normal"
                msg["Importance"] = "Normal"

        try:
            self.conn.sendmail(from_addr, all_recipients, msg.as_string())
        except Exception as e:
            raise ConnectionError(
                tr_multi(
                    f"SMTP-sendo malsukcesis: {e}",
                    f"SMTP send failed: {e}",
                    f"Échec d'envoi SMTP: {e}",
                )
            ) from e

    @staticmethod
    def _attach_file(msg: MIMEMultipart, path: str | Path) -> None:
        """Attach a file to a MIME message."""
        path = Path(path)
        if not path.exists():
            return

        with path.open("rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{path.name}"',
            )
            msg.attach(part)


__all__ = ["SMTPClient"]
