"""
SiriusMail FastAPI MVP

This file defines the first version of the core API endpoints:

1. POST /campaigns
   Create a new email campaign.

2. GET /campaigns
   List campaigns for a workspace.

3. POST /campaigns/{campaign_id}/send
   Queue a campaign for sending.

4. GET /analytics
   Return basic campaign analytics.

In a real production app, database access would be split into repositories,
schemas into separate files, and sending would happen through SQS + workers.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, List


app = FastAPI(
    title="SiriusMail API",
    description="MVP backend for an email marketing platform.",
    version="0.1.0",
)


# -----------------------------
# Pydantic request/response models
# -----------------------------

class CampaignCreateRequest(BaseModel):
    """
    Request body for creating a campaign.

    audience_id:
        The audience this campaign will be sent to.

    name:
        Internal campaign name, visible to the SiriusMail user.

    subject:
        Email subject line.

    html_body:
        Final HTML email content.
    """
    workspace_id: UUID
    audience_id: UUID
    name: str
    subject: str
    from_name: str
    from_email: EmailStr
    html_body: str


class CampaignResponse(BaseModel):
    """
    API response for campaign data.
    """
    id: UUID
    workspace_id: UUID
    audience_id: UUID
    name: str
    subject: str
    status: str
    created_at: datetime


class SendCampaignResponse(BaseModel):
    """
    Response after a campaign is queued for sending.
    """
    campaign_id: UUID
    status: str
    queued_recipients: int
    message: str


class AnalyticsResponse(BaseModel):
    """
    Basic analytics for one campaign.
    """
    campaign_id: UUID
    sent: int
    delivered: int
    opened: int
    clicked: int
    bounced: int
    unsubscribed: int
    open_rate: float
    click_rate: float


# -----------------------------
# Temporary in-memory data
# Replace this with Postgres later
# -----------------------------

campaigns_db = {}
email_sends_db = []
email_events_db = []


# -----------------------------
# API Endpoints
# -----------------------------

@app.post("/campaigns", response_model=CampaignResponse)
def create_campaign(request: CampaignCreateRequest):
    """
    Create a new draft campaign.

    System design decision:
    - Creating a campaign does NOT send email.
    - Campaign creation and campaign sending are separate actions.
    - This prevents accidental sends and lets users preview/edit before launch.

    Production version:
    - Insert campaign into Postgres.
    - Validate workspace ownership.
    - Validate audience exists.
    - Store large assets/images in S3, not directly in the DB.
    """

    campaign_id = uuid4()

    campaign = {
        "id": campaign_id,
        "workspace_id": request.workspace_id,
        "audience_id": request.audience_id,
        "name": request.name,
        "subject": request.subject,
        "from_name": request.from_name,
        "from_email": request.from_email,
        "html_body": request.html_body,
        "status": "draft",
        "created_at": datetime.utcnow(),
    }

    campaigns_db[campaign_id] = campaign

    return CampaignResponse(
        id=campaign["id"],
        workspace_id=campaign["workspace_id"],
        audience_id=campaign["audience_id"],
        name=campaign["name"],
        subject=campaign["subject"],
        status=campaign["status"],
        created_at=campaign["created_at"],
    )


@app.get("/campaigns", response_model=List[CampaignResponse])
def list_campaigns(workspace_id: UUID):
    """
    List campaigns for a workspace.

    System design decision:
    - Campaigns belong to a workspace.
    - This makes the app multi-tenant from the beginning.
    - Later, the same workspace model can support teams, roles, and billing.

    Production version:
    - Query Postgres:
        SELECT * FROM campaigns
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC;
    """

    results = []

    for campaign in campaigns_db.values():
        if campaign["workspace_id"] == workspace_id:
            results.append(
                CampaignResponse(
                    id=campaign["id"],
                    workspace_id=campaign["workspace_id"],
                    audience_id=campaign["audience_id"],
                    name=campaign["name"],
                    subject=campaign["subject"],
                    status=campaign["status"],
                    created_at=campaign["created_at"],
                )
            )

    return results


@app.post("/campaigns/{campaign_id}/send", response_model=SendCampaignResponse)
def send_campaign(campaign_id: UUID):
    """
    Queue a campaign for sending.

    System design decision:
    - The API should NOT send all emails synchronously.
    - Instead, it validates the campaign, marks it as sending,
      creates send records, and pushes jobs to a queue.
    - A background worker then sends emails through AWS SES.

    Why?
    - Prevents API timeout.
    - Supports retries.
    - Reduces duplicate-send risk.
    - Allows scaling workers independently.
    """

    campaign = campaigns_db.get(campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign["status"] not in ["draft", "scheduled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign cannot be sent from status: {campaign['status']}",
        )

    # In real code, fetch contacts from Postgres by audience_id.
    # For MVP pseudocode, assume audience has 100 contacts.
    recipient_count = 100

    campaign["status"] = "sending"

    for _ in range(recipient_count):
        send_record = {
            "id": uuid4(),
            "campaign_id": campaign_id,
            "status": "queued",
            "created_at": datetime.utcnow(),
        }

        email_sends_db.append(send_record)

        # Production version:
        # sqs.send_message(
        #     QueueUrl=EMAIL_SEND_QUEUE_URL,
        #     MessageBody=json.dumps({
        #         "send_id": str(send_record["id"]),
        #         "campaign_id": str(campaign_id)
        #     })
        # )

    return SendCampaignResponse(
        campaign_id=campaign_id,
        status="sending",
        queued_recipients=recipient_count,
        message="Campaign has been queued for async sending.",
    )


@app.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(campaign_id: UUID):
    """
    Get basic campaign analytics.

    System design decision:
    - Email sends and email events are stored separately.
    - One email send can produce many events:
        opened once
        opened multiple times
        clicked multiple links
        bounced
        unsubscribed

    Production version:
    - Aggregate from Postgres using COUNT queries.
    - For very large scale, pre-aggregate analytics into summary tables.
    """

    campaign = campaigns_db.get(campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    sent = len([
        send for send in email_sends_db
        if send["campaign_id"] == campaign_id
        and send["status"] in ["sent", "queued"]
    ])

    delivered = len([
        send for send in email_sends_db
        if send["campaign_id"] == campaign_id
        and send["status"] == "sent"
    ])

    opened = len([
        event for event in email_events_db
        if event["campaign_id"] == campaign_id
        and event["event_type"] == "open"
    ])

    clicked = len([
        event for event in email_events_db
        if event["campaign_id"] == campaign_id
        and event["event_type"] == "click"
    ])

    bounced = len([
        event for event in email_events_db
        if event["campaign_id"] == campaign_id
        and event["event_type"] == "bounce"
    ])

    unsubscribed = len([
        event for event in email_events_db
        if event["campaign_id"] == campaign_id
        and event["event_type"] == "unsubscribe"
    ])

    open_rate = opened / delivered if delivered > 0 else 0
    click_rate = clicked / delivered if delivered > 0 else 0

    return AnalyticsResponse(
        campaign_id=campaign_id,
        sent=sent,
        delivered=delivered,
        opened=opened,
        clicked=clicked,
        bounced=bounced,
        unsubscribed=unsubscribed,
        open_rate=open_rate,
        click_rate=click_rate,
    )