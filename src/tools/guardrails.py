import logging
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.tools.llm_interface import OllamaInterface, LLMConfig
from src.utils.prompt_templates import PromptTemplates, MessageTone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GuardrailStatus(Enum):
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


@dataclass
class FactCheckResult:
    all_claims_verified: bool
    verified_claims: List[str]
    unverified_claims: List[Dict[str, str]]
    recommendation: str
    confidence: float


@dataclass
class ToneCheckResult:
    tone_match: bool
    detected_tone: str
    appropriateness_score: float
    red_flags: List[str]
    recommendation: str
    revision_suggestions: List[str]


@dataclass
class GuardrailResult:
    status: GuardrailStatus
    fact_check: Optional[FactCheckResult]
    tone_check: Optional[ToneCheckResult]
    overall_score: float
    feedback: List[str]
    passed_checks: int
    total_checks: int


class Guardrails:
    
    def __init__(
        self,
        llm_interface: Optional[OllamaInterface] = None,
        model_name: str = "qwen3:4b-instruct",
        min_citations: int = 2,
        max_word_count: int = 200,
        min_appropriateness_score: float = 7.0
    ):
        self.llm = llm_interface or OllamaInterface(config=LLMConfig(model=model_name))
        self.min_citations = min_citations
        self.max_word_count = max_word_count
        self.min_appropriateness_score = min_appropriateness_score
        self.prompt_templates = PromptTemplates()
    
    def check_message(
        self,
        message: str,
        source_material: Dict[str, str],
        requested_tone: MessageTone,
        skip_llm_checks: bool = False
    ) -> GuardrailResult:
        
        if not message or len(message.strip()) < 10:
            return self._create_rejection_result("Message is too short or empty")
        
        feedback = []
        passed_checks = 0
        total_checks = 0
        
        total_checks += 1
        word_count = len(message.split())
        if word_count <= self.max_word_count:
            passed_checks += 1
        else:
            feedback.append(f"Word count {word_count} exceeds limit {self.max_word_count}")
        
        total_checks += 1
        citation_count = self._count_citations(message)
        if citation_count >= self.min_citations:
            passed_checks += 1
        else:
            feedback.append(
                f"Only {citation_count} citations found, minimum {self.min_citations} required"
            )
        
        total_checks += 1
        generic_patterns = [
            r'\bi am writing to express my interest\b',
            r'\bi came across your posting\b',
            r'\bi would be a great fit\b',
            r'\bi am confident that\b',
            r'\bthank you for your time and consideration\b'
        ]
        
        generic_count = sum(
            1 for pattern in generic_patterns
            if re.search(pattern, message.lower())
        )
        
        if generic_count <= 1:
            passed_checks += 1
        else:
            feedback.append(f"Message contains {generic_count} generic phrases")
        
        fact_check = None
        tone_check = None
        
        if not skip_llm_checks:
            try:
                fact_check = self._check_facts(message, source_material)
                total_checks += 1
                if fact_check.all_claims_verified:
                    passed_checks += 1
                else:
                    feedback.append(
                        f"Fact check failed: {len(fact_check.unverified_claims)} "
                        f"unverified claims"
                    )
                    for claim in fact_check.unverified_claims[:2]:
                        feedback.append(f"  - {claim.get('claim', 'Unknown claim')}")
            except Exception as e:
                logger.error(f"Fact checking failed: {e}")
                feedback.append("Fact checking could not be completed")
            
            try:
                tone_check = self._check_tone(message, requested_tone)
                total_checks += 1
                if (tone_check.tone_match and 
                    tone_check.appropriateness_score >= self.min_appropriateness_score):
                    passed_checks += 1
                else:
                    feedback.append(
                        f"Tone check failed: score {tone_check.appropriateness_score:.1f}"
                    )
                    if tone_check.red_flags:
                        for flag in tone_check.red_flags[:2]:
                            feedback.append(f"  - {flag}")
            except Exception as e:
                logger.error(f"Tone checking failed: {e}")
                feedback.append("Tone checking could not be completed")
        
        overall_score = passed_checks / total_checks if total_checks > 0 else 0.0

        if overall_score >= 0.75:
            status = GuardrailStatus.APPROVED
        elif overall_score >= 0.5:
            status = GuardrailStatus.NEEDS_REVISION
        else:
            status = GuardrailStatus.REJECTED
        
        return GuardrailResult(
            status=status,
            fact_check=fact_check,
            tone_check=tone_check,
            overall_score=overall_score,
            feedback=feedback,
            passed_checks=passed_checks,
            total_checks=total_checks
        )
    
    def _check_facts(
        self,
        message: str,
        source_material: Dict[str, str]
    ) -> FactCheckResult:
        
        if not source_material:
            logger.warning("No source material provided for fact checking")
            return FactCheckResult(
                all_claims_verified=False,
                verified_claims=[],
                unverified_claims=[{"claim": "No source material", "reason": "Cannot verify"}],
                recommendation="reject",
                confidence=0.0
            )
        
        prompt = self.prompt_templates.format_guardrails_check(
            message=message,
            source_material=source_material
        )
        
        system_prompt = self.prompt_templates.GUARDRAILS_CHECK_SYSTEM
        
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1500
        )
        
        parsed = self._parse_json_response(response)
        
        if not parsed:
            return FactCheckResult(
                all_claims_verified=False,
                verified_claims=[],
                unverified_claims=[{"claim": "Parse error", "reason": "Could not parse response"}],
                recommendation="reject",
                confidence=0.0
            )
        
        return FactCheckResult(
            all_claims_verified=parsed.get('all_claims_verified', False),
            verified_claims=parsed.get('verified_claims', []),
            unverified_claims=parsed.get('unverified_claims', []),
            recommendation=parsed.get('recommendation', 'reject'),
            confidence=0.8 if parsed.get('all_claims_verified') else 0.4
        )
    
    def _check_tone(
        self,
        message: str,
        requested_tone: MessageTone
    ) -> ToneCheckResult:
        
        prompt = self.prompt_templates.format_tone_check(
            message=message,
            requested_tone=requested_tone
        )
        
        system_prompt = self.prompt_templates.TONE_CHECK_SYSTEM
        
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1000
        )
        
        parsed = self._parse_json_response(response)
        
        if not parsed:
            return ToneCheckResult(
                tone_match=False,
                detected_tone="unknown",
                appropriateness_score=5.0,
                red_flags=["Could not parse tone check response"],
                recommendation="revise",
                revision_suggestions=[]
            )
        
        return ToneCheckResult(
            tone_match=parsed.get('tone_match', False),
            detected_tone=parsed.get('detected_tone', 'unknown'),
            appropriateness_score=float(parsed.get('appropriateness_score', 5.0)),
            red_flags=parsed.get('red_flags', []),
            recommendation=parsed.get('recommendation', 'revise'),
            revision_suggestions=parsed.get('revision_suggestions', [])
        )
    
    def _count_citations(self, message: str) -> int:
        citation_patterns = [
            r'\[source:\s*[^\]]+\]',
            r'\[via\s+[^\]]+\]',
            r'\(source:\s*[^\)]+\)',
            r'according to their .+ page'
        ]
        
        count = 0
        for pattern in citation_patterns:
            count += len(re.findall(pattern, message.lower()))
        
        return count
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        cleaned = response.strip()
        
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        if cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        
        cleaned = cleaned.strip()
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    return None
            
            return None
    
    def _create_rejection_result(self, reason: str) -> GuardrailResult:
        return GuardrailResult(
            status=GuardrailStatus.REJECTED,
            fact_check=None,
            tone_check=None,
            overall_score=0.0,
            feedback=[reason],
            passed_checks=0,
            total_checks=1
        )


def check_outreach_message(
    message: str,
    source_material: Dict[str, str],
    requested_tone: str = "professional",
    model_name: str = "qwen3:4b-instruct",
    skip_llm_checks: bool = False
) -> GuardrailResult:
    
    try:
        tone_enum = MessageTone[requested_tone.upper()]
    except KeyError:
        raise ValueError(
            f"Invalid tone: {requested_tone}. "
            f"Valid options: {[t.name.lower() for t in MessageTone]}"
        )
    
    guardrails = Guardrails(model_name=model_name)
    
    return guardrails.check_message(
        message=message,
        source_material=source_material,
        requested_tone=tone_enum,
        skip_llm_checks=skip_llm_checks
    )
