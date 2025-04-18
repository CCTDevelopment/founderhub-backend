from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.db import get_sync_db
from app.models.user import User
from app.services.email import send_template_email

def check_inactive_users():
    db: Session = get_sync_db()
    cutoff = datetime.utcnow() - timedelta(days=3)  # or 7

    users = db.query(User).filter(
        User.last_login_at < cutoff,
        User.is_admin == False
    ).all()

    for user in users:
        send_template_email(
            to_email=user.email,
            name=user.name,
            template_key="inactivity_reminder",
            db=db,
            user_id=str(user.id)
        )
        print(f"📬 Sent inactivity reminder to {user.email}")

    db.close()
