import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from src.database.models import (
    Base,
    Company,
    Contact,
    OutreachMessage,
    FollowUp,
    Campaign,
    OutreachStatus,
    MessageChannel
)
from src.database.crud import CRUDOperations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FollowUpSchedule(Enum):
    NONE = 0
    FIRST_FOLLOWUP = 7
    SECOND_FOLLOWUP = 14
    THIRD_FOLLOWUP = 21

@dataclass
class OutreachStats:
    total_sent: int
    total_replied: int
    total_no_response: int
    total_rejected: int
    reply_rate: float
    avg_response_time_hours: Optional[float]
    pending_followups: int

@dataclass
class TrackingResult:
    success: bool
    message_id: Optional[int]
    followup_scheduled: bool
    next_followup_date: Optional[datetime]
    error: Optional[str]

class TrackingAgent:
    def __init__(self, 
        db_path: str = "data/outreach.db",
        auto_schedule_followups: bool = True,
        default_followup_days: int = 7
    ):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.crud = CRUDOperations(self.engine)
        self.auto_schedule_followups = auto_schedule_followups
        self.default_followup_days = default_followup_days

    def track_outreach(
            self,
            company_name: str,
            company_url: str,
            contact_name: Optional[str],
            contact_email: Optional[str],
            message_text: str,
            channel: MessageChannel,
            target_role: str,
            campaign_name: Optional[str] = None,
            metadata: Optional[Dict] = None,
    ) -> TrackingResult:
        if not company_name or len(company_name.strip()) < 2:
            return TrackingResult(
                success=False,
                message_id=None,
                followup_scheduled=False,
                next_followup_date=None,
                error="Invalid company_name"
            )
        
        if not message_text or len(message_text.strip()) < 10:
            return TrackingResult(
                success=False,
                message_id=None,
                followup_scheduled=False,
                next_followup_date=None,
                error="Invalid message_text"
            )
        
        try:
            company = self.crud.get_company_by_name(company_name)
            if not company:
                company = self.crud.create_company(
                    name=company_name,
                    website=company_url,
                    industry=None,
                    size=None,
                    metadata=metadata or {}
                )
                logger.info(f"Created new company: {company_name}")

            contact = None
            if contact_name or contact_email:
                contact = self.crud.create_contact(
                    company_id=company.id,
                    name=contact_name,
                    email=contact_email,
                    title=target_role,
                    linkedin_url=None
                )
                logger.info(f"Created new contact: {contact_name or contact_email}")

            campaign = None
            if campaign_name:
                campaign = self.crud.get_campaign_by_name(campaign_name)
                if not campaign:
                    campaign = self.crud.create_campaign(
                        name=campaign_name,
                        description=f"Outreach for {target_role} positions",
                        start_date=datetime.utcnow()
                    )

            message = self.crud.create_outreach_message(
                company_id = company.id,
                contact_id = contact.id if contact else None,
                campaign_id = campaign.id if campaign else None,
                message_text = message_text,
                channel = channel,
                status = OutreachStatus.SENT,
                target_role = target_role
            )

            logger.info(
                f"Tracked outreach: {company_name} - {channel.value} "
                f"(ID: {message.id})"
            )
            
            next_followup_date = None
            followup_scheduled = False

            if self.auto_schedule_followups:
                next_followup_date = datetime.utcnow() + timedelta(
                    days=self.default_followup_days
                )
                
                followup = self.crud.create_followup(
                    message_id=message.id,
                    scheduled_date=next_followup_date,
                    followup_number=1
                )
                
                if followup:
                    followup_scheduled = True
                    logger.info(
                        f"Scheduled follow-up for {next_followup_date.date()}"
                    )
            
            return TrackingResult(
                success=True,
                message_id=message.id,
                followup_scheduled=followup_scheduled,
                next_followup_date=next_followup_date,
                error=None
            )
        
        except Exception as e:
            logger.error(f"Failed to track outreach: {e}")
            return TrackingResult(
                success=False,
                message_id=None,
                followup_scheduled=False,
                next_followup_date=None,
                error=str(e)
            )
        
    def update_message_status(
        self,
        message_id: int,
        new_status: OutreachStatus,
        response_text: Optional[str] = None
    ) -> bool:
        try:
            message = self.crud.get_outreach_message(message_id)

            if not message:
                logger.warning(f'Message {message_id} not found.')
                return False
            
            message.status = new_status
            message.updated_at = datetime.utcnow()
            if new_status == OutreachStatus.REPLIED and response_text:
                message.reply_content  = response_text
                message.replied_at = datetime.utcnow()
                if message.sent_date:
                    response_time = message.replied_at - message.sent_at
                    message.response_time_hours = response_time.total_seconds() / 3600

            self.crud.session.commit()
            logger.info(f"Updated message {message_id} status to {new_status.value}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update message status: {e}")
            self.crud.session.rollback()
            return False
        
    def get_pending_followups(self, days_ahead: int = 7) -> List[FollowUp]:
        try:
            end_date = datetime.utcnow() + timedelta(days=days_ahead)
            followups = self.crud.session.query(FollowUp).filter(
                FollowUp.scheduled_date <= end_date,
                FollowUp.completed == False
            ).order_by(FollowUp.scheduled_date).all()

            logger.info(f"Found {len(followups)} pending follow-ups")
            return followups
            
        except Exception as e:
            logger.error(f"Failed to get pending follow-ups: {e}")
            return []
        
    def complete_followup(
        self,
        followup_id: int,
        notes: Optional[str] = None,
        schedule_next: bool = True
    ) -> bool:
        try:
            followup = self.crud.session.query(FollowUp).get(followup_id)

            if not followup:
                logger.warning(f"Follow-up {followup_id} not found.")
                return False
            
            followup.completed = True
            followup.completed_date = datetime.utcnow()
            if notes:
                followup.notes = notes
            if schedule_next and followup.followup_number < 3:
                next_date = datetime.utcnow() + timedelta(
                    days=self.default_followup_days
                )
                
                next_followup = self.crud.create_followup(
                    message_id=followup.message_id,
                    scheduled_date=next_date,
                    followup_number=followup.followup_number + 1
                )

                if next_followup:
                    logger.info(
                        f"Scheduled follow-up #{next_followup.followup_number} "
                        f"for {next_date.date()}"
                    )
            
            self.crud.session.commit()
            logger.info(f"Completed follow-up {followup_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to complete follow-up: {e}")
            self.crud.session.rollback()
            return False
        
    def get_outreach_stats(
        self,
        company_id: Optional[int] = None,
        campaign_id: Optional[int] = None,
        days_back: Optional[int] = None,
    ) -> OutreachStats:
        try:
            query = self.crud.session.query(OutreachMessage)
            if company_id:
                query = query.filter(OutreachMessage.company_id == company_id)
            if campaign_id: 
                query = query.filter(OutreachMessage.campaign_id == campaign_id)

            if days_back:
                cutoff_date = datetime.utcnow() - timedelta(days=days_back)
                query = query.filter(OutreachMessage.sent_at >= cutoff_date)

            messages = query.all()

            total_sent = len(messages)
            total_replied = sum(1 for m in messages if m.status == OutreachStatus.REPLIED)
            total_no_response = sum(1 for m in messages if m.status == OutreachStatus.NO_RESPONSE)
            total_rejected = sum(1 for m in messages if m.status == OutreachStatus.NOT_INTERESTED)
            reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0.0

            response_times = [m.response_time_hours for m in messages if m.response_time_hours is not None]
            avg_response_time = (sum(response_times) / len(response_times)) if response_times else None
            avg_response_time_hours=avg_response_time,
            pending_followups_count = self.crud.session.query(FollowUp).filter(
                FollowUp.completed == False
            ).count()
            
            return OutreachStats(
                total_sent=total_sent,
                total_replied=total_replied,
                total_no_response=total_no_response,
                total_rejected=total_rejected,
                reply_rate=reply_rate,
                pending_followups=pending_followups_count,
                avg_response_time_hours=avg_response_time
            )
        
        except Exception as e:
            logger.error(f"Failed to get outreach stats: {e}")
            return OutreachStats(
                total_sent=0,
                total_replied=0,
                total_no_response=0,
                total_rejected=0,
                reply_rate=0.0,
                pending_followups=0,
                avg_response_time_hours=0.0
            )
        
    def get_all_messages(
        self, 
        status: Optional[OutreachStatus] = None,
        limit: int = 100
    ) -> List[OutreachMessage]:
        try:
            query = self.crud.session.query(OutreachMessage)
            
            if status:
                query = query.filter(OutreachMessage.status == status)
            
            messages = query.order_by(
                OutreachMessage.sent_at.desc()
            ).limit(limit).all()
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []


def track_new_outreach(
    company_name: str,
    company_url: str,
    message_text: str,
    channel: str = "linkedin_message",
    target_role: str = "Software Engineer",
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    db_path: str = "data/outreach.db"
) -> TrackingResult:
    
    try:
        channel_enum = MessageChannel[channel.upper()]
    except KeyError:
        raise ValueError(
            f"Invalid channel: {channel}. "
            f"Valid options: {[c.name.lower() for c in MessageChannel]}"
        )
    
    agent = TrackingAgent(db_path=db_path)
    
    return agent.track_outreach(
        company_name=company_name,
        company_url=company_url,
        contact_name=contact_name,
        contact_email=contact_email,
        message_text=message_text,
        channel=channel_enum,
        target_role=target_role
    )



