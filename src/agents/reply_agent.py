import logging
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from src.tools.llm_interface import OllamaInterface
from src.utils.prompt_templates import PromptTemplates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReplyCategory(Enum):
    INTERESTED = 'interested'
    NOT_INTERESTED = 'not_interested'
    NEEDS_INFO = 'needs_info'
    OUT_OF_OFFICE = 'out_of_office'
    SPAM = 'spam'

class ReplySentiment(Enum):
    POSITIVE = 'positive'
    NEUTRAL = 'neutral'
    NEGATIVE = 'negative'

class ActionNeeded(Enum):
    RESPOND = 'respond'
    WAIT = 'wait'
    CLOSE = 'close'

@dataclass 
class ReplyClassification:
    category: ReplyCategory
    sentiment: ReplySentiment
    action_needed: ActionNeeded
    key_points: List[str]
    confidence: float

@dataclass
class ResponseSuggestion:
    message: str
    subject: Optional[str]
    tone: str
    suggested_action: str

@dataclass
class ReplyAnalysis:
    classification: ReplyClassification
    suggestions: List[ResponseSuggestion]
    analysis_metadata: Dict

class ReplyAgent:
    def __init__(self, llm_interface: Optional[OllamaInterface] = None,
                 model_name: str = "llama:3.1:8b", temperature: float = 0.7, max_retries: int=3):
        self.llm = llm_interface or OllamaInterface(model=model_name)
        self.temperature = temperature
        self.max_retries = max_retries
        self.prompt_templates = PromptTemplates()

    def classify_reply(
            self, original_message: str, reply_text: str
    ) -> ReplyClassification:
        if not reply_text or len(reply_text.strip()) < 5:
            raise ValueError("Reply text is too short or empty")
        logger.info('Classifying reply...')
        prompt = self.prompt_templates.format_reply_classification(original_message=original_message, reply_text=reply_text)
        system_prompt = self.prompt_templates.REPLY_CLASSIFICATION_SYSTEM
        for attempt in range(self.max_retries):
            try:
                response = self.llm.generate(
                    prompt = prompt,
                    system_prompt = system_prompt,
                    temperature = 0.3,
                    max_tokens = 1000
                )

                parsed = self._parse_json_response(response)
                if not parsed:
                    logger.warning(f'Failed to parse response on attempt {attempt+1}')
                    continue

                category_str = parsed.get('category', 'SPAM')
                try:
                    category = ReplyCategory[category_str]
                except KeyError:
                    category = self._infer_category_from_text(reply_text)

                sentiment_str = parsed.get('sentiment', 'neutral')
                try:
                    sentiment = ReplySentiment[sentiment_str.upper()]
                except KeyError:
                    snetiment = ReplySentiment.NEUTRAL

                action_str = parsed.get('action_needed', 'close')
                try:
                    action = ActionNeeded[action_str.upper()]
                except KeyError:
                    action = ActionNeeded.CLOSE

                return ReplyClassification(
                    category=category,
                    sentiment=sentiment,
                    action_needed=action,
                    key_points=parsed.get('key_points', []), 
                    confidence=float(parsed.get('confidence', 0.5))
                )
            except Exception as e:
                logger.error(f'Classification failed on attempt {attempt + 1}: {e}')
                if attempt == self.max_retries - 1:
                    return self._create_fallback_classification(reply_text)
                continue

        return self._create_fallback_classification(reply_text)
    
    def suggest_responses(
            self, original_message: str, reply_text: str, classification: ReplyClassification, candidate_info: Dict[str, any], num_variants: int = 2
    ) -> List[ResponseSuggestion]:
        if classification.action_needed == ActionNeeded.CLOSE:
            logger.info('No response needed for this reply')
            return []
        
        if classification.action_needed == ActionNeeded.WAIT:
            logger.info("Waiting is recommended, no suggestions generated")
            return []
        
        logger.info(f'Generating {num_variants} response suggestions...')

        classification_summary = json.dumps({
            'category': classification.category.value,
            'sentiment': classification.sentiment.value,
            'key_points': classification.key_points
        }, indent=2)

        prompt = self.prompt_templates.format_reply_suggestion(
            original_message=original_message,
            reply_text=reply_text,
            classification_result=classification_summary,
            candidate_info=candidate_info,
            num_variants=num_variants
        )

        system_prompt = self.prompt_templates.REPLY_SUGGESTION_SYSTEM

        for attempt in range(self.max_retries):
            try:
                response = self.llm.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=self.temperature,
                    max_tokens=1500
                )

                parsed = self._parse_json_response(response)
                if not parsed or 'variants' not in parsed:
                    logger.warning(f"Invalid response structure on attempt {attempt + 1}")
                    continue

                suggestions = []
                for variant in parsed['variants']:
                    if not isinstance(variant, dict):
                        continue

                    message = variant.get('message', '')
                    if not message or len(message.strip()) < 10:
                        continue

                    suggestions.append(ResponseSuggestion(
                        message=message.strip(),
                        subject=variant.get('subject'),
                        tone=variant.get('tone', 'professional'),
                        suggested_action=variant.get('suggested_action', 'respond')
                    ))

                if suggestions:
                    logger.info(f"Generated {len(suggestions)} response suggestions")
                    return suggestions
                
            except Exception as e:
                logger.error(f"Suggestion generation failed on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    return []
                continue
        
        return []
    
    def analyze_reply(
            self, original_message: str, reply_text: str, candidate_info: Dict[str, any],
            generate_suggestions: bool=True, num_suggestions: int = 2
    ) -> ReplyAnalysis:
        classification = self.classify_reply(original_message=original_message, reply_text=reply_text)
        suggestions = []
        if generate_suggestions and classification.action_needed == ActionNeeded.RESPOND:
            suggestions = self.suggest_responses(
                original_message=original_message,
                reply_text=reply_text,
                classification=classification,
                candidate_info=candidate_info,
                num_variants=num_suggestions
            )

        return ReplyAnalysis(
            classification=classification,
            suggestions=suggestions,
            analysis_metadata={
                'model': self.llm.model,
                'temperature': self.temperature,
                'original_message_length': len(original_message),
                'reply_length': len(reply_text)
            }
        )
    
    def _infer_category_from_text(self, text: str) -> ReplyCategory:
        text_lower = text.lower()
        interested_keywords = [
            'interested', 'schedule', 'call', 'meeting', 'discuss',
            'portfolio', 'resume', 'interview', 'let\'s connect'
        ]
        
        not_interested_keywords = [
            'not hiring', 'not interested', 'no positions', 'filled',
            'not a fit', 'decline', 'pass', 'unfortunately'
        ]
        
        ooo_keywords = [
            'out of office', 'away', 'unavailable', 'vacation',
            'auto-reply', 'automated response'
        ]
        
        info_keywords = [
            'more information', 'can you', 'could you', 'tell me',
            'provide', 'send', 'share'
        ]

        if any(kw in text_lower for kw in ooo_keywords):
            return ReplyCategory.OUT_OF_OFFICE
        
        if any(kw in text_lower for kw in interested_keywords):
            return ReplyCategory.INTERESTED
        
        if any(kw in text_lower for kw in not_interested_keywords):
            return ReplyCategory.NOT_INTERESTED
        
        if any(kw in text_lower for kw in info_keywords):
            return ReplyCategory.NEEDS_INFO
        
        return ReplyCategory.SPAM
    
    def _create_fallback_classification(self, reply_text: str) -> ReplyClassification:
        category = self._infer_category_from_text(reply_text)
        action = ActionNeeded.CLOSE
        if category == ReplyCategory.INTERESTED:
            action = ActionNeeded.RESPOND
        elif category == ReplyCategory.NEEDS_INFO:
            action = ActionNeeded.RESPOND
        elif category == ReplyCategory.OUT_OF_OFFICE:
            action = ActionNeeded.WAIT

        sentiment = ReplySentiment.NEUTRAL
        if category == ReplyCategory.INTERESTED:
            sentiment = ReplySentiment.POSITIVE
        elif category == ReplyCategory.NOT_INTERESTED:
            sentiment = ReplySentiment.NEGATIVE

        return ReplyClassification(
            category=category,
            sentiment=sentiment,
            action_needed=action,
            key_points=["Classification based on keyword analysis"],
            confidence=0.6
        )
    
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
        
    def analyze_reply_and_suggest(original_message: str,
                                  reply_text: str,
                                  candidate_name: str = 'Candidate',
                                  candidate_email: Optional[str] = None,
                                  candidate_skills: Optional[List[str]] = None,
                                  model_name: str = 'llama3.1:8b') -> ReplyAnalysis:
        candidate_info = {
            'name': candidate_name,
            'email': candidate_email,
            'skills': candidate_skills
        }

        agent = ReplyAgent(model_name = model_name)
        return agent.analyze_reply(
            original_message=original_message,
            reply_text=reply_text,
            candidate_info=candidate_info,
            generate_suggestions=True,
            num_suggestions=2
        )