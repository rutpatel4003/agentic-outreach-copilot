import logging
from typing import Dict, List, Optional, TypedDict, Annotated
from datetime import datetime
from enum import Enum

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.agents.scraper_agent import ScraperAgent
from src.agents.personalization_agent import PersonalizationAgent
from src.agents.tracking_agent import TrackingAgent
from src.tools.guardrails import Guardrails, GuardrailStatus
from src.utils.resume_parser import ResumeParser, ResumeData
from src.utils.prompt_templates import MessageType, MessageTone
from src.database.models import MessageChannel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WorkflowStatus(Enum):
    INITIALIZED = "initialized"
    SCRAPING = "scraping"
    PERSONALIZING = "personalizing"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    TRACKED = "tracked"
    FAILED = "failed"

class OutreachState(TypedDict):
    resume_path: str
    resume_data: Optional[ResumeData]
    target_role: str
    company_url: str
    company_name: Optional[str]
    scraped_data: Optional[Dict]
    message_variants: Optional[List[Dict]]
    selected_variant: Optional[Dict]
    guardrail_result: Optional[Dict]
    tracking_result: Optional[Dict]
    status: str
    error: Optional[str]
    metadata: Dict
    message_type: str
    tone: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    skip_guardrails: bool
    max_retries: int
    current_retry: int

class OutreachWorkflow:
    def __init__(
        self,
        scraper_agent: Optional[ScraperAgent] = None,
        personalization_agent: Optional[PersonalizationAgent] = None,
        guardrails: Optional[Guardrails] = None,
        tracking_agent: Optional[TrackingAgent] = None,
        resume_parser: Optional[ResumeParser] = None,
        model_name: str = 'llama3.1:8b'
    ):
        self.scraper = scraper_agent or ScraperAgent()
        self.personalizer = personalization_agent or PersonalizationAgent(model_name=model_name)
        self.guardrails = guardrails or Guardrails(model_name=model_name)
        self.tracker = tracking_agent or TrackingAgent()
        self.resume_parser = resume_parser or ResumeParser()
        self.workflow = self._build_workflow()
        self.memory = MemorySaver()
        self.app = self.workflow.compile(checkpointer = self.memory)

    def _build_workflow(self) -> StateGraph:
        workflow = StateGraph(OutreachState)
        workflow.add_node('parse_resume', self._parse_resume_node)
        workflow.add_node('scrape_company', self._scrape_company_node)
        workflow.add_node('generate_messages', self._generate_messages_node)
        workflow.add_node('check_guardrails', self._check_guardrails_node)
        workflow.add_node('track_outreach', self._track_outreach_node)
        workflow.add_node('hadle_failure', self._handle_failure_node)

        workflow.set_entry_point('parse_resume')
        workflow.add_edge('parse_resume', 'scrape_company')
        workflow.add_edge('scrape_company', 'generate_messages')
        workflow.add_conditional_edges(
            'generate_messages', self._should_check_guardrails, {
                'check': 'check_guardrails',
                'skip': "track_outreach",
                'fail': 'handle_failure'
            }
        )

        workflow.add_conditional_edges(
            'check_guardrails',
            self._guardrails_passed,
            {
                'approved': 'track_outreach',
                'retry': 'generate_messages',
                'reject': 'handle_failure'
            }
        )

        workflow.add_edge('track_outreach', END)
        workflow.add_edge('handle_failure', END)
        return workflow
    
    def _parse_resume_node(self, state: OutreachState) -> OutreachState:
        logger.info(f'Parsing resume: {state['resume_path']}')
        try:
            resume_data = self.resume_parser.parse(state['resume_path'])
            state['resume_data'] = resume_data
            state['status'] = WorkflowStatus.INITALIZED.value
            state['metadata']['resume_parsed'] = True
            state['metadata']['skills_count'] = len(resume_data.skills)
            logger.info(f'Resume parsed: {resume_data.name or 'Unknown'}, '
                        f"{len(resume_data.skills)} skills")
        except Exception as e:
            logger.error(f'Resume parsing failed: {e}')
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f'Resume parsing failed: {str(e)}'

        return state
    
    def _scrape_company_node(self, state: OutreachState) -> OutreachState:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return state
        
        logger.info(f"Scraping company: {state['company_url']}")
        state['status'] = WorkflowStatus.SCRAPING.value
        
        try:
            result = self.scraper.scrape_company(state['company_url'])
            state['scraped_data'] = result
            state['company_name'] = result.get('company_name', 'Unknown Company')
            state['metadata']['scraping_success'] = True
            state['metadata']['pages_scraped'] = len([
                v for v in result.values() if v
            ])

            logger.info(
                f"Scraping complete: {state['company_name']}, "
                f"{state['metadata']['pages_scraped']} pages"
            )

        except Exception as e:
            logger.error(f"Company scraping failed: {e}")
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f"Company scraping failed: {str(e)}"
        
        return state
    
    def _generate_message_node(self, state: OutreachState) -> OutreachState:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return state
        
        logger.info('Generating personalized messages')
        state['status'] = WorkflowStatus.PERSONALIZING.value
        try:
            message_type = MessageType(state.get('message_type', 'LINKEDIN_MESSAGE'))
            tone = MessageTone[state.get('tone', 'PROFESSIONAL').upper()]
            result = self.personalizer.generate_outreach_messages(
                resume_data=state['resume_data'],
                target_role=state['target_role'],
                company_data={
                    'company_name': state['company_name'],
                    'mission': state['scraped_data'].get('mission', ''),
                    'recent_news': state['scraped_data'].get('recent_news', ''),
                    'hiring_roles': state['scraped_data'].get('hiring_roles', []),
                    'key_people': state['scraped_data'].get('key_people', [])
                },
                message_type=message_type,
                tone=tone,
                num_variants=3
            )

            state['message_variants'] = [
                {
                    'message': v.message,
                    'subject': v.subject,
                    'citations': v.citations,
                    'skills_highlighted': v.skills_highlighted,
                    'word_count': v.word_count
                }
                for v in result.variants
            ]

            if state['message_variants']:
                state['selected_variant'] = state['message_variants'][0]
            
            state['metadata']['variants_generated'] = len(state['message_variants'])
            
            logger.info(f"Generated {len(state['message_variants'])} message variants")
            
        except Exception as e:
            logger.error(f"Message generation failed: {e}")
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f"Message generation failed: {str(e)}"
        
        return state
    
    def _check_guardrails_node(self, state: OutreachState) -> OutreachState:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return state
        
        logger.info('Checking guardrails')
        state['status'] = WorkflowStatus.REVIEWING.value
        try:
            selected_message = state['selected_variant']['message']
            source_material = {
                'about': state['scraped_data'].get('mission', ''),
                'news': state['scraped_data'].get('recent_news', ''),
                'careers': '\n'.join(state['scraped_data'].get('hiring_roles', []))
            }

            tone = MessageTone[state.get('tone', 'PROFESSIONAL').upper()]
            guardrail_result = self.guardrails.check_message(
                message=selected_message,
                source_material=source_material,
                requested_tone=tone,
                skip_llm_checks=False
            )

            state['guardrail_result'] = {
                'status': guardrail_result.status.value,
                'overall_score': guardrail_result.overall_score,
                'passed_checks': guardrail_result.passed_checks,
                'total_checks': guardrail_result.total_checks,
                'feedback': guardrail_result.feedback
            }

            if guardrail_result.status == GuardrailStatus.APPROVED:
                state['status'] = WorkflowStatus.APPROVED.value
            elif guardrail_result.status == GuardrailStatus.NEEDS_REVISION:
                state['current_retry'] = state.get('current_retry', 0) + 1
                if state['current_retry'] >= state.get('max_retries', 2):
                    state['status'] = WorkflowStatus.REJECTED.value
            else:
                state['status'] = WorkflowStatus.REJECTED.value
            
            logger.info(
                f"Guardrails check: {guardrail_result.status.value}, "
                f"score: {guardrail_result.overall_score:.2f}"
            )
        except Exception as e:
            logger.error(f"Guardrails check failed: {e}")
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f"Guardrails check failed: {str(e)}"
        
        return state
    
    def _track_outreach_node(self, state: OutreachState) -> OutreachState:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return state
        
        logger.info(f'Tracking outreach in CRM')
        state['status'] = WorkflowStatus.TRACKED.value

        try:
            message_type_str = state.get('message_type', 'linkedin_message')
            channel = MessageChannel[message_type_str.upper()]
            tracking_result = self.tracker.track_outreach(
                company_name=state['company_name'],
                company_url=state['company_url'],
                contact_name=state.get('contact_name'),
                contact_email=state.get('contact_email'),
                message_text=state['selected_variant']['message'],
                channel=channel,
                target_role=state['target_role'],
                metadata={
                    'word_count': state['selected_variant']['word_count'],
                    'citations': state['selected_variant']['citations'],
                    'skills_highlighted': state['selected_variant']['skills_highlighted'],
                    'guardrail_score': state.get('guardrail_result', {}).get('overall_score'),
                    'workflow_run_date': datetime.utcnow().isoformat()
                }
            )

            state['tracking_result'] = {
                'success': tracking_result.success,
                'message_id': tracking_result.message_id,
                'followup_scheduled': tracking_result.followup_scheduled,
                'next_followup_date': (
                    tracking_result.next_followup_date.isoformat()
                    if tracking_result.next_followup_date else None
                )
            }
            
            logger.info(
                f"Outreach tracked: Message ID {tracking_result.message_id}"
            )
            
        except Exception as e:
            logger.error(f"Tracking failed: {e}")
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f"Tracking failed: {str(e)}"
        
        return state
    
    def _handle_failure_node(self, state: OutreachState) -> OutreachState:
        logger.error(f"Workflow failed: {state.get('error', 'Unknown error')}")
        state['status'] = WorkflowStatus.FAILED.value
        return state
    
    def _should_check_guardrails(self, state: OutreachState) -> str:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return "fail"
        
        if not state.get('message_variants'):
            return "fail"
        
        if state.get('skip_guardrails', False):
            return "skip"
        
        return "check"
    
    def _guardrails_passed(self, state: OutreachState) -> str:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return "reject"
        
        status = state.get('status')
        
        if status == WorkflowStatus.APPROVED.value:
            return "approved"
        elif status == WorkflowStatus.REJECTED.value:
            return "reject"
        else:
            current_retry = state.get('current_retry', 0)
            max_retries = state.get('max_retries', 2)
            
            if current_retry < max_retries:
                return "retry"
            else:
                return "reject"
    
    def run(
        self,
        resume_path: str,
        target_role: str,
        company_url: str,
        message_type: str = "linkedin_message",
        tone: str = "professional",
        contact_name: Optional[str] = None,
        contact_email: Optional[str] = None,
        skip_guardrails: bool = False,
        max_retries: int = 2
    ) -> OutreachState:
        
        initial_state: OutreachState = {
            'resume_path': resume_path,
            'resume_data': None,
            'target_role': target_role,
            'company_url': company_url,
            'company_name': None,
            'scraped_data': None,
            'message_variants': None,
            'selected_variant': None,
            'guardrail_result': None,
            'tracking_result': None,
            'status': WorkflowStatus.INITIALIZED.value,
            'error': None,
            'metadata': {},
            'message_type': message_type,
            'tone': tone,
            'contact_name': contact_name,
            'contact_email': contact_email,
            'skip_guardrails': skip_guardrails,
            'max_retries': max_retries,
            'current_retry': 0
        }
        
        logger.info(f"Starting outreach workflow for {company_url}")
        
        try:
            config = {"configurable": {"thread_id": datetime.utcnow().isoformat()}}
            final_state = self.app.invoke(initial_state, config)
            
            logger.info(f"Workflow completed with status: {final_state['status']}")
            return final_state
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            initial_state['status'] = WorkflowStatus.FAILED.value
            initial_state['error'] = str(e)
            return initial_state


def run_outreach_workflow(
    resume_path: str,
    target_role: str,
    company_url: str,
    message_type: str = "linkedin_message",
    tone: str = "professional",
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    skip_guardrails: bool = False,
    model_name: str = "llama3.1:8b"
) -> Dict:
    workflow = OutreachWorkflow(model_name=model_name)
    result = workflow.run(
        resume_path=resume_path,
        target_role=target_role,
        company_url=company_url,
        message_type=message_type,
        tone=tone,
        contact_name=contact_name,
        contact_email=contact_email,
        skip_guardrails=skip_guardrails
    )
    
    return dict(result)
        


