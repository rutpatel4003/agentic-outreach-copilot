from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import enum

Base = declarative_base()

class OutreachStatus(enum.Enum):
    """
    Status of outreach attempt
    """
    DRAFT = 'draft'
    SENT = 'sent'
    REPLIED = 'replied'
    NO_RESPONSE = 'no_response'
    FOLLOW_UP_SCHEDULED = 'follow_uo_scheduled'
    BOUNCED = 'bounced'
    INTERESTED = 'interested'
    NOT_INTERESTED = 'not_interested'
    CLOSED = 'closed'

class MessageChannel(enum.Enum):
    """
    Communication channel
    """
    LINKED_CONNECTION = 'linkedin_connection'
    LINKEDIN_MESSAGE = 'linkedin_message'
    EMAIL = 'email'
    X = 'x'
    OTHER = 'other'

class ReplyCategory(enum.Enum):
    """
    Classification of reply sentiment
    """
    INTERESTED = 'interested'
    NOT_INTERESTED = 'not_interested'
    NEEDS_INFO = 'needs_info'
    OUT_OF_OFFICE = 'out_of_office'
    SPAM = 'spam'
    UNKNOWN = 'unknown'

class Company(Base):
    """
    Company information scraped from the website
    """
    __tablename_ = 'companies'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(512), nullable=False, unique=True)
    domain = Column(String(255), nullabel=True, index=True)
    mission = Column(Text, nullable=True)
    about_text = Column(Text, nullable=True)
    careers_text = Column(Text, nullable=True)
    news_text = Column(Text, nullable=True)
    team_text = Column(Text, nullable=True)

    scraped_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    scrape_success_count = Column(Integer, default=0)
    scrape_failed_pages = Column(Text, nullable=True)
    
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    
    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    outreach_messages = relationship("OutreachMessage", back_populates="company", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}', url='{self.url}')>"

class Contact(Base):
    """
    Contact person at company
    """
    __tablename__ = 'contacts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    linkedin_url = Column(String(512), nullable=True)
    x_handle = Column(String(100), nullable=True)
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_contacted = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    company = relationship("Company", back_populates='contacts')
    outreach_messages = relationship('OutreachMessage', back_populates='contact', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Contact(id={self.id}, name='{self.name}', title='{self.title}')>"
    
class OutreachMessage(Base):
    """
    Individual outreach message sent to a contact
    """
    __tablename__ = 'outreach_messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=True, index=True)  
    target_role = Column(String(255), nullable=False)
    channel = Column(SQLEnum(MessageChannel), nullable=False, index=True)
    status = Column(SQLEnum(OutreachStatus), nullable=False, default=OutreachStatus.DRAFT, index=True)
    message_content = Column(Text, nullable=False)
    message_variant = Column(Integer, default=1)
    tone = Column(String(50), nullable=True)
    subject_line = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    last_followed_up = Column(DateTime, nullable=True)
    next_followup_scheduled = Column(DateTime, nullable=True)
    reply_content = Column(Text, nullable=True)
    reply_category = Column(SQLEnum(ReplyCategory), nullable=True)
    reply_sentiment_score = Column(Float, nullable=True)
    guardrails_passed = Column(Boolean, default=False)
    guardrails_issues = Column(Text, nullable=True)
    citations = Column(Text, nullable=True)
    open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    notes = Column(Text, nulable=True)
    metadata = Column(Text, nullable=True)
    company = relationship("Company", back_populates='outreach_messages')
    contact = relationship('Contact', back_populates='outreach_messages')
    follow_ups = relationship('FollowUp', back_populates='original_message', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<OutreachMessage(id={self.id}, status='{self.status.value}', channel='{self.channel.value}')>"
    
class FollowUp(Base):
    """
    Follow-up messages for an original outreach
    """
    id = Column(Integer, primary_key=True, autoincrement=True)
    original_message_id = Column(Integer, ForeignKey('outreach_messages.id'), nullable=False, index=True)
    sequence_number = Column(Integer, nullable=False)
    message_content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    status = Column(SQLEnum(OutreachStatus), nullable=False, default=OutreachStatus.DRAFT)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
    original_memssage = relationship('OutreachMessage', back_populates='follow_ups')

    def __repr__(self):
        return f"<FollowUp(id={self.id}, sequence={self.sequence_number}, status='{self.status.value}')>"
    
class Campaign(Base):
    """
    Outreach campaign grouping multiple messages
    """
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    target_role = Column(String(255), nullable=False)
    resume_hash = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    total_sent = Column(Integer, default=0)
    total_replied = Column(Integer, default=0)
    total_interested = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<Campaign(id={self.id}, name='{self.name}', active={self.is_active})>"
    
def create_database(database_url: str="sqlite:///data/outreach.db"):
    """
    Create all tables in the database
    """
    engine = create_engine(
        database_url, 
        connect_args={'check_same_thread': False} if database_url.startswith('sqlite') else {},
        echo=False
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal

def get_session(database_url: str = 'sqlite:///data/outreach.db'):
    """
    Get a database session
    """
    _, SessionLocal = create_database(database_url)
    return SessionLocal()





    