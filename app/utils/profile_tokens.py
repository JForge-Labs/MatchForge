"""Per-profile token spend for dashboard display."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.credits import CreditTransaction
from app.models.profile import Profile, ProfileEvidence


def evidence_token_total(profile: Profile) -> int:
    return sum((e.tokens_charged or 0) for e in (profile.evidence or []))


def profile_tokens_spent(profile: Profile, db: Session | None = None) -> int:
    """Total tokens invested in vetting this profile tile."""
    initial = int((profile.extracted_data or {}).get("tokens_spent") or 0)
    from_evidence = evidence_token_total(profile)
    if from_evidence or not db:
        return initial + from_evidence

    ledger = (
        db.query(func.coalesce(func.sum(-CreditTransaction.delta), 0))
        .filter(
            CreditTransaction.account_id == profile.account_id,
            CreditTransaction.delta < 0,
            CreditTransaction.metadata_json["profile_id"].astext == str(profile.id),
        )
        .scalar()
    )
    return initial + int(ledger or 0)