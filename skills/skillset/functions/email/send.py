import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


def send_email(to: str, subject: str, body: str, cc: str = None) -> str:
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = os.getenv("evy_email")
        msg["To"] = to
        if cc:
            msg["Cc"] = cc

        recipients = [to] + ([cc] if cc else [])
        host = os.getenv("evy_email_smtp_host", "smtp.gmail.com")
        port = int(os.getenv("evy_email_smtp_port", "465"))

        with smtplib.SMTP_SSL(host, port) as server:
            server.login(os.getenv("evy_email"), os.getenv("evy_email_password"))
            server.sendmail(os.getenv("evy_email"), recipients, msg.as_string())

        return f"Email sent to {to}: {subject}"
    except Exception as e:
        return f"Failed to send email: {e}"
