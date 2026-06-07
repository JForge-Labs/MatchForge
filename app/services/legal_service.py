"""Record and verify Terms & Privacy acceptance."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import UserProfile
from app.services import onboarding_service
from app.utils.legal import POLICIES_VERSION, policies_accepted


def accept_policies(db: Session, account_id: int) -> UserProfile:
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    user.policies_accepted_at = datetime.now(timezone.utc)
    user.policies_version = POLICIES_VERSION
    db.commit()
    db.refresh(user)
    return user


def require_policies_message() -> str:
    return (
        "Accept the Terms of Service and Privacy Policy at /legal/accept "
        "before using MatchForge's safety and due diligence tools."
    )