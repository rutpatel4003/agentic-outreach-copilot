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
    scraped_data: Optional[Dict]  # now includes 'extracted_contacts' list
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
    # scraper settings
    js_rendering: bool
    scroll_page: bool
    js_wait_time: int  # milliseconds

class OutreachWorkflow:
    def __init__(
        self,
        scraper_agent: Optional[ScraperAgent] = None,
        personalization_agent: Optional[PersonalizationAgent] = None,
        guardrails: Optional[Guardrails] = None,
        tracking_agent: Optional[TrackingAgent] = None,
        resume_parser: Optional[ResumeParser] = None,
        model_name: str = 'qwen3:4b-instruct',
        progress_callback: Optional[callable] = None
    ):
        self.scraper = scraper_agent or ScraperAgent()
        self.personalizer = personalization_agent or PersonalizationAgent(model_name=model_name)
        self.guardrails = guardrails or Guardrails(model_name=model_name)
        self.tracker = tracking_agent or TrackingAgent()
        self.resume_parser = resume_parser or ResumeParser()
        self.progress_callback = progress_callback
        self.workflow = self._build_workflow()
        self.memory = MemorySaver()
        self.app = self.workflow.compile(checkpointer = self.memory)

    def _report_progress(self, step: str, progress: float, status: str):
        """Report progress to callback if provided"""
        if self.progress_callback:
            try:
                self.progress_callback(step=step, progress=progress, status=status)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    def _build_workflow(self) -> StateGraph:
        workflow = StateGraph(OutreachState)
        workflow.add_node('parse_resume', self._parse_resume_node)
        workflow.add_node('scrape_company', self._scrape_company_node)
        workflow.add_node('generate_messages', self._generate_messages_node)
        workflow.add_node('check_guardrails', self._check_guardrails_node)
        workflow.add_node('track_outreach', self._track_outreach_node)
        workflow.add_node('handle_failure', self._handle_failure_node)

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
        self._report_progress('parse_resume', 0.1, '📄 Parsing resume...')
        logger.info(f"Parsing resume: {state['resume_path']}")
        try:
            resume_data = self.resume_parser.parse(state['resume_path'])
            state['resume_data'] = resume_data
            state['status'] = WorkflowStatus.INITIALIZED.value
            state['metadata']['resume_parsed'] = True
            state['metadata']['skills_count'] = len(resume_data.skills)
            logger.info(f"Resume parsed: {resume_data.name or 'Unknown'}, "
                        f"{len(resume_data.skills)} skills")
        except Exception as e:
            logger.error(f'Resume parsing failed: {e}')
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f'Resume parsing failed: {str(e)}'

        return state
    
    def _scrape_company_node(self, state: OutreachState) -> OutreachState:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return state

        self._report_progress('scrape_company', 0.2, '🌐 Scraping company website...')
        logger.info(f"Scraping company: {state['company_url']}")
        state['status'] = WorkflowStatus.SCRAPING.value

        try:
            # get manual urls from state
            manual_urls = state.get('manual_urls', None)

            result = self.scraper.scrape_company(
                state['company_url'],
                manual_urls=manual_urls,
                js_rendering=state.get('js_rendering', True),
                scroll_page=state.get('scroll_page', True),
                js_wait_time=state.get('js_wait_time', 3000)
            )
            
            state['scraped_data'] = result
            pages = (result or {}).get("pages", {}) or {}

            def _page_text(key: str) -> str:
                v = pages.get(key) or {}
                return (v.get("text") or "").strip()

            # keep original pages + provide convenience fields used elsewhere
            result["mission"] = _page_text("about")
            result["recent_news"] = _page_text("news")
            result["careers_text"] = _page_text("careers")
            result["team_text"] = _page_text("team")

            # keep a simple url map for citations
            result["page_urls"] = {
                k: (pages.get(k) or {}).get("url", "")
                for k in ["about", "careers", "news", "team"]
            }
            state['company_name'] = result.get('company_name', 'Unknown Company')
            state['metadata']['scraping_success'] = True
            pages = (result or {}).get('pages', {})
            state['metadata']['pages_scraped'] = len(pages) if isinstance(pages, dict) else 0

            # re-extract contacts with target_role for better relevance scoring
            contacts = result.get('extracted_contacts', [])
            if contacts:
                # boost relevance for contacts matching target role
                target_role = state.get('target_role', '').lower()
                for contact in contacts:
                    if contact.get('title'):
                        title_lower = contact['title'].lower()
                        # check for role keyword matches
                        if any(kw in title_lower for kw in target_role.split()):
                            contact['relevance_score'] = min(1.0, contact.get('relevance_score', 0) + 0.2)

                # re-sort by relevance
                contacts.sort(key=lambda c: c.get('relevance_score', 0), reverse=True)
                result['extracted_contacts'] = contacts

            state['metadata']['contacts_found'] = len(contacts)

            # filter and score job listings by target role
            jobs = result.get('extracted_jobs', [])
            if jobs and state.get('target_role'):
                target_role = state['target_role'].lower()
                target_words = set(target_role.split())

                for job in jobs:
                    title_lower = job['title'].lower()
                    title_words = set(title_lower.split())
                    overlap = target_words & title_words

                    if overlap:
                        job['match_score'] = len(overlap) / len(target_words)
                    else:
                        # Check for partial matches
                        job['match_score'] = 0.0
                        for tw in target_words:
                            if tw in title_lower:
                                job['match_score'] += 0.3

                # sort by match score
                jobs.sort(key=lambda j: j.get('match_score', 0), reverse=True)
                result['extracted_jobs'] = jobs

                # log matching jobs
                matching_jobs = [j for j in jobs if j.get('match_score', 0) > 0.3]
                if matching_jobs:
                    logger.info(f"Found {len(matching_jobs)} jobs matching '{state['target_role']}'")

            state['metadata']['jobs_found'] = len(jobs)

            
            logger.info(
                f"Scraping complete: {state['company_name']}, "
                f"{state['metadata']['pages_scraped']} pages, "
                f"{len(contacts)} contacts, {len(jobs)} jobs found"
            )
            
        except Exception as e:
            logger.error(f"Company scraping failed: {e}")
            state['status'] = WorkflowStatus.FAILED.value
            state['error'] = f"Company scraping failed: {str(e)}"
        
        return state
    
    def _generate_messages_node(self, state: OutreachState) -> OutreachState:
        if state.get('status') == WorkflowStatus.FAILED.value:
            return state

        self._report_progress('generate_messages', 0.5, '✍️ Generating personalized messages...')
        logger.info('Generating personalized messages')
        state['status'] = WorkflowStatus.PERSONALIZING.value
        try:
            message_type = MessageType(state.get("message_type", MessageType.LINKEDIN_MESSAGE.value))
            tone = MessageTone[state.get('tone', 'PROFESSIONAL').upper()]

            # extract scraped page content from the correct structure
            pages = (state.get('scraped_data') or {}).get('pages', {})

            def _page_text(key: str) -> str:
                v = pages.get(key, {})
                return v.get('text', '') if isinstance(v, dict) else (v or '')

            # extract the convenience fields that scraper already prepared
            scraped_data = state.get('scraped_data', {})

            # get revision feedback from previous guardrails check
            revision_feedback = None
            if state.get('guardrail_result'):
                feedback_list = state['guardrail_result'].get('feedback', [])
                if feedback_list:
                    revision_feedback = feedback_list

            result = self.personalizer.generate_outreach_messages(
                resume_data=state['resume_data'],
                target_role=state['target_role'],
                company_data={
                    'company_name': state['company_name'],
                    'about': _page_text('about'),
                    'news': _page_text('news'),
                    'careers': _page_text('careers'),
                    'team': _page_text('team'),
                    'mission': scraped_data.get('mission', ''),
                    'recent_news': scraped_data.get('recent_news', ''),
                    'careers_text': scraped_data.get('careers_text', ''),
                    'team_text': scraped_data.get('team_text', ''),
                    'hiring_roles': [],  # can be populated if scraper extracts job listings - in progress currently
                    'key_people': [],  # can be populated if scraper extracts job listings - in progress currently
                },
                message_type=message_type,
                tone=tone,
                num_variants=3,
                revision_feedback=revision_feedback
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

        self._report_progress('check_guardrails', 0.7, '🛡️ Checking message quality...')
        logger.info('Checking guardrails')
        state['status'] = WorkflowStatus.REVIEWING.value
        try:
            selected_message = state['selected_variant']['message']

            pages = state["scraped_data"].get("pages", {}) or {}
            page_urls = state["scraped_data"].get("page_urls", {}) or {}

            def _pack(k: str) -> str:
                # include URL header so the fact-checker can align citations
                text = ((pages.get(k) or {}).get("text") or "").strip()
                url = (page_urls.get(k) or "").strip()
                if not text:
                    return ""
                # trim to keep guardrails prompt small
                text = text[:2000]
                return f"URL: {url}\n{text}"

            source_material = {
                "about": _pack("about"),
                "careers": _pack("careers"),
                "news": _pack("news"),
                "team": _pack("team"),
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
                    state['error'] = (
                        f"Guardrails rejected after {state['current_retry']} attempts. "
                        f"Feedback: {guardrail_result.feedback}"
                    )
                else:
                    # keep status as reviewing (so graph routes to retry)
                    state['status'] = WorkflowStatus.REVIEWING.value
            else:
                state['status'] = WorkflowStatus.REJECTED.value
                state['error'] = f"Guardrails rejected. Feedback: {guardrail_result.feedback}"
            
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

        self._report_progress('track_outreach', 0.9, '💾 Saving to database...')
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
                message_metadata={
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
            self._report_progress('complete', 1.0, '✅ Complete!')

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
        max_retries: int = 2,
        manual_urls: Optional[Dict[str, str]] = None,
        js_rendering: bool = True,
        scroll_page: bool = True,
        js_wait_time: int = 3000
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
            'current_retry': 0,
            'manual_urls': manual_urls,
            'js_rendering': js_rendering,
            'scroll_page': scroll_page,
            'js_wait_time': js_wait_time
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
    model_name: str = "qwen3:4b-instruct"
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
        


