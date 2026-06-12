import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.connected_account import ConnectedAccount
from app.models.export import Export, ExportStatus
from app.models.publish_attempt import PublishAttempt
from app.models.publish_job import PublishJob, PublishMode, PublishStatus
from app.services.crypto import decrypt_secret, encrypt_secret, encryption_available
from app.services.r2 import r2_client
from app.services.social.registry import get_adapter
from app.services.social.types import PublishPayload

logger = logging.getLogger(__name__)
X_REQUIRED_MEDIA_SCOPES = {"media.write"}
SCHEDULE_BATCH_SIZE = 50
STALE_QUEUED_AFTER = timedelta(minutes=5)


def _missing_x_media_scopes(scopes: list[str] | None) -> list[str]:
    present = {scope.strip().lower() for scope in (scopes or []) if isinstance(scope, str) and scope.strip()}
    return sorted(X_REQUIRED_MEDIA_SCOPES - present)


@celery_app.task(name="app.worker.tasks.publish.execute_publish_job", bind=True, queue="publish", max_retries=0)
def execute_publish_job(self, publish_job_id: str):
    logger.info("[publish] start publish_job_id=%s", publish_job_id)

    try:
        job_uuid = uuid.UUID(publish_job_id)
    except ValueError:
        logger.error("[publish] invalid publish_job_id=%s", publish_job_id)
        return {"publish_job_id": publish_job_id, "status": "failed", "error": "invalid id"}

    tmp_dir = Path(f"/tmp/clipbandit-publish/{publish_job_id}")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with SyncSessionLocal() as db:
        claimed_id = db.execute(
            update(PublishJob)
            .where(
                PublishJob.id == job_uuid,
                PublishJob.status == PublishStatus.queued,
            )
            .values(
                status=PublishStatus.publishing,
                error_message=None,
                updated_at=datetime.now(timezone.utc),
            )
            .returning(PublishJob.id)
        ).scalar_one_or_none()
        db.commit()
        if not claimed_id:
            current_status = db.scalar(
                select(PublishJob.status).where(PublishJob.id == job_uuid)
            )
            logger.info(
                "[publish] duplicate or ineligible delivery ignored publish_job_id=%s status=%s",
                publish_job_id,
                current_status,
            )
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {
                "publish_job_id": publish_job_id,
                "status": current_status.value if current_status else "missing",
                "duplicate": True,
            }

        publish_row = db.execute(
            select(PublishJob, ConnectedAccount, Export)
            .outerjoin(ConnectedAccount, PublishJob.connected_account_id == ConnectedAccount.id)
            .outerjoin(Export, PublishJob.export_id == Export.id)
            .where(PublishJob.id == job_uuid)
        ).first()

        if not publish_row:
            logger.error("[publish] publish job not found id=%s", publish_job_id)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"publish_job_id": publish_job_id, "status": "failed", "error": "publish job not found"}

        publish_job, account, export = publish_row
        if account is None:
            publish_job.status = PublishStatus.waiting_user_action
            publish_job.error_message = "Reconnect the destination account before publishing."
            db.commit()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {
                "publish_job_id": str(publish_job.id),
                "status": publish_job.status.value,
                "error": publish_job.error_message,
            }
        if export is None:
            publish_job.status = PublishStatus.failed
            publish_job.error_message = "The export asset was deleted before publishing."
            db.commit()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {
                "publish_job_id": str(publish_job.id),
                "status": publish_job.status.value,
                "error": publish_job.error_message,
            }

        attempt_number = (
            db.execute(select(PublishAttempt).where(PublishAttempt.publish_job_id == publish_job.id))
            .scalars()
            .all()
        )
        next_attempt = len(attempt_number) + 1

        attempt = PublishAttempt(
            publish_job_id=publish_job.id,
            attempt_number=next_attempt,
            started_at=datetime.now(timezone.utc),
            request_payload_json={
                "platform": publish_job.platform.value,
                "export_id": str(publish_job.export_id),
                "connected_account_id": str(publish_job.connected_account_id),
                "publish_mode": publish_job.publish_mode.value,
                "scheduled_for": publish_job.scheduled_for.isoformat() if publish_job.scheduled_for else None,
            },
        )
        db.add(attempt)

        db.commit()

        try:
            adapter = get_adapter(publish_job.platform)
            setup_status, setup_message = adapter.setup_status()
            setup_details = adapter.setup_details() if hasattr(adapter, "setup_details") else {}
            capabilities = adapter.capabilities()
            if not encryption_available() or setup_status != "ready":
                message = (
                    "SOCIAL_TOKEN_ENCRYPTION_KEY is not configured"
                    if not encryption_available()
                    else (setup_message or "Provider is not configured")
                )
                publish_job.status = PublishStatus.provider_not_configured
                publish_job.error_message = message
                publish_job.provider_metadata_json = {
                    **(publish_job.provider_metadata_json or {}),
                    "provider_setup": setup_details if isinstance(setup_details, dict) else {},
                }
                attempt.error_message = message
                attempt.finished_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "publish_job_id": str(publish_job.id),
                    "status": publish_job.status.value,
                    "error": message,
                }

            if export.status != ExportStatus.ready or not export.storage_key:
                raise RuntimeError("Export is not ready for publishing")

            if publish_job.platform.value == "x":
                missing_scopes = _missing_x_media_scopes(account.scopes)
                if missing_scopes:
                    message = "Reconnect X to grant media.write scope before posting media."
                    metadata = {
                        "stage": "preflight_permissions",
                        "reason": "missing_scope",
                        "action": "reconnect_x",
                        "missing_scopes": missing_scopes,
                        "account_scopes": account.scopes or [],
                    }
                    publish_job.status = PublishStatus.waiting_user_action
                    publish_job.error_message = message
                    publish_job.provider_metadata_json = {
                        **(publish_job.provider_metadata_json or {}),
                        **metadata,
                    }
                    attempt.response_payload_json = {
                        "status": publish_job.status.value,
                        "provider_metadata_json": metadata,
                    }
                    attempt.error_message = message
                    attempt.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    return {
                        "publish_job_id": str(publish_job.id),
                        "status": publish_job.status.value,
                        "error": message,
                    }

            media_path = tmp_dir / "export.mp4"
            r2_client.download_file(export.storage_key, str(media_path))
            media_url = r2_client.get_presigned_download_url(export.storage_key, expiry=3600)
            media_url_for_publish = media_url if capabilities.supports_video_upload else None

            access_token = decrypt_secret(account.access_token_encrypted)
            refresh_token = decrypt_secret(account.refresh_token_encrypted) if account.refresh_token_encrypted else None

            payload = PublishPayload(
                title=publish_job.title,
                description=publish_job.description,
                caption=publish_job.caption,
                hashtags=publish_job.hashtags,
                privacy=publish_job.privacy,
                scheduled_for=None,
                media_url=media_url_for_publish,
                destination_external_id=str(account.external_account_id),
                destination_metadata={
                    **(account.metadata_json or {}),
                    "scopes": account.scopes or [],
                },
            )

            result = adapter.publish(
                media_path=str(media_path),
                media_url=media_url_for_publish,
                payload=payload,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=account.token_expires_at,
            )

            if result.updated_access_token:
                account.access_token_encrypted = encrypt_secret(result.updated_access_token)
            if result.updated_refresh_token:
                account.refresh_token_encrypted = encrypt_secret(result.updated_refresh_token)
            if result.updated_token_expires_at:
                account.token_expires_at = result.updated_token_expires_at

            mapped_status = result.status if result.status in {status.value for status in PublishStatus} else "failed"
            publish_job.status = PublishStatus(mapped_status)
            publish_job.external_post_id = result.external_post_id
            publish_job.external_post_url = result.external_post_url
            publish_job.error_message = result.error_message
            publish_job.provider_metadata_json = {
                **(publish_job.provider_metadata_json or {}),
                **(result.provider_metadata_json or {}),
            }

            attempt.response_payload_json = {
                "status": result.status,
                "external_post_id": result.external_post_id,
                "external_post_url": result.external_post_url,
                "provider_metadata_json": result.provider_metadata_json,
            }
            attempt.error_message = result.error_message
            attempt.finished_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "publish_job_id": str(publish_job.id),
                "status": publish_job.status.value,
                "external_post_id": publish_job.external_post_id,
            }
        except Exception as exc:
            logger.exception("[publish] failed publish_job_id=%s error=%s", publish_job_id, exc)
            publish_job.status = PublishStatus.failed
            publish_job.error_message = str(exc)[:500]
            attempt.error_message = str(exc)[:500]
            attempt.finished_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "publish_job_id": str(publish_job.id),
                "status": publish_job.status.value,
                "error": publish_job.error_message,
            }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _dispatch_publish_job(db, publish_job: PublishJob, *, reason: str) -> str:
    task = execute_publish_job.apply_async(
        args=[str(publish_job.id)],
        queue="publish",
        countdown=1,
    )
    publish_job.provider_metadata_json = {
        **(publish_job.provider_metadata_json or {}),
        "celery_task_id": task.id,
        "dispatch_reason": reason,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
    }
    return task.id


@celery_app.task(
    name="app.worker.tasks.publish.process_scheduled_publish_jobs",
    queue="publish",
    max_retries=0,
)
def process_scheduled_publish_jobs():
    now = datetime.now(timezone.utc)
    dispatched = 0
    stale_redispatched = 0

    with SyncSessionLocal() as db:
        due_jobs = (
            db.execute(
                select(PublishJob)
                .where(
                    PublishJob.status == PublishStatus.scheduled,
                    PublishJob.scheduled_for.is_not(None),
                    PublishJob.scheduled_for <= now,
                )
                .order_by(PublishJob.scheduled_for.asc())
                .with_for_update(skip_locked=True)
                .limit(SCHEDULE_BATCH_SIZE)
            )
            .scalars()
            .all()
        )
        for publish_job in due_jobs:
            publish_job.status = PublishStatus.queued
            publish_job.error_message = None
            publish_job.provider_metadata_json = {
                **(publish_job.provider_metadata_json or {}),
                "scheduler_due_at": now.isoformat(),
            }
        db.commit()

        for publish_job in due_jobs:
            _dispatch_publish_job(db, publish_job, reason="schedule_due")
            dispatched += 1
        if due_jobs:
            db.commit()

        stale_cutoff = now - STALE_QUEUED_AFTER
        stale_jobs = (
            db.execute(
                select(PublishJob)
                .where(
                    PublishJob.status == PublishStatus.queued,
                    PublishJob.publish_mode == PublishMode.scheduled,
                    PublishJob.scheduled_for.is_not(None),
                    PublishJob.scheduled_for <= now,
                    PublishJob.updated_at <= stale_cutoff,
                )
                .order_by(PublishJob.updated_at.asc())
                .with_for_update(skip_locked=True)
                .limit(SCHEDULE_BATCH_SIZE)
            )
            .scalars()
            .all()
        )
        for publish_job in stale_jobs:
            _dispatch_publish_job(db, publish_job, reason="stale_queued_recovery")
            publish_job.updated_at = now
            stale_redispatched += 1
        if stale_jobs:
            db.commit()

    logger.info(
        "[publish_scheduler] complete due_dispatched=%s stale_redispatched=%s",
        dispatched,
        stale_redispatched,
    )
    return {
        "due_dispatched": dispatched,
        "stale_redispatched": stale_redispatched,
    }
