from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import and_, or_, desc, func
import logging

from .models import (
    Company,
    Contact,
    OutreachMessage,
    FollowUp,
    Campaign,
    OutreachStatus,
    MessageChannel,
    ReplyCategory
)
from src.utils.validators import (
    validate_url,
    validate_email,
    validate_company_name,
    validate_contact_data,
    ValidationError
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CompanyCRUD:
    """
    CRUD operations for Company model
    """

    @staticmethod
    def create(session: Session, name: str, url: str, domain: Optional[str]=None, mission: Optional[str]=None, about_text: Optional[str]=None,
               news_text: Optional[str] = None, careers_text: Optional[str]=None, team_text: Optional[str]=None, scrape_success_count: int=0,
               scrape_failed_pages: Optional[str] = None, notes: Optional[str] = None) -> Optional[Company]:
        """
        Create a new company record with validation
        """
        try:
            # validate company name
            is_valid, error = validate_company_name(name)
            if not is_valid:
                logger.error(f"Invalid company name: {error}")
                return None

            # validate URL
            is_valid, error = validate_url(url)
            if not is_valid:
                logger.error(f"Invalid company URL: {error}")
                return None

            company = Company(name=name.strip(), 
                            url = url.strip(),
                            domain = domain.strip() if domain else None,
                            mission = mission,
                            about_text = about_text, 
                            careers_text = careers_text, 
                            news_text = news_text,
                            team_text = team_text, 
                            scrape_success_count = scrape_success_count,
                            scrape_failed_pages = scrape_failed_pages,
                            notes = notes)
            session.add(company)
            session.commit()
            session.refresh(company)

            logger.info(f'Created company: {company.name} (ID: {company.id})')
            return company
        
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Company with URL: {url} already exists: {e}")
            return None
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database error creating company: {e}")
            return None
        
    @staticmethod
    def get_by_id(session: Session, company_id: int) -> Optional[Company]:
        """
        Get company by ID
        """
        try: 
            return session.query(Company).filter(Company.id == company_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching company {company_id}: {e}")
            return None
        
    @staticmethod
    def get_by_url(session: Session, url: str) -> Optional[Company]:
        """
        Get company by URL
        """
        try:
            return session.query(Company).filter(Company.url == url.strip()).first()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching company by URL {url}: {e}")
            return None
    
    @staticmethod
    def update(session: Session, company_id: int, **kwargs) -> Optional[Company]:
        """
        Update company fields
        """
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                logger.warning(f"Company {company_id} not found for update")
                return None
            for key, value in kwargs.items():
                if hasattr(company, key):
                    setattr(company, key, value)

            company.last_updated = datetime.utcnow()
            session.commit()
            session.refresh(company)
            logger.info(f"Updated company {company_id}")
            return company
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error updating company {company_id}: {e}")
            return None
        
    @staticmethod
    def list_active(session: Session, limit: int=100, offset: int = 0) -> List[Company]:
        """
        List active companies
        """
        try:
            return session.query(Company).filter(Company.is_active == True).order_by(desc(Company.last_updated)).limit(limit).offset(offset).all()
        
        except SQLAlchemyError as e:
            logger.error(f"Error listing companies: {e}")
            return []
        
    @staticmethod
    def delete(session: Session, company_id: int) -> bool:
        """
        Soft delete company
        """
        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                return False
            
            company.is_active = False
            session.commit()

            logger.info(f"Deleted company {company_id}")
            return True
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error deleting company {company_id}: {e}")
            return False
        
class ContactCRUD:
    """
    CRUD operations for Contact model
    """
    def create(session: Session,
               company_id: int,
               name: Optional[str] = None,
               title: Optional[str] = None,
               email: Optional[str] = None,
               linkedin_url: Optional[str] = None,
               x_handle: Optional[str] = None,
               is_primary: bool = False,
               notes: Optional[str] = None) -> Optional[Contact]:
        """
        Create a new contact with validation
        """
        try:
            # validate contact data
            all_valid, errors = validate_contact_data(
                name=name,
                email=email,
                linkedin_url=linkedin_url,
                title=title
            )

            if not all_valid:
                for error in errors:
                    logger.error(f"Invalid contact data: {error}")
                return None

            contact = Contact(
                company_id=company_id,
                name=name.strip() if name else None,
                title=title.strip() if title else None,
                email=email.strip().lower() if email else None,
                linkedin_url=linkedin_url.strip() if linkedin_url else None,
                x_handle=x_handle.strip() if x_handle else None,
                is_primary=is_primary,
                notes=notes
            )

            session.add(contact)
            session.commit()
            session.refresh(contact)
            logger.info(f"Created contact: {contact.name} (ID: {contact.id})")
            return contact
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error creating contact: {e}")
            return None
    
    @staticmethod
    def get_by_company(
        session: Session,
        company_id: int, 
        active_only: bool = True
    ) -> List[Contact]:
        """
        Get all contacts for a company
        """
        try:
            query = session.query(Contact).filter(Contact.company_id == company_id)
            if active_only: 
                query = query.filter(Contact.is_active == True)

            return query.order_by(desc(Contact.is_primary)).all()
    
        except SQLAlchemyError as e:
            logger.error(f"Error fetching contacts for company {company_id}: {e}")
            return []
        
    
    @staticmethod
    def update_last_contacted(
        session: Session,
        contact_id: int,
    ) -> bool:
        """
        Update last contacted timestamp
        """
        try: 
            contact = session.query(Contact).filter(Contact.id == contact_id).first()
            if not contact:
                return False
            
            contact.last_contacted = datetime.utcnow()
            session.commit()
            return True
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error updating contact {contact_id}: {e}")
            return False
        
class OutreachMessageCRUD:
    """
    CRUD operations for OutreachMessage model
    """
    @staticmethod
    def create(
        session: Session,
        company_id: int,
        target_role: str,
        channel: MessageChannel,
        message_content: str,
        contact_id: Optional[int] = None,
        message_variant: int = 1,
        tone: Optional[str] = None,
        subject_line: Optional[str] = None,
        guardrails_passed: bool = False,
        guardrails_issues: Optional[str] = None,
        citations: Optional[str] = None,
        notes: Optional[str] = None,
        message_metadata: Optional[str] = None
    ) -> Optional[OutreachMessage]:
        """
        Create a new outreach message
        """
        try: 
            message = OutreachMessage(
                company_id=company_id,
                contact_id=contact_id,
                target_role=target_role.strip(),
                channel=channel,
                message_content=message_content.strip(),
                message_variant=message_variant,
                tone=tone,
                subject_line=subject_line.strip() if subject_line else None,
                guardrails_passed=guardrails_passed,
                guardrails_issues=guardrails_issues,
                citations=citations,
                notes=notes,
                message_metadata=message_metadata
            )
            session.add(message)
            session.commit()
            session.refresh(message)

            logger.info(f"Created outreach message (ID: {message.id})")
            return message
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error creating outreach message: {e}")
            return None
        
    @staticmethod
    def mark_sent(
        session: Session,
        message_id: int
    ) -> bool:
        """
        Mark message as sent
        """
        try: 
            message = session.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
            if not message:
                return False
            
            message.status = OutreachStatus.SENT
            message.sent_at = datetime.utcnow()
            if message.contact_id:
                ContactCRUD.update_last_contacted(session, message.contact_id)
            session.commit()
            logger.info(f"Marked message {message_id} as sent")
            return True
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error marking message {message_id}: {e}")
            return None
        
    @staticmethod
    def record_reply(
        session: Session,
        message_id: int, 
        reply_content: str,
        reply_category: Optional[ReplyCategory] = None,
        reply_sentiment_score: Optional[float] = None
    ) -> bool:
        """
        Record a reply to an outreach message
        """
        try: 
            message = session.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
            if not message:
                return False
            
            message.status = OutreachStatus.REPLIED
            message.replied_at = datetime.utcnow()
            message.reply_content = reply_content.strip()
            message.reply_category = reply_category
            message.reply_sentiment_score = reply_sentiment_score

            session.commit()
            logger.info(f'Recorded reply for message {message_id}')
            return True
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f'Error recording reply for message {message_id}: {e}')
            return False
        
    @staticmethod
    def schedule_follow(
        session: Session,
        message_id: int,
        days_from_now: int = 7
    ):
        """
        Schedule a follow-up for a message
        """
        try:
            message = session.query(OutreachMessage).filter(
                OutreachMessage.id == message_id
            ).first()
            
            if not message:
                return False
            
            message.next_followup_scheduled = datetime.utcnow() + timedelta(days=days_from_now)
            message.status = OutreachStatus.FOLLOW_UP_SCHEDULED
            
            session.commit()
            logger.info(f"Scheduled follow-up for message {message_id}")
            return True
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error scheduling follow-up for message {message_id}: {e}")
            return False
        
    @staticmethod
    def get_by_status(
        session: Session,
        status: OutreachStatus,
        limit: int = 100
    ) -> List[OutreachMessage]:
        """
        Get messages by status
        """
        try:
            return session.query(OutreachMessage)\
                .filter(OutreachMessage.status == status)\
                .order_by(desc(OutreachMessage.created_at))\
                .limit(limit)\
                .all()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching messages by status: {e}")
            return []
    
    @staticmethod
    def get_pending_followups(session: Session) -> List[OutreachMessage]:
        """
        Get messages with follow-ups due
        """
        try:
            now = datetime.utcnow()
            return session.query(OutreachMessage)\
                .filter(
                    and_(
                        OutreachMessage.status == OutreachStatus.FOLLOW_UP_SCHEDULED,
                        OutreachMessage.next_followup_scheduled <= now
                    )
                )\
                .order_by(OutreachMessage.next_followup_scheduled)\
                .all()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching pending follow-ups: {e}")
            return []
    
    @staticmethod
    def get_statistics(session: Session) -> Dict[str, Any]:
        """
        Get outreach statistics
        """
        try:
            total = session.query(func.count(OutreachMessage.id)).scalar()
            sent = session.query(func.count(OutreachMessage.id))\
                .filter(OutreachMessage.status == OutreachStatus.SENT)\
                .scalar()
            replied = session.query(func.count(OutreachMessage.id))\
                .filter(OutreachMessage.status == OutreachStatus.REPLIED)\
                .scalar()
            interested = session.query(func.count(OutreachMessage.id))\
                .filter(OutreachMessage.reply_category == ReplyCategory.INTERESTED)\
                .scalar()
            
            return {
                'total_messages': total or 0,
                'sent': sent or 0,
                'replied': replied or 0,
                'interested': interested or 0,
                'response_rate': round((replied / sent * 100), 2) if sent > 0 else 0.0,
                'interest_rate': round((interested / replied * 100), 2) if replied > 0 else 0.0
            }
        except SQLAlchemyError as e:
            logger.error(f"Error calculating statistics: {e}")
            return {
                'total_messages': 0,
                'sent': 0,
                'replied': 0,
                'interested': 0,
                'response_rate': 0.0,
                'interest_rate': 0.0
            }


class FollowUpCRUD:
    """
    CRUD operations for FollowUp model
    """
    
    @staticmethod
    def create(
        session: Session,
        original_message_id: int,
        sequence_number: int,
        message_content: str,
        scheduled_at: datetime,
        notes: Optional[str] = None
    ) -> Optional[FollowUp]:
        """
        Create a follow up message
        """
        try:
            followup = FollowUp(
                original_message_id=original_message_id,
                sequence_number=sequence_number,
                message_content=message_content.strip(),
                scheduled_at=scheduled_at,
                notes=notes
            )
            
            session.add(followup)
            session.commit()
            session.refresh(followup)
            
            logger.info(f"Created follow up (ID: {followup.id})")
            return followup
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error creating follow up: {e}")
            return None
        
    @staticmethod
    def get_by_message(
        session: Session,
        message_id: int
    ) -> List[FollowUp]:
        """Get all follow-ups for a message"""
        try:
            return session.query(FollowUp)\
                .filter(FollowUp.original_message_id == message_id)\
                .order_by(FollowUp.sequence_number)\
                .all()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching follow-ups for message {message_id}: {e}")
            return []


class CampaignCRUD:
    """
    CRUD operations for Campaign model
    """
    
    @staticmethod
    def create(
        session: Session,
        name: str,
        target_role: str,
        description: Optional[str] = None,
        resume_hash: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[Campaign]:
        """
        Create a new campaign
        """
        try:
            campaign = Campaign(
                name=name.strip(),
                description=description,
                target_role=target_role.strip(),
                resume_hash=resume_hash,
                notes=notes
            )
            
            session.add(campaign)
            session.commit()
            session.refresh(campaign)
            
            logger.info(f"Created campaign: {campaign.name} (ID: {campaign.id})")
            return campaign
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error creating campaign: {e}")
            return None
    
    @staticmethod
    def update_stats(
        session: Session,
        campaign_id: int
    ) -> bool:
        """
        Recalculate campaign statistics
        """
        try:
            campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
            
            if not campaign:
                return False
            
            stats = OutreachMessageCRUD.get_statistics(session)
            campaign.total_sent = stats['sent']
            campaign.total_replied = stats['replied']
            campaign.total_interested = stats['interested']
            
            session.commit()
            return True
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error updating campaign {campaign_id} stats: {e}")
            return False

