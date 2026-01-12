import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

try: 
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try: 
    from docx import Document
except ImportError:
    Document = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ResumeData:
    raw_text: str
    skills: List[str]
    experience: List[str]
    education: List[str]
    email: Optional[str]
    phone: Optional[str]
    name: Optional[str]

class ResumeParser:
    COMMON_SKILLS = {
        'python', 'java', 'javascript', 'typescript', 'react', 'node.js', 'angular',
        'vue', 'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'sql', 'nosql',
        'mongodb', 'postgresql', 'mysql', 'redis', 'git', 'ci/cd', 'jenkins',
        'machine learning', 'deep learning', 'nlp', 'computer vision', 'tensorflow',
        'pytorch', 'scikit-learn', 'pandas', 'numpy', 'rest', 'api', 'graphql',
        'microservices', 'agile', 'scrum', 'jira', 'linux', 'bash', 'shell',
        'html', 'css', 'sass', 'tailwind', 'bootstrap', 'django', 'flask',
        'fastapi', 'spring', 'express', 'go', 'rust', 'c++', 'c#', '.net',
        'swift', 'kotlin', 'android', 'ios', 'flutter', 'react native',
        'data analysis', 'data science', 'statistics', 'r', 'matlab',
        'tableau', 'power bi', 'spark', 'hadoop', 'kafka', 'airflow',
        'terraform', 'ansible', 'blockchain', 'web3', 'solidity', 'langchain', 'hugging face'
    }
    
    EXPERIENCE_KEYWORDS = [
        'experience', 'work history', 'employment', 'professional experience',
        'work experience', 'career history', 'positions held'
    ]
    
    EDUCATION_KEYWORDS = [
        'education', 'academic', 'degree', 'university', 'college',
        'bachelor', 'master', 'phd', 'certification', 'graduated'
    ]

    def __init__(self, custom_skills: Optional[Set[str]] = None):
        self.skills_database = self.COMMON_SKILLS.copy()
        if custom_skills: 
            self.skills_database.update(s.lower() for s in custom_skills)
        
    def parse(self, file_path: str) -> ResumeData:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f'Resume file not found: {file_path}')
        
        suffix = path.suffix.lower()

        if suffix == '.pdf':
            raw_text = self._extract_from_pdf(path)
        elif suffix in ['.docx', '.doc']:
            raw_text = self._extract_from_docx(path)
        elif suffix == '.txt':
            raw_text = path.read_text(encoding='utf-8', errors='ignore')
        else:
            raise ValueError
        
        if not raw_text or len(raw_text.strip()) < 50:
            raise ValueError("Extracted text is too short or empty")
        
        return ResumeData(
            raw_text=raw_text,
            skills=self._extract_skills(raw_text),
            experience=self._extract_experience(raw_text),
            education=self._extract_education(raw_text),
            email=self._extract_email(raw_text),
            phone=self._extract_phone(raw_text),
            name=self._extract_name(raw_text)
        )
    
    def parse_from_text(self, text: str) -> ResumeData:
        if not text or len(text.strip()) < 50:
            raise ValueError("Text is too short or empty")
        
        return ResumeData(
            raw_text=text,
            skills=self._extract_skills(text),
            experience=self._extract_experience(text),
            education=self._extract_education(text),
            email=self._extract_email(text),
            phone=self._extract_phone(text),
            name=self._extract_name(text)
        )
    
    def _extract_from_pdf(self, path: Path) -> str:
        if PdfReader is None:
            raise ImportError("pypdf is required for PDF parsing. Install with: pip install pypdf")
        
        try:
            reader = PdfReader(str(path))
            text_parts = []
            
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            
            return '\n'.join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract PDF: {e}")
            raise ValueError(f"Could not parse PDF: {e}")
    
    def _extract_from_docx(self, path: Path) -> str:
        if Document is None:
            raise ImportError("python-docx is required for DOCX parsing. Install with: pip install python-docx")
        
        try:
            doc = Document(str(path))
            text_parts = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
            return '\n'.join(text_parts)
        except Exception as e:
            logger.error(f"Failed to extract DOCX: {e}")
            raise ValueError(f"Could not parse DOCX: {e}")
    
    def _extract_skills(self, text: str) -> List[str]:
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.skills_database:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill.title())
        
        return sorted(set(found_skills))
    
    def _extract_experience(self, text: str) -> List[str]:
        lines = text.split('\n')
        experience_lines = []
        capturing = False
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            if any(kw in line_lower for kw in self.EXPERIENCE_KEYWORDS):
                capturing = True
                continue
            
            if capturing:
                if any(kw in line_lower for kw in self.EDUCATION_KEYWORDS):
                    break
                
                if line.strip() and len(line.strip()) > 10:
                    if re.search(r'\d{4}', line):
                        experience_lines.append(line.strip())
                    elif i > 0 and experience_lines:
                        experience_lines[-1] += ' ' + line.strip()
        
        return experience_lines[:10]
    
    def _extract_education(self, text: str) -> List[str]:
        lines = text.split('\n')
        education_lines = []
        capturing = False
        
        for line in lines:
            line_lower = line.lower()
            
            if any(kw in line_lower for kw in self.EDUCATION_KEYWORDS):
                capturing = True
                continue
            
            if capturing:
                if line.strip() and len(line.strip()) > 10:
                    if any(deg in line_lower for deg in ['bachelor', 'master', 'phd', 'b.s', 'm.s', 'b.a', 'm.a']):
                        education_lines.append(line.strip())
                    elif re.search(r'\d{4}', line) and education_lines:
                        education_lines[-1] += ' ' + line.strip()
        
        return education_lines[:5]
    
    def _extract_email(self, text: str) -> Optional[str]:
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, text)
        return matches[0] if matches else None
    
    def _extract_phone(self, text: str) -> Optional[str]:
        phone_patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        ]
        
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        
        return None
    
    def _extract_name(self, text: str) -> Optional[str]:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        if not lines:
            return None
        
        first_line = lines[0]
        
        if len(first_line.split()) <= 4 and len(first_line) < 50:
            if not re.search(r'[@\d]', first_line):
                return first_line
        
        return None


def parse_resume(file_path: str, custom_skills: Optional[Set[str]] = None) -> ResumeData:
    parser = ResumeParser(custom_skills=custom_skills)
    return parser.parse(file_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.utils.resume_parser <resume_file>")
        sys.exit(1)
    
    try:
        resume_data = parse_resume(sys.argv[1])
        
        print("\n=== RESUME PARSING RESULTS ===\n")
        print(f"Name: {resume_data.name or 'Not found'}")
        print(f"Email: {resume_data.email or 'Not found'}")
        print(f"Phone: {resume_data.phone or 'Not found'}")
        print(f"\nSkills ({len(resume_data.skills)}):")
        for skill in resume_data.skills[:20]:
            print(f"  - {skill}")
        print(f"\nExperience ({len(resume_data.experience)} entries):")
        for exp in resume_data.experience[:5]:
            print(f"  - {exp[:100]}...")
        print(f"\nEducation ({len(resume_data.education)} entries):")
        for edu in resume_data.education:
            print(f"  - {edu}")
        
    except Exception as e:
        logger.error(f"Failed to parse resume: {e}")
        sys.exit(1)