import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.connected_account import SocialPlatform
from app.models.social_workflow import SocialWorkflowCopyMode, SocialWorkflowStatus
from app.models.social_workflow_run import SocialWorkflowRunStatus
from app.models.social_workflow_source_post import SocialWorkflowSourceStatus
from app.schemas.social import PublishJobResponse


class SocialWorkflowDestinationInput(BaseModel):
    platform: SocialPlatform
    connected_account_id: uuid.UUID


class SocialWorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_platform: SocialPlatform = SocialPlatform.instagram
    source_account_id: uuid.UUID
    copy_mode: SocialWorkflowCopyMode = SocialWorkflowCopyMode.both
    auto_publish: bool = True
    destinations: list[SocialWorkflowDestinationInput] = Field(min_length=1, max_length=12)


class SocialWorkflowPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: SocialWorkflowStatus | None = None
    copy_mode: SocialWorkflowCopyMode | None = None
    auto_publish: bool | None = None
    destinations: list[SocialWorkflowDestinationInput] | None = Field(default=None, min_length=1, max_length=12)


class SocialWorkflowAttachExportRequest(BaseModel):
    export_id: uuid.UUID


class SocialWorkflowRunResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    workflow_id: uuid.UUID
    status: SocialWorkflowRunStatus
    publish_job_ids_json: list[str]
    destination_results_json: dict
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SocialWorkflowSourcePostResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    workflow_id: uuid.UUID
    source_account_id: uuid.UUID | None
    source_platform: SocialPlatform
    external_post_id: str
    permalink: str | None
    caption_snapshot: str | None
    thumbnail_url: str | None
    published_at: datetime | None
    status: SocialWorkflowSourceStatus
    video_id: uuid.UUID | None
    export_id: uuid.UUID | None
    workflow_run_id: uuid.UUID | None
    error_message: str | None
    raw_metadata_json: dict
    created_at: datetime
    updated_at: datetime
    workflow_run: SocialWorkflowRunResponse | None = None
    publish_jobs: list[PublishJobResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SocialWorkflowResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    source_platform: SocialPlatform
    source_account_id: uuid.UUID | None
    status: SocialWorkflowStatus
    copy_mode: SocialWorkflowCopyMode
    auto_publish: bool
    destination_targets_json: list[dict]
    poll_cursor_json: dict
    last_polled_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    source_posts: list[SocialWorkflowSourcePostResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SocialWorkflowPollResponse(BaseModel):
    workflow_id: uuid.UUID
    enqueued: bool
    task_id: str | None = None


class SocialWorkflowAttachExportResponse(BaseModel):
    source_post_id: uuid.UUID
    export_id: uuid.UUID
    status: SocialWorkflowSourceStatus
