import os
import requests
import logging
from datetime import datetime
from uuid import uuid4

from msal import ConfidentialClientApplication
from jinja2 import Template
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.models.email_log import EmailLog

# === ENV CONFIG ===
GRAPH_URL = "https://graph.microsoft.com/v1.0"
CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
TENANT_ID = os.getenv("MS_TENANT_ID")
SENDER_EMAIL = os.getenv("MS_SENDER_EMAIL")

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, SENDER_EMAIL]):
    raise RuntimeError("❌ Missing one or more required Microsoft Graph environment variables")

logger = logging.getLogger(__name__)


# === Public Shortcut ===
def send_verification_email(to_email: str, name: str, token: str, user_id: str, db: Session):
    return send_template_email(
        to_email=to_email,
        name=name,
        template_key="verify_email",
        db=db,
        user_id=user_id,
        variables={"token": token, "verification_link": f"https://portal.founderhub.ai/verify-email?token={token}"}
    )


# === Reusable Email Sender ===
def send_template_email(
    to_email: str,
    name: str,
    template_key: str,
    db: Session,
    user_id: str = None,
    variables: dict = {}
):
    try:
        # 1. Load Template
        template = db.query(EmailTemplate).filter(
            EmailTemplate.template_key == template_key
        ).first()
        if not template:
            raise Exception(f"Email template '{template_key}' not found in DB")

        # 2. Render Template
        variables.update({"name": name, "email": to_email})
        subject = Template(template.subject).render(**variables)
        body = Template(template.html).render(**variables)

        # 3. Authenticate to Graph
        app = ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}"
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise Exception("Microsoft Graph token acquisition failed")

        # 4. Send Email
        logger.info(f"📤 Sending '{template_key}' from {SENDER_EMAIL} to {to_email}")

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_email}}]
            },
            "saveToSentItems": "false"
        }

        response = requests.post(
            f"{GRAPH_URL}/users/{SENDER_EMAIL}/sendMail",
            headers={
                "Authorization": f"Bearer {result['access_token']}",
                "Content-Type": "application/json"
            },
            json=payload
        )

        # 5. Log Email
        db.add(EmailLog(
            id=str(uuid4()),
            user_id=user_id,
            to_email=to_email,
            subject=subject,
            template_key=template_key,
            status="sent" if response.ok else "failed",
            error=None if response.ok else response.text,
            sent_at=datetime.utcnow()
        ))
        db.commit()

        if not response.ok:
            raise Exception(f"Graph sendMail failed: {response.status_code} {response.text}")

        logger.info(f"✅ Email sent: {template_key} → {to_email}")

    except Exception as e:
        logger.error(f"❌ Email error [{template_key}]: {str(e)}")
        try:
            db.add(EmailLog(
                id=str(uuid4()),
                user_id=user_id,
                to_email=to_email,
                subject=f"ERROR: {template_key}",
                template_key=template_key,
                status="failed",
                error=str(e),
                sent_at=datetime.utcnow()
            ))
            db.commit()
        except Exception as log_error:
            logger.critical(f"⚠️ Failed to write email log: {log_error}")

        raise
