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
