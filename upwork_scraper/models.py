from pydantic import BaseModel, Field
from datetime import datetime, timezone


class JobLead(BaseModel):
    """A single scraped job listing from any platform."""

    title: str
    company_client: str = ""
    platform: str = ""
    location: str = ""
    job_type: str = ""
    budget: str = ""
    posted_date: str = ""
    url: str = ""
    description: str = ""
    skills_required: str = ""
    experience_level: str = ""
    country: str = ""
    valid_job: str = "Yes"
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    job_id: str = ""
    keyword_searched: str = ""
