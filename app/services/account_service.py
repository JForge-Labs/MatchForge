"""Account lifecycle: deletion and cleanup."""
import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.profile import Profile
from app.models.user import UserProfile
logger = logging.getLogger(__name__)


def _unlink_upload(path_str: str | None) -> None:
    if not path_str:
        return
    path = Path(path_str)
    if path.is_file():
        path.unlink(missing_ok=True)


def _remove_account_upload_dir(account_id: int) -> None:
    upload_dir = Path("data/uploads/users") / str(account_id)
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)


def delete_account(db: Session, account_id: int) -> bool:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        return False

    user = (
        db.query(UserProfile).filter(UserProfile.account_id == account_id).first()
    )
    if user:
        _unlink_upload(user.avatar_path)
        _unlink_upload(user.selfie_path)

    for profile in db.query(Profile).filter(Profile.account_id == account_id).all():
        uploads = Path("data/uploads") / "profiles" / str(profile.id)
        if uploads.is_dir():
            shutil.rmtree(uploads, ignore_errors=True)

    _remove_account_upload_dir(account_id)

    db.delete(account)
    db.commit()
    logger.info("Deleted account id=%s email=%s", account_id, account.email)
    return True