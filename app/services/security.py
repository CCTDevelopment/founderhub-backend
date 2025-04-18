import os
import requests
from datetime import datetime
from uuid import uuid4
from ipaddress import ip_address

from sqlalchemy.orm import Session
from app.models.login_event import LoginEvent
from app.models.user import User
from app.services.email import send_template_email
from app.models.allowed_country import AllowedCountry

IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")

# Define hardcoded allowed countries (G8 + any extras)
ALLOWED_COUNTRIES_DEFAULT = [
    # North America
    ("US", "🇺🇸 United States"),
    ("CA", "🇨🇦 Canada"),
    ("MX", "🇲🇽 Mexico"),

    # Europe (GDPR-compliant, low-risk)
    ("UK", "🇬🇧 United Kingdom"),
    ("FR", "🇫🇷 France"),
    ("DE", "🇩🇪 Germany"),
    ("NL", "🇳🇱 Netherlands"),
    ("SE", "🇸🇪 Sweden"),
    ("NO", "🇳🇴 Norway"),
    ("FI", "🇫🇮 Finland"),
    ("DK", "🇩🇰 Denmark"),
    ("CH", "🇨🇭 Switzerland"),
    ("AT", "🇦🇹 Austria"),
    ("IE", "🇮🇪 Ireland"),
    ("ES", "🇪🇸 Spain"),
    ("IT", "🇮🇹 Italy"),
    ("BE", "🇧🇪 Belgium"),
    ("PT", "🇵🇹 Portugal"),
    ("PL", "🇵🇱 Poland"),
    ("CZ", "🇨🇿 Czech Republic"),
    ("SK", "🇸🇰 Slovakia"),
    ("LT", "🇱🇹 Lithuania"),
    ("LV", "🇱🇻 Latvia"),
    ("EE", "🇪🇪 Estonia"),
    ("LU", "🇱🇺 Luxembourg"),
    ("SI", "🇸🇮 Slovenia"),
    ("HR", "🇭🇷 Croatia"),

    # Asia-Pacific
    ("AU", "🇦🇺 Australia"),
    ("NZ", "🇳🇿 New Zealand"),
    ("JP", "🇯🇵 Japan"),
    ("SG", "🇸🇬 Singapore"),
    ("KR", "🇰🇷 South Korea"),
    ("IN", "🇮🇳 India"),
    ("PH", "🇵🇭 Philippines"),

    # Middle East (trusted)
    ("AE", "🇦🇪 United Arab Emirates"),
    ("IL", "🇮🇱 Israel"),
    ("QA", "🇶🇦 Qatar"),
    ("OM", "🇴🇲 Oman"),
    ("BH", "🇧🇭 Bahrain"),

    # South America
    ("BR", "🇧🇷 Brazil"),
    ("AR", "🇦🇷 Argentina"),
    ("CL", "🇨🇱 Chile"),
    ("CO", "🇨🇴 Colombia"),
    ("PE", "🇵🇪 Peru"),
    ("UY", "🇺🇾 Uruguay"),

    # Africa (optional, stable markets)
    ("ZA", "🇿🇦 South Africa"),
    ("MU", "🇲🇺 Mauritius"),
    ("KE", "🇰🇪 Kenya"),
]


def is_private_ip(ip: str) -> bool:
    try:
        return ip_address(ip).is_private
    except ValueError:
        return False


def get_allowed_countries(tenant_id: str, db: Session) -> list[str]:
    countries = db.query(AllowedCountry.country_code).filter(
        AllowedCountry.tenant_id == tenant_id
    ).all()
    return [c[0] for c in countries] if countries else ALLOWED_COUNTRIES_DEFAULT


def get_ip_metadata(ip: str) -> dict:
    try:
        res = requests.get(f"https://ipinfo.io/{ip}?token={IPINFO_TOKEN}", timeout=5)
        return res.json()
    except Exception:
        return {}


def log_login_event(user: User, ip: str, user_agent: str, db: Session):
    # Check if IP is new
    existing = db.query(LoginEvent).filter(
        LoginEvent.user_id == user.id,
        LoginEvent.ip_address == ip
    ).first()

    ip_info = get_ip_metadata(ip)
    country = ip_info.get("country", "Unknown")
    city = ip_info.get("city", "Unknown")
    region = ip_info.get("region", "Unknown")

    is_new = existing is None
    timestamp = datetime.utcnow()

    # Log login event
    login_event = LoginEvent(
        id=str(uuid4()),
        user_id=user.id,
        ip_address=ip,
        location=f"{city}, {region}",
        country=country,
        user_agent=user_agent,
        is_new_ip=is_new,
        created_at=timestamp
    )
    db.add(login_event)
    db.commit()

    # === Enforce Allowed Countries ===
    allowed = get_allowed_countries(str(user.tenant_id), db)

    if (
        is_new
        and country not in allowed
        and not is_private_ip(ip)
        and country != "Unknown"
        and not user.allow_new_region_login
    ):
        raise Exception(f"Login blocked from disallowed country: {country}")

    # === Notify Admin if enabled ===
    if is_new and user.allow_admin_alerts:
        send_template_email(
            db=db,
            to_email="admin@founderhub.ai",
            name="Admin",
            template_key="admin_login_alert",
            variables={
                "email": user.email,
                "ip": ip,
                "location": f"{city}, {region}"
            }
        )

    # === Notify User ===
    if is_new:
        send_template_email(
            db=db,
            to_email=user.email,
            name=user.name,
            template_key="new_login_detected",
            variables={
                "ip": ip,
                "location": f"{city}, {region}",
                "timestamp": timestamp.isoformat()
            }
        )

    return is_new
