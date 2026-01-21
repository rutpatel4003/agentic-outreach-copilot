from typing import Dict, List, Optional
from enum import Enum

class MessageTone(Enum):
    PROFESSIONAL = 'professional'
    CASUAL = 'casual'
    ENTHUSIASTIC = 'enthusiastic'

class MessageType(Enum):
    LINKEDIN_CONNECTION = 'linkedin_connection'
    LINKEDIN_MESSAGE = 'linkedin_message'
    EMAIL = 'email'

class PromptTemplates:
    PERSONALIZATION_SYSTEM = """You are an expert cold outreach writer specializing in job applications. Your messages are:
- Authentic and personalized (never generic)
- Concise (under 150 words for LinkedIn, under 250 for email)
- Fact-based (cite specific company information)
- Action-oriented (clear call-to-action)
- Professional yet human

CRITICAL RULES:
1. ALWAYS cite sources using [source: page_name] format
2. NEVER make claims not found in provided company data
3. Connect candidate skills to specific company needs
4. Use the specified tone consistently
5. End with a clear, low-pressure CTA

ABSOLUTELY FORBIDDEN - DO NOT DO THIS:
NEVER write "At [Company Name], I built..." - the candidate has NEVER worked at the target company
NEVER claim the candidate has past experience AT the company they're applying to
The candidate is APPLYING for a job, they are NOT a current or former employee
"Relevant Experience" is from OTHER companies (past jobs), NOT the target company
Correct: "In my previous role at [Other Company], I built..."
Correct: "I've architected AWS pipelines that could help Nuro scale..."
Correct: "My experience with [skill] aligns with Nuro's mission to..."
WRONG: "At Nuro, I architected..." (they don't work there!)"""

    PERSONALIZATION_TEMPLATE = """Generate a personalized {message_type} for a job application.

CANDIDATE PROFILE (THE SENDER - this is who is WRITING the message):
Name: {candidate_name}
Target Role: {target_role}
Top Skills: {top_skills}
Relevant Experience (from PAST jobs at OTHER companies): {relevant_experience}

CRITICAL INSTRUCTIONS:
- {candidate_name} is the SENDER (the person applying for the job)
- Write from {candidate_name}'s perspective ("I", "my", "me")
- DO NOT address the message to {candidate_name} - that's the sender's own name!
- For LinkedIn messages: Start with "Hi," or skip greeting entirely
- For emails: Use "Hi [Hiring Manager]," or "Hello,"
- NEVER write "Hi {candidate_name}" - that makes no sense!
- For LinkedIn messages: Do NOT include email-style sign-offs like "Best regards," "Sincerely," or your name at the end. Just end with your CTA question.
- For emails only: You may include a brief sign-off and your first name.

REMINDER: The candidate is APPLYING to {company_name}. They have NEVER worked there before.
Do NOT write "At {company_name}, I..." - that would be a lie!

COMPANY INFORMATION:
Company Name: {company_name}
Mission/About: {company_mission}
Recent News: {recent_news}
Open Roles: {open_roles}
Key People: {key_people}

REQUIREMENTS:
1. Message Type: {message_type}
2. Tone: {tone}
3. Word Limit: {word_limit} words maximum
4. Must cite at least 2 specific facts from company data using [source: page] format
5. Connect 2-3 candidate skills to company needs
6. End with clear CTA: {cta_type}

VARIANT FOCUS - CRITICAL REQUIREMENT:
This variant MUST focus exclusively on: {variant_focus}

FOCUS GUIDELINES:
- If "Mission/About": Lead with company mission, values, or core technology. Cite [source: about]
- If "Recent News": Lead with specific recent achievement, announcement, or milestone. Cite [source: news]
- If "Open Roles": Lead with job description alignment, team needs, or role requirements. Cite [source: careers]
- If "Team/People": Lead with team structure, leadership, or specific people mentioned. Cite [source: team]

The opening sentence MUST be completely different from other variants.
DO NOT use generic openings like "I'm applying for..." or "I wanted to reach out..."
Instead, start with the focus area directly (e.g., "Your recent launch of X...", "Your mission to Y...", "The role's focus on Z...")

CITATIONS (mandatory):
- Include at least 2 inline citations in the message body.
- Citations MUST be exactly one of: [source: about], [source: careers], [source: news], [source: team]
- Do NOT cite raw URLs. Do NOT invent sources.
PERSPECTIVE:
- You are the candidate reaching out. Never say "our company/team" or imply you work there.

{revision_feedback}

Generate {num_variants} variants (slightly different angles/openings).

OUTPUT FORMAT (JSON):
{{
    "variants": [
        {{
            "message": "The full message text",
            "subject": "Email subject line (email only, otherwise null)",
            "citations": ["List of facts cited with sources"],
            "skills_highlighted": ["Skills mentioned"],
            "word_count": 123
        }}
    ]
}}"""

    GUARDRAILS_CHECK_SYSTEM = """You are a fact-checking assistant. Your job is to verify claims in outreach messages against source material.

CRITICAL RULES:
1. IGNORE subjective/relationship statements about the recipient (e.g., "impressed by your profile", "love your background", "excited about", "passionate about") - these are NOT fact claims requiring verification
2. IGNORE statements about the candidate's own skills/experience - only verify company facts
3. ONLY verify factual claims about the company (mission, products, news, people, achievements)

EXTREMELY IMPORTANT:
- If a sentence says "I built...", "I architected...", "I developed..." → This is about the CANDIDATE, NOT the company. DO NOT check it.
- If a sentence starts with "At [Company]" but then talks about what "I" did → This is the candidate describing their PAST work (they're applying TO the company, not FROM the company). DO NOT check it.
- ONLY check claims that directly describe the COMPANY itself (e.g., "Nuro is building autonomous delivery vehicles")

For each FACTUAL claim about the company:
1. Verify if it appears in the source material
2. Paraphrases are acceptable if they preserve accuracy
3. Only flag claims that are clearly false or completely absent from source material

Be reasonable - if a claim is a close paraphrase of source content, mark it as verified."""

    GUARDRAILS_CHECK_TEMPLATE = """Verify ONLY factual claims about the company in this outreach message.

MESSAGE:
{message}

SOURCE MATERIAL:
{source_material}

WHAT TO CHECK:
- Company mission statements, values, or goals
- Company products, services, or technologies
- Recent news, announcements, or achievements
- Information about company people (founders, team members)

WHAT TO IGNORE (DO NOT FLAG):
- Subjective statements about the recipient ("impressed by", "excited about", "love your")
- Statements about the candidate's own skills/experience (starts with "I built", "I architected", "My experience with")
- Statements like "At [Company], I..." - this is the candidate describing their PAST work at OTHER companies, NOT a claim about the target company
- Generic industry statements
- Relationship-building phrases

CRITICAL: The candidate is APPLYING to the company. They have NOT worked there before.
Any sentence with "I" as the subject is describing the CANDIDATE'S experience, not the company's facts.

For each FACTUAL claim about the company:
1. Can it be verified in source material (exact or paraphrase)?
2. If unverified, what is the specific claim?

OUTPUT FORMAT (JSON):
{{
    "all_claims_verified": true/false,
    "verified_claims": ["List of verified claims"],
    "unverified_claims": [
        {{"claim": "The specific claim", "reason": "Why it cannot be verified"}}
    ],
    "recommendation": "approve/revise/reject"
}}"""

    TONE_CHECK_SYSTEM = """You are a tone analysis expert. Evaluate if the message matches the requested tone and is appropriate for professional outreach.

Tone Guidelines:
- Professional: Formal, respectful, business-appropriate
- Casual: Friendly but still respectful, conversational
- Enthusiastic: Energetic and passionate, but not over-the-top

Red Flags:
- Excessive flattery or sycophancy
- Pushy or aggressive language
- Overly familiar or informal (unless casual tone requested)
- Desperate or begging tone
- Generic buzzwords without substance"""

    TONE_CHECK_TEMPLATE = """Analyze the tone of this outreach message.

MESSAGE:
{message}

REQUESTED TONE: {requested_tone}

Evaluate:
1. Does it match the requested tone?
2. Is it appropriate for professional outreach?
3. Any red flags or concerns?
4. Tone consistency throughout?

OUTPUT FORMAT (JSON):
{{
    "tone_match": true/false,
    "detected_tone": "description",
    "appropriateness_score": 0-10,
    "red_flags": ["List any concerns"],
    "recommendation": "approve/revise",
    "revision_suggestions": ["Optional suggestions if revise"]
}}"""

    REPLY_CLASSIFICATION_SYSTEM = """You are an email reply classifier. Categorize incoming replies to outreach messages.

Categories:
- INTERESTED: Positive response, wants to continue conversation
- NOT_INTERESTED: Polite decline or not hiring
- NEEDS_INFO: Asking for more information or clarification
- OUT_OF_OFFICE: Auto-reply or unavailable
- SPAM: Irrelevant or automated response"""

    REPLY_CLASSIFICATION_TEMPLATE = """Classify this reply to a job outreach message.

ORIGINAL MESSAGE:
{original_message}

REPLY:
{reply_text}

Determine:
1. Primary category
2. Sentiment (positive/neutral/negative)
3. Action needed (respond/wait/close)
4. Key points from reply

OUTPUT FORMAT (JSON):
{{
    "category": "INTERESTED/NOT_INTERESTED/NEEDS_INFO/OUT_OF_OFFICE/SPAM",
    "sentiment": "positive/neutral/negative",
    "action_needed": "respond/wait/close",
    "key_points": ["Main points from reply"],
    "confidence": 0.0-1.0
}}"""

    REPLY_SUGGESTION_SYSTEM = """You are an expert at writing professional follow-up responses. Create appropriate replies based on the context.

Guidelines:
- Match the tone of their reply
- Be prompt and direct
- Provide requested information clearly
- Suggest next steps (call, meeting, portfolio review)
- Keep it brief (under 100 words)"""

    REPLY_SUGGESTION_TEMPLATE = """Generate a response to this reply.

ORIGINAL OUTREACH:
{original_message}

THEIR REPLY:
{reply_text}

REPLY CLASSIFICATION:
{classification_result}

CANDIDATE INFO:
{candidate_info}

Generate {num_variants} response variants appropriate for the situation.

OUTPUT FORMAT (JSON):
{{
    "variants": [
        {{
            "message": "The response text",
            "subject": "Email subject (if replying to email)",
            "tone": "professional/casual/enthusiastic",
            "suggested_action": "call/meeting/info"
        }}
    ]
}}"""

    @staticmethod
    def format_personalization_prompt(
        candidate_name: str,
        target_role: str,
        top_skills: List[str],
        relevant_experience: List[str],
        company_name: str,
        company_mission: str,
        recent_news: Optional[str],
        open_roles: Optional[List[str]],
        key_people: Optional[List[str]],
        message_type: MessageType,
        tone: MessageTone,
        num_variants: int = 3,
        revision_feedback: Optional[List[str]] = None,
        variant_focus: str = "Mission/About"
    ) -> str:
        word_limits = {
            MessageType.LINKEDIN_CONNECTION: 100,
            MessageType.LINKEDIN_MESSAGE: 150,
            MessageType.EMAIL: 250
        }

        cta_types = {
            MessageType.LINKEDIN_CONNECTION: "Connect to continue conversation",
            MessageType.LINKEDIN_MESSAGE: "Schedule brief call or ask for referral",
            MessageType.EMAIL: "Schedule call or request portfolio review"
        }

        feedback_text = ""
        if revision_feedback:
            feedback_text = (
                "\nPREVIOUS ATTEMPT HAD ISSUES - FIX THESE:\n"
                + "\n".join(f"- {fb}" for fb in revision_feedback)
                + "\n"
            )

        return PromptTemplates.PERSONALIZATION_TEMPLATE.format(
            candidate_name=candidate_name or "I",
            target_role=target_role,
            top_skills=", ".join(top_skills[:5]),
            relevant_experience="\n".join(f"- {exp}" for exp in relevant_experience[:3]),
            company_name=company_name,
            company_mission=company_mission or "No mission statement found",
            recent_news=recent_news or "No recent news found",
            open_roles=", ".join(open_roles) if open_roles else "No specific roles found",
            key_people=", ".join(key_people) if key_people else "No key people identified",
            message_type=message_type.value.replace('_', ' ').title(),
            tone=tone.value.title(),
            word_limit=word_limits[message_type],
            cta_type=cta_types[message_type],
            num_variants=num_variants,
            revision_feedback=feedback_text,
            variant_focus=variant_focus
        )
    
    @staticmethod
    def format_guardrails_check(message: str, source_material: Dict[str, str]) -> str:
        formatted_sources = '\n\n'.join(
            f'--- {page.upper()} PAGE ---\n{content}'
            for page, content in source_material.items()
            if content
        )

        return PromptTemplates.GUARDRAILS_CHECK_TEMPLATE.format(
            message=message,
            source_material=formatted_sources
        )
    
    @staticmethod
    def format_tone_check(message: str, requested_tone: MessageTone) -> str:
        return PromptTemplates.TONE_CHECK_TEMPLATE.format(
            message=message,
            requested_tone=requested_tone.value.title()
        )
    
    @staticmethod
    def format_reply_classification(original_message: str, reply_text: str) -> str:
        return PromptTemplates.REPLY_CLASSIFICATION_TEMPLATE.format(
            original_message=original_message,
            reply_text=reply_text
        )
    
    @staticmethod
    def format_reply_suggestion(
        original_message: str,
        reply_text: str,
        classification_result: str,
        candidate_info: Dict[str, any],
        num_variants: int = 2
    ) -> str:
        candidate_summary = f"""
Name: {candidate_info.get('name', 'Candidate')}
Skills: {', '.join(candidate_info.get('skills', [])[:5])}
Contact: {candidate_info.get('email', 'Not provided')}
        """.strip()
        
        return PromptTemplates.REPLY_SUGGESTION_TEMPLATE.format(
            original_message=original_message,
            reply_text=reply_text,
            classification_result=classification_result,
            candidate_info=candidate_summary,
            num_variants=num_variants
        )

