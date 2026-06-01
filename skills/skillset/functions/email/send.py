import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def send_email(to: str, subject: str, body: str, cc: Optional[str] = None) -> str:
    email = os.getenv("evy-email")
    password = os.getenv("evy-email-password")
    if not email or not password:
        return "Evy's email credentials not configured. Set evy-email and evy-email-password in .env"

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email
        msg["To"] = to
        if cc:
            msg["Cc"] = cc

        recipients = [to] + ([cc] if cc else [])
        host = os.getenv("evy-email-smtp-host", "smtp.gmail.com")
        port = int(os.getenv("evy-email-smtp-port", "465"))

        with smtplib.SMTP_SSL(host, port) as server:
            server.login(email, password)
            server.sendmail(email, recipients, msg.as_string())

        return f"Email sent to {to}: {subject}"
    except Exception as e:
        return f"Failed to send email: {e}"


def send_email_on_behalf(
    to: str, subject: str, body: str, cc: Optional[str] = None
) -> str:
    email = os.getenv("user-email")
    password = os.getenv("user-email-password")
    if not email or not password:
        return "Your email credentials not configured. Set user-email and user-email-password in .env"

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email
        msg["To"] = to
        if cc:
            msg["Cc"] = cc

        recipients = [to] + ([cc] if cc else [])
        host = os.getenv(
            "user-email-smtp-host", os.getenv("evy-email-smtp-host", "smtp.gmail.com")
        )
        port = int(
            os.getenv("user-email-smtp-port", os.getenv("evy-email-smtp-port", "465"))
        )

        with smtplib.SMTP_SSL(host, port) as server:
            server.login(email, password)
            server.sendmail(email, recipients, msg.as_string())

        return f"Email sent on your behalf to {to}: {subject}"
    except Exception as e:
        return f"Failed to send email on your behalf: {e}"


def send_batch_email(to: list[str], subject: str, body: str, cc: Optional[str] = None) -> str:
    email = os.getenv("evy-email")
    password = os.getenv("evy-email-password")
    if not email or not password:
        return "Evy's email credentials not configured. Set evy-email and evy-email-password in .env"

    host = os.getenv("evy-email-smtp-host", "smtp.gmail.com")
    port = int(os.getenv("evy-email-smtp-port", "465"))

    results = []
    for recipient in to:
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = email
            msg["To"] = recipient
            if cc:
                msg["Cc"] = cc

            recipients = [recipient] + ([cc] if cc else [])

            with smtplib.SMTP_SSL(host, port) as server:
                server.login(email, password)
                server.sendmail(email, recipients, msg.as_string())

            results.append(f"✓ {recipient}")
        except Exception as e:
            results.append(f"✗ {recipient}: {e}")

    return "Batch email results:\n" + "\n".join(results)
