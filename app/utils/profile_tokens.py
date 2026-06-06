"""Per-profile token spend for dashboard display."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.credits import CreditTransaction
from app.models.profile import Profile, ProfileEvidence


def evidence_token_total(profile) -> int:
    evidence = getattr(profile, "evidence", None)
    if evidence is not None:
        return sum((e.tokens_charged or 0) for e in evidence)
    return 0


def profile_tokens_spent(profile, db: Session | None = None) -> int:
    """Total tokens invested in vetting this profile tile."""
    extracted = getattr(profile, "extracted_data", None) or {}
    initial = int(extracted.get("tokens_spent") or 0)
    from_evidence = evidence_token_total(profile)
    if from_evidence:
        return initial + from_evidence
    if not db:
        return initial

    profile_id = getattr(profile, "id", None)
    account_id = getattr(profile, "account_id", None)
    if profile_id is None or account_id is None:
        return initial

    evidence_sum = (
        db.query(func.coalesce(func.sum(ProfileEvidence.tokens_charged), 0))
        .filter(ProfileEvidence.profile_id == profile_id)
        .scalar()
    )
    if evidence_sum:
        return initial + int(evidence_sum)

    ledger = (
        db.query(func.coalesce(func.sum(-CreditTransaction.delta), 0))
        .filter(
            CreditTransaction.account_id == account_id,
            CreditTransaction.delta < 0,
            CreditTransaction.metadata_json["profile_id"].astext == str(profile_id),
        )
        .scalar()
    )
    return initial + int(ledger or 0)