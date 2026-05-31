import os
import smtplib
from typing import Optional
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


def send_email(to: str, subject: str, body: str, cc: Optional[str] = None) -> str:
    email = os.getenv("evy_email")
    password = os.getenv("evy_email_password")
    if not email or not password:
        return "Evy's email credentials not configured. Set evy_email and evy_email_password in .env"

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email
        msg["To"] = to
        if cc:
            msg["Cc"] = cc

        recipients = [to] + ([cc] if cc else [])
        host = os.getenv("evy_email_smtp_host", "smtp.gmail.com")
        port = int(os.getenv("evy_email_smtp_port", "465"))

        with smtplib.SMTP_SSL(host, port) as server:
            server.login(email, password)
            server.sendmail(email, recipients, msg.as_string())

        return f"Email sent to {to}: {subject}"
    except Exception as e:
        return f"Failed to send email: {e}"
