import os
import requests
from uuid import uuid4
from datetime import datetime

from sqlalchemy.orm import Session
from app.models.login_event import LoginEvent
from app.models.user import User
from app.models.allowed_country import AllowedCountry
from app.services.email import send_template_email

IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")

# Optional fallback if tenant has no defined countries
# ✳️ Canada-friendly by default (NATO, G7, Commonwealth, strong trading partners)
ALLOWED_COUNTRIES_DEFAULT = [
    "CA", "US", "UK", "AU", "NZ", "FR", "DE", "JP", "KR",
    "IT", "SE", "FI", "NL", "NO", "DK", "IE", "SG", "BE"
]


def get_allowed_countries(tenant_id: str, db: Session) -> list[str]:
    countries = db.query(AllowedCountry).filter(
        AllowedCountry.tenant_id == tenant_id
    ).all()
    return [row.country_code for row in countries] if countries else ALLOWED_COUNTRIES_DEFAULT


def get_ip_metadata(ip: str) -> dict:
    try:
        res = requests.get(f"https://ipinfo.io/{ip}?token={IPINFO_TOKEN}", timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[IPINFO] Error fetching metadata: {e}")
        return {}


def log_login_event(user: User, ip: str, user_agent: str, db: Session) -> bool:
    is_new_ip = not db.query(LoginEvent).filter(
        LoginEvent.user_id == user.id,
        LoginEvent.ip_address == ip
    ).first()

    ip_data = get_ip_metadata(ip)
    country = ip_data.get("country", "Unknown")
    city = ip_data.get("city", "")
    region = ip_data.get("region", "")
    location = f"{city}, {region}".strip(", ")

    # Log event
    db.add(LoginEvent(
        id=str(uuid4()),
        user_id=user.id,
        ip_address=ip,
        location=location,
        country=country,
        user_agent=user_agent,
        is_new_ip=is_new_ip,
        created_at=datetime.utcnow()
    ))
    db.commit()

    # ❌ Block login if region is not allowed (and user did not disable)
    if is_new_ip and not getattr(user, "allow_new_region_login", False):
        allowed = get_allowed_countries(user.tenant_id, db)
        if country not in allowed:
            raise Exception(f"Login from disallowed region: {country}")

    # 🛎️ Alert admin if enabled
    if is_new_ip and getattr(user, "allow_admin_alerts", False):
        send_template_email(
            db=db,
            to_email="admin@founderhub.ai",
            name="Admin",
            template_key="admin_login_alert",
            user_id=user.id,
            variables={
                "email": user.email,
                "location": location,
                "ip": ip
            }
        )

    # 📤 Notify user
    if is_new_ip:
        send_template_email(
            db=db,
            to_email=user.email,
            name=user.name,
            template_key="new_login_detected",
            user_id=user.id,
            variables={
                "location": location,
                "ip": ip,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    return is_new_ip
