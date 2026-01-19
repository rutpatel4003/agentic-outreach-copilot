import unittest
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.scraper_agent import ScraperAgent
from src.agents.personalization_agent import PersonalizationAgent
from src.agents.tracking_agent import TrackingAgent, FollowUpSchedule
from src.agents.reply_agent import ReplyAgent, ReplyCategory
from src.tools.guardrails import Guardrails, GuardrailStatus
from src.tools.llm_interface import OllamaInterface
from src.utils.resume_parser import ResumeParser, ResumeData
from src.utils.prompt_templates import MessageType, MessageTone
from src.database.models import OutreachStatus, MessageChannel
from src.workflows.outreach_graph import OutreachWorkflow, WorkflowStatus


class TestResumeParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = ResumeParser()
    
    def test_parse_from_text(self):
        sample_text = """
        John Doe
        john.doe@example.com
        (555) 123-4567
        
        EXPERIENCE
        Software Engineer at TechCorp (2020-2023)
        Built scalable microservices using Python, Docker, and Kubernetes.
        
        EDUCATION
        Master of Science in Computer Science
        University of California (2018-2020)
        
        SKILLS
        Python, JavaScript, React, Docker, Kubernetes, AWS, Machine Learning
        """
        
        result = self.parser.parse_from_text(sample_text)
        
        self.assertIsInstance(result, ResumeData)
        self.assertEqual(result.name, "John Doe")
        self.assertEqual(result.email, "john.doe@example.com")
        self.assertIn("Python", result.skills)
        self.assertIn("Docker", result.skills)
        self.assertTrue(len(result.experience) > 0)
        self.assertTrue(len(result.education) > 0)
    
    def test_skills_extraction(self):
        text = "I have experience with Python, React, and AWS cloud services."
        result = self.parser.parse_from_text(text)
        
        self.assertIn("Python", result.skills)
        self.assertIn("React", result.skills)
        self.assertIn("Aws", result.skills)
    
    def test_email_extraction(self):
        text = "Contact me at test.user@company.com for more information."
        result = self.parser.parse_from_text(text)
        
        self.assertEqual(result.email, "test.user@company.com")
    
    def test_phone_extraction(self):
        text = "Phone: (555) 123-4567"
        result = self.parser.parse_from_text(text)
        
        self.assertIsNotNone(result.phone)
        self.assertIn("555", result.phone)


class TestScraperAgent(unittest.TestCase):
    
    def setUp(self):
        self.scraper = ScraperAgent()
    
    def test_scraper_initialization(self):
        self.assertIsNotNone(self.scraper.web_scraper)
    
    def test_extract_company_name(self):
        html = "<title>TechCorp - Building the Future</title>"
        name = self.scraper._extract_company_name("https://techcorp.com", html)
        self.assertIn("TechCorp", name)
    
    def test_extract_mission(self):
        html = """
        <div class="about">
            <p>Our mission is to democratize AI technology for everyone.</p>
        </div>
        """
        mission = self.scraper._extract_mission(html)
        self.assertIsNotNone(mission)
        self.assertIn("mission", mission.lower())


class TestTrackingAgent(unittest.TestCase):
    
    def setUp(self):
        self.tracker = TrackingAgent(db_path="data/test_outreach.db")
    
    def test_track_outreach(self):
        result = self.tracker.track_outreach(
            company_name="TestCorp",
            company_url="https://testcorp.com",
            contact_name="Jane Doe",
            contact_email="jane@testcorp.com",
            message_text="Test message for outreach tracking",
            channel=MessageChannel.LINKEDIN_MESSAGE,
            target_role="Software Engineer"
        )
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.message_id)
        self.assertTrue(result.followup_scheduled)
    
    def test_update_message_status(self):
        result = self.tracker.track_outreach(
            company_name="TestCorp2",
            company_url="https://testcorp2.com",
            contact_name=None,
            contact_email=None,
            message_text="Another test message",
            channel=MessageChannel.EMAIL,
            target_role="Data Scientist"
        )
        
        self.assertTrue(result.success)
        
        success = self.tracker.update_message_status(
            result.message_id,
            OutreachStatus.REPLIED,
            response_text="Thanks for reaching out!"
        )
        
        self.assertTrue(success)
    
    def test_get_outreach_stats(self):
        stats = self.tracker.get_outreach_stats()
        
        self.assertIsNotNone(stats)
        self.assertGreaterEqual(stats.total_sent, 0)
        self.assertGreaterEqual(stats.reply_rate, 0)
    
    def test_get_pending_followups(self):
        followups = self.tracker.get_pending_followups(days_ahead=30)
        
        self.assertIsInstance(followups, list)


class TestReplyAgent(unittest.TestCase):
    
    def setUp(self):
        try:
            self.reply_agent = ReplyAgent()
        except Exception:
            self.skipTest("Ollama not available")
    
    def test_classify_interested_reply(self):
        original = "Hi Jane, I'm interested in the ML Engineer role at your company."
        reply = "Thanks for reaching out! I'd love to schedule a call. Are you available Tuesday?"
        
        classification = self.reply_agent.classify_reply(original, reply)
        
        self.assertIsNotNone(classification)
        self.assertIn(classification.category, [
            ReplyCategory.INTERESTED,
            ReplyCategory.NEEDS_INFO
        ])
    
    def test_classify_not_interested_reply(self):
        original = "Hi Jane, I'm interested in the ML Engineer role."
        reply = "Thank you for your interest. Unfortunately, we've filled the position."
        
        classification = self.reply_agent.classify_reply(original, reply)
        
        self.assertIsNotNone(classification)
        self.assertEqual(classification.category, ReplyCategory.NOT_INTERESTED)
    
    def test_fallback_classification(self):
        fallback = self.reply_agent._create_fallback_classification(
            "I'm interested in learning more about your company."
        )
        
        self.assertIsNotNone(fallback)
        self.assertEqual(fallback.confidence, 0.6)


class TestGuardrails(unittest.TestCase):
    
    def setUp(self):
        try:
            self.guardrails = Guardrails()
        except Exception:
            self.skipTest("Ollama not available")
    
    def test_check_message_with_citations(self):
        message = """Hi Jane,
        
I noticed TechCorp recently raised $50M [source: news page] to expand your ML team.
With expertise in Python and TensorFlow, I'm excited about the Senior ML Engineer role [source: careers page].

Would you be open to a brief call?"""
        
        sources = {
            'news': 'TechCorp announces $50M Series B funding',
            'careers': 'Hiring: Senior ML Engineer, Software Engineer'
        }
        
        result = self.guardrails.check_message(
            message=message,
            source_material=sources,
            requested_tone=MessageTone.PROFESSIONAL,
            skip_llm_checks=True
        )
        
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.overall_score, 0.5)
    
    def test_count_citations(self):
        message = "TechCorp raised $50M [source: news]. They're hiring [source: careers]."
        count = self.guardrails._count_citations(message)
        
        self.assertEqual(count, 2)
    
    def test_reject_short_message(self):
        result = self.guardrails.check_message(
            message="Hi",
            source_material={},
            requested_tone=MessageTone.PROFESSIONAL,
            skip_llm_checks=True
        )
        
        self.assertEqual(result.status, GuardrailStatus.REJECTED)


class TestIntegration(unittest.TestCase):
    
    def setUp(self):
        try:
            self.workflow = OutreachWorkflow()
        except Exception:
            self.skipTest("Ollama not available")
    
    def test_workflow_initialization(self):
        self.assertIsNotNone(self.workflow.scraper)
        self.assertIsNotNone(self.workflow.personalizer)
        self.assertIsNotNone(self.workflow.guardrails)
        self.assertIsNotNone(self.workflow.tracker)


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestResumeParser))
    suite.addTests(loader.loadTestsFromTestCase(TestScraperAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestTrackingAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestReplyAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestGuardrails))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)