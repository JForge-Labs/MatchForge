#!/usr/bin/env python3
"""Upload job registry tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import upload_jobs


def test_job_lifecycle_and_ownership():
    job = upload_jobs.create_job(42, ["a.png", "b.png"])
    assert job["status"] == "queued"
    assert [f["stage"] for f in job["files"]] == ["queued", "queued"]

    # owner can fetch, others cannot
    assert upload_jobs.get_job(job["id"], 42) is job
    assert upload_jobs.get_job(job["id"], 99) is None
    assert upload_jobs.get_job("nonexistent", 42) is None

    upload_jobs.set_file_stage(job, 0, "done", profile_id=7, merged=True)
    assert job["files"][0] == {
        "name": "a.png",
        "stage": "done",
        "profile_id": 7,
        "merged": True,
        "error": None,
    }

    view = upload_jobs.public_view(job)
    assert "account_id" not in view
    assert view["id"] == job["id"]


def test_registry_prunes_to_cap():
    for i in range(upload_jobs._MAX_JOBS + 20):
        upload_jobs.create_job(1, [f"f{i}.png"])
    assert len(upload_jobs._JOBS) <= upload_jobs._MAX_JOBS


if __name__ == "__main__":
    test_job_lifecycle_and_ownership()
    test_registry_prunes_to_cap()
    print("All upload-job tests passed.")
