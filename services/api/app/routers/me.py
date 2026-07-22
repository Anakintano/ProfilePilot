from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, status

from ..auth import CurrentUser, get_current_user
from ..db import get_pool

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.delete("/data", status_code=status.HTTP_200_OK)
def delete_my_data(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Deletes reports, extracted data, feedback linkage, uploads, and their
    on-disk objects. Retains only non-identifying aggregate counters
    (product_events rows are anonymized in place, not deleted, since they
    carry no PII once user_id is nulled)."""
    with get_pool().connection() as conn:
        upload_rows = conn.execute(
            "SELECT storage_key FROM uploads WHERE user_id = %s", (str(user.id),)
        ).fetchall()

        deleted_counts = {}
        # feedback, analysis_events, extracted_fields, analysis_uploads, jobs,
        # score_runs/items/recommendations all cascade via FK ON DELETE CASCADE
        # from analyses/uploads below.
        conn.execute("UPDATE product_events SET user_id = NULL WHERE user_id = %s", (str(user.id),))
        result = conn.execute("DELETE FROM analyses WHERE user_id = %s", (str(user.id),))
        deleted_counts["analyses"] = result.rowcount
        result = conn.execute("DELETE FROM uploads WHERE user_id = %s", (str(user.id),))
        deleted_counts["uploads"] = result.rowcount
        result = conn.execute("DELETE FROM goal_profiles WHERE user_id = %s", (str(user.id),))
        deleted_counts["goal_profiles"] = result.rowcount
        conn.commit()

    for row in upload_rows:
        path = Path(row["storage_key"])
        path.unlink(missing_ok=True)

    return {"deleted": deleted_counts}
