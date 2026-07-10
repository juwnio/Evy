import email
import imaplib
import json
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from typing import Optional

from utilities.scripts.google_auth import get_connection

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(part))
    return " ".join(parts)


def _fetch_email_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        return "\n".join(parts)
    try:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    except Exception:
        pass
    return ""


def _build_imap_query(content: Optional[str] = None, where: Optional[dict] = None) -> str:
    parts = ["ALL"]
    if where:
        if where.get("starred") is True:
            parts.append("FLAGGED")
        elif where.get("starred") is False:
            parts.append("UNFLAGGED")
        if where.get("is_unread") is True:
            parts.append("UNSEEN")
        elif where.get("is_unread") is False:
            parts.append("SEEN")
        if where.get("from_"):
            parts.append(f'FROM "{where["from_"]}"')
        if where.get("subject_contains"):
            parts.append(f'SUBJECT "{where["subject_contains"]}"')
        if where.get("sent_before"):
            parts.append(f'BEFORE "{where["sent_before"]}"')
        if where.get("sent_after"):
            parts.append(f'SINCE "{where["sent_after"]}"')
    if content:
        parts.append(f'TEXT "{content}"')
    return " ".join(parts)


def search_email(
    content: Optional[str] = None,
    where: Optional[dict] = None,
    order_by: Optional[str] = "-date",
    limit: Optional[int] = 20,
    connection_id: Optional[str] = None,
) -> str:
    creds, err = get_connection(connection_id)
    if err:
        return err

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(creds["email"], creds["app_password"])
        mail.select("INBOX")

        query = _build_imap_query(content, where)
        status, data = mail.search(None, query)
        if status != "OK" or not data[0]:
            mail.logout()
            return "No emails found."

        ids = data[0].split()
        ids = ids[-limit:] if len(ids) > limit else ids

        results = []
        for uid in reversed(ids):
            status, msg_data = mail.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            flags_status, flags_data = mail.fetch(uid, "(FLAGS)")
            flags = flags_data[0] if flags_data else b""
            is_seen = b"\\Seen" in flags
            is_flagged = b"\\Flagged" in flags

            results.append({
                "email_id": uid.decode() if isinstance(uid, bytes) else uid,
                "from": _decode_header_value(msg.get("From", "")),
                "to": [a.strip() for a in _decode_header_value(msg.get("To", "")).split(",") if a.strip()],
                "cc": [a.strip() for a in _decode_header_value(msg.get("Cc", "")).split(",") if a.strip()],
                "subject": _decode_header_value(msg.get("Subject", "")),
                "date": _decode_header_value(msg.get("Date", "")),
                "is_read": is_seen,
                "is_starred": is_flagged,
                "folder": "INBOX",
            })

        mail.logout()

        reverse = True
        sort_field = "date"
        if order_by:
            if order_by.startswith("-"):
                reverse = True
                sort_field = order_by[1:]
            else:
                reverse = False
                sort_field = order_by
        results.sort(key=lambda r: r.get(sort_field, ""), reverse=reverse)

        return json.dumps(results, indent=2)

    except Exception as e:
        return f"Email search failed: {e}"


def get_email_body(email_id: str, connection_id: Optional[str] = None) -> str:
    creds, err = get_connection(connection_id)
    if err:
        return err

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(creds["email"], creds["app_password"])
        mail.select("INBOX")

        status, msg_data = mail.fetch(email_id.encode(), "(RFC822)")
        if status != "OK":
            mail.logout()
            return "Failed to fetch email."

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        body = _fetch_email_body(msg)

        mail.logout()
        return body.strip() or "(empty body)"

    except Exception as e:
        return f"Failed to get email body: {e}"


def forward_email(
    email_id: str, to: str, body: Optional[str] = None, connection_id: Optional[str] = None
) -> str:
    creds, err = get_connection(connection_id)
    if err:
        return err

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(creds["email"], creds["app_password"])
        mail.select("INBOX")

        status, msg_data = mail.fetch(email_id.encode(), "(RFC822)")
        if status != "OK":
            mail.logout()
            return "Failed to fetch original email for forwarding."

        raw_email = msg_data[0][1]
        original = email.message_from_bytes(raw_email)

        original_subject = _decode_header_value(original.get("Subject", ""))
        original_from = _decode_header_value(original.get("From", ""))
        original_date = _decode_header_value(original.get("Date", ""))
        original_body = _fetch_email_body(original)

        mail.logout()

        forward_text = ""
        if body:
            forward_text += body + "\n\n"
        forward_text += "---------- Forwarded message ----------\n"
        forward_text += f"From: {original_from}\n"
        forward_text += f"Date: {original_date}\n"
        forward_text += f"Subject: {original_subject}\n\n"
        forward_text += original_body

        mime = MIMEText(forward_text)
        mime["Subject"] = f"Fwd: {original_subject}"
        mime["From"] = creds["email"]
        mime["To"] = to

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(creds["email"], creds["app_password"])
            server.send_message(mime)

        return f"Email forwarded to {to}: Fwd: {original_subject}"

    except Exception as e:
        return f"Failed to forward email: {e}"


def trash_email(
    email_ids: list[str],
    connection_id: Optional[str] = None,
) -> str:
    creds, err = get_connection(connection_id)
    if err:
        return err

    if not email_ids:
        return json.dumps({"trashed": [], "failed": []})

    email_ids = email_ids[:100]

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(creds["email"], creds["app_password"])
        mail.select("INBOX")

        trashed = []
        failed = []
        for eid in email_ids:
            try:
                mail.store(eid.encode(), "+FLAGS", "\\Deleted")
                trashed.append(eid)
            except Exception as e:
                failed.append({"email_id": eid, "error": str(e)})

        mail.expunge()
        mail.logout()
        return json.dumps({"trashed": trashed, "failed": failed})

    except Exception as e:
        return json.dumps({"trashed": [], "failed": [{"email_id": "all", "error": str(e)}]})
