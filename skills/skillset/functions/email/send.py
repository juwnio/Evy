import smtplib
from email.mime.text import MIMEText
from typing import Optional

from utilities.scripts.google_auth import get_connection

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def _send_smtp(to: str, subject: str, body: str, sender_email: str, app_password: str, cc: Optional[str] = None) -> None:
    msg = MIMEText(body)
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = sender_email
    if cc:
        msg["Cc"] = cc

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)


def send_email(to: str, subject: str, body: str, cc: Optional[str] = None, connection_id: Optional[str] = None) -> str:
    creds, err = get_connection(connection_id)
    if err:
        return err

    try:
        _send_smtp(to, subject, body, creds["email"], creds["app_password"], cc)
        return f"Email sent to {to}: {subject}"
    except Exception as e:
        return f"Failed to send email: {e}"


def send_batch_email(
    to: list[str], subject: str, body: str, cc: Optional[str] = None, connection_id: Optional[str] = None
) -> str:
    creds, err = get_connection(connection_id)
    if err:
        return err

    results = []
    for recipient in to:
        try:
            _send_smtp(recipient, subject, body, creds["email"], creds["app_password"], cc)
            results.append(f"\u2713 {recipient}")
        except Exception as e:
            results.append(f"\u2717 {recipient}: {e}")

    return "Batch email results:\n" + "\n".join(results)
