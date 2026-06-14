import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.connected_account import SocialPlatform
from app.models.social_workflow import WorkflowCopyMode, WorkflowRunStatus


class WorkflowDestinationInput(BaseModel):
    connected_account_id: uuid.UUID
    platform: SocialPlatform
    privacy: str | None = Field(default=None, max_length=64)


class WorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_account_id: uuid.UUID
    copy_mode: WorkflowCopyMode = WorkflowCopyMode.ai_platform
    destinations: list[WorkflowDestinationInput] = Field(min_length=1)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_unique_destinations(self):
        ids = [item.connected_account_id for item in self.destinations]
        if len(ids) != len(set(ids)):
            raise ValueError("Destination accounts must be unique")
        if self.source_account_id in ids:
            raise ValueError("The source account cannot also be a destination")
        return self


class WorkflowPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source_account_id: uuid.UUID | None = None
    copy_mode: WorkflowCopyMode | None = None
    destinations: list[WorkflowDestinationInput] | None = None
    enabled: bool | None = None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    source_account_id: uuid.UUID | None
    source_platform: SocialPlatform
    copy_mode: WorkflowCopyMode
    destination_configs: list[dict]
    enabled: bool
    cursor_json: dict
    last_checked_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    user_id: uuid.UUID
    source_publish_job_id: uuid.UUID | None
    source_export_id: uuid.UUID | None
    source_platform: SocialPlatform
    source_external_post_id: str
    source_external_url: str | None
    source_title: str | None
    source_description: str | None
    source_published_at: datetime | None
    status: WorkflowRunStatus
    generated_copy_json: dict
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]
    total: int


class WorkflowAttachExportRequest(BaseModel):
    export_id: uuid.UUID


class WorkflowSourceCapabilityResponse(BaseModel):
    connected_account_id: uuid.UUID
    platform: SocialPlatform
    status: str
    message: str | None = None
    missing_scopes: list[str] = Field(default_factory=list)
