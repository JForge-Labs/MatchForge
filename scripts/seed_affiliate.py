#!/usr/bin/env python3
"""Create an affiliate partner record."""
import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.services import affiliate_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed an affiliate partner")
    parser.add_argument("--slug", required=True, help="URL slug for ?aff= links")
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--email", required=True, help="Contact email")
    parser.add_argument("--rate", type=float, default=0.15, help="Commission rate (default 0.15)")
    parser.add_argument("--notes", default=None, help="Internal notes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        affiliate = affiliate_service.create_affiliate(
            db,
            slug=args.slug,
            name=args.name,
            contact_email=args.email,
            commission_rate=Decimal(str(args.rate)),
            notes=args.notes,
        )
        db.commit()
        url = affiliate_service.build_affiliate_url(
            affiliate_service.ensure_link_code(db, affiliate)
        )
        print(f"Created affiliate id={affiliate.id} slug={affiliate.slug}")
        print(f"Link: {url}")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
