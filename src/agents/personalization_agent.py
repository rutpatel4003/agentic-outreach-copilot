import logging
import json
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

from src.tools.llm_interface import OllamaInterface, LLMConfig
from src.utils.resume_parser import ResumeData, ResumeParser
from src.utils.prompt_templates import (
    PromptTemplates,
    MessageType,
    MessageTone
)
from src.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MessageVariant:
    message: str
    subject: Optional[str]
    citations: List[str]
    skills_highlighted: List[str]
    word_count: int
    message_type: MessageType
    tone: MessageTone


@dataclass
class PersonalizationResult:
    variants: List[MessageVariant]
    company_name: str
    target_role: str
    candidate_name: Optional[str]
    generation_metadata: Dict


class PersonalizationAgent:

    def __init__(
        self,
        llm_interface: Optional[OllamaInterface] = None,
        resume_parser: Optional[ResumeParser] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None
    ):
        # use config defaults if not provided
        model_name = model_name or config.llm.model
        temperature = temperature if temperature is not None else config.llm.temperature
        max_retries = max_retries if max_retries is not None else config.llm.max_retries

        self.llm = llm_interface or OllamaInterface(config=LLMConfig(model=model_name))
        self.resume_parser = resume_parser or ResumeParser()
        self.temperature = temperature
        self.max_retries = max_retries
        self.prompt_templates = PromptTemplates()

    def _count_inline_sources(self, text: str) -> int:
        """Count inline citations in message text"""
        return len(re.findall(r'\[source:\s*[^\]]+\]', text, flags=re.I))
    
    def generate_outreach_messages(
        self,
        resume_data: ResumeData,
        target_role: str,
        company_data: Dict[str, Any],
        message_type: MessageType = MessageType.LINKEDIN_MESSAGE,
        tone: MessageTone = MessageTone.PROFESSIONAL,
        num_variants: int = 3
    ) -> PersonalizationResult:
        
        if not company_data.get('company_name'):
            raise ValueError("company_name is required in company_data")
        
        if not target_role or len(target_role.strip()) < 3:
            raise ValueError("target_role must be a valid job title")
        
        if num_variants < 1 or num_variants > 5:
            raise ValueError("num_variants must be between 1 and 5")
        
        logger.info(
            f"Generating {num_variants} {message_type.value} variants for "
            f"{company_data['company_name']} - {target_role}"
        )
        
        top_skills = resume_data.skills[:8] if resume_data.skills else []
        relevant_experience = resume_data.experience[:3] if resume_data.experience else []
        
        prompt = self.prompt_templates.format_personalization_prompt(
            candidate_name=resume_data.name,
            target_role=target_role,
            top_skills=top_skills,
            relevant_experience=relevant_experience,
            company_name=company_data['company_name'],
            company_mission=company_data.get('mission', ''),
            recent_news=company_data.get('recent_news', ''),
            open_roles=company_data.get('hiring_roles', []),
            key_people=company_data.get('key_people', []),
            message_type=message_type,
            tone=tone,
            num_variants=num_variants
        )
        
        system_prompt = self.prompt_templates.PERSONALIZATION_SYSTEM
        
        for attempt in range(self.max_retries):
            try:
                response = self.llm.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=self.temperature,
                    max_tokens=config.llm.max_tokens,
                    response_format='json'
                )

                parsed_response = self._parse_llm_response(response)

                if not parsed_response or 'variants' not in parsed_response:
                    logger.warning(f"Invalid response structure on attempt {attempt + 1}")
                    continue

                # filter variants to ensure they have at least 2 inline citations
                valid_variants = []
                for variant_data in parsed_response['variants']:
                    if not isinstance(variant_data, dict):
                        continue

                    message = variant_data.get('message', '')
                    citation_count = self._count_inline_sources(message)

                    if citation_count < 2:
                        logger.warning(f"Variant has only {citation_count} inline citations; skipping")
                        continue

                    valid_variants.append(variant_data)

                if not valid_variants:
                    logger.warning(f"No variants with 2+ citations on attempt {attempt + 1}; retrying")
                    continue

                variants = self._build_message_variants(
                    valid_variants,
                    message_type,
                    tone
                )

                if variants:
                    logger.info(f"Successfully generated {len(variants)} variants with 2+ citations")
                    return PersonalizationResult(
                        variants=variants,
                        company_name=company_data['company_name'],
                        target_role=target_role,
                        candidate_name=resume_data.name,
                        generation_metadata={
                            'attempt': attempt + 1,
                            'model': self.llm.config.model,
                            'temperature': self.temperature,
                            'skills_used': top_skills,
                            'message_type': message_type.value,
                            'tone': tone.value
                        }
                    )
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parsing failed on attempt {attempt + 1}: {e}")
                continue
            except Exception as e:
                logger.error(f"Generation failed on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                continue
        
        raise RuntimeError(
            f"Failed to generate messages after {self.max_retries} attempts"
        )
    
    def generate_from_resume_file(
        self,
        resume_path: str,
        target_role: str,
        company_data: Dict[str, Any],
        message_type: MessageType = MessageType.LINKEDIN_MESSAGE,
        tone: MessageTone = MessageTone.PROFESSIONAL,
        num_variants: int = 3
    ) -> PersonalizationResult:
        
        logger.info(f"Parsing resume from: {resume_path}")
        resume_data = self.resume_parser.parse(resume_path)
        
        return self.generate_outreach_messages(
            resume_data=resume_data,
            target_role=target_role,
            company_data=company_data,
            message_type=message_type,
            tone=tone,
            num_variants=num_variants
        )
    
    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        cleaned_response = response.strip()
        
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
        
        cleaned_response = cleaned_response.strip()
        
        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            start = cleaned_response.find('{')
            end = cleaned_response.rfind('}')
            
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned_response[start:end + 1])
                except json.JSONDecodeError:
                    pass
            
            return None
    
    def _build_message_variants(
        self,
        variants_data: List[Dict],
        message_type: MessageType,
        tone: MessageTone
    ) -> List[MessageVariant]:
        
        variants = []
        
        for variant_data in variants_data:
            if not isinstance(variant_data, dict):
                continue
            
            message = variant_data.get('message', '')
            if not message or len(message.strip()) < 20:
                continue
            
            word_count = len(message.split())
            
            max_words = {
                MessageType.LINKEDIN_CONNECTION: 120,
                MessageType.LINKEDIN_MESSAGE: 180,
                MessageType.EMAIL: 300
            }.get(message_type, 200)
            
            if word_count > max_words:
                logger.warning(
                    f"Variant exceeds word limit: {word_count} > {max_words}"
                )
                continue
            
            citations = variant_data.get('citations', [])
            if not isinstance(citations, list):
                citations = []
            
            if len(citations) < 1:
                logger.warning("Variant has no citations, may lack specificity")
            
            variants.append(MessageVariant(
                message=message.strip(),
                subject=variant_data.get('subject'),
                citations=citations,
                skills_highlighted=variant_data.get('skills_highlighted', []),
                word_count=word_count,
                message_type=message_type,
                tone=tone
            ))
        
        return variants


def generate_personalized_outreach(
    resume_path: str,
    target_role: str,
    company_data: Dict[str, Any],
    message_type: str = "linkedin_message",
    tone: str = "professional",
    num_variants: int = 3,
    model_name: str = "qwen3:4b-instruct"
) -> PersonalizationResult:
    
    try:
        msg_type = MessageType[message_type.upper()]
    except KeyError:
        raise ValueError(
            f"Invalid message_type: {message_type}. "
            f"Valid options: {[t.name.lower() for t in MessageType]}"
        )
    
    try:
        tone_enum = MessageTone[tone.upper()]
    except KeyError:
        raise ValueError(
            f"Invalid tone: {tone}. "
            f"Valid options: {[t.name.lower() for t in MessageTone]}"
        )
    
    agent = PersonalizationAgent(model_name=model_name)
    
    return agent.generate_from_resume_file(
        resume_path=resume_path,
        target_role=target_role,
        company_data=company_data,
        message_type=msg_type,
        tone=tone_enum,
        num_variants=num_variants
    )