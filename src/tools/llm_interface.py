import json
import time
import logging
from typing import Optional, List, Dict, Any, Generator
from dataclasses import dataclass
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LLMConfig:
    """
    Configuration for LLM Interface
    """
    base_url: str = "http://localhost:11434"
    model: str = 'qwen3:4b-instruct'
    temperature: float = 0.7
    max_tokens: int = 900
    timeout: int = 120
    max_retries: int = 3
    retry_delay: float = 2.0
    top_p: float = 0.9
    top_k: int = 40

class OllamaInterface:
    """
    Interface for interacting with LLMs 
    Provides both synchronous and streaming responses
    """
    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initalize LLM interface
        """
        self.config = config or LLMConfig()
        self._verify_connection()

    def _verify_connection(self) -> bool:
        """Verify Ollama is running and accessible"""
        try:    
            response = requests.get(
                f'{self.config.base_url}/api/tags', 
                timeout = 5
            )
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]

                if self.config.model not in model_names:
                    logger.warning(
                        f'Model {self.config.model} not found.'
                        f"Available: {', '.join(model_names)}"
                    )
                    return False
                
        except RequestException as e:
            logger.error(
                f'Cannot connect to Ollama at {self.config.base_url}'
                f'Is Ollama running? Error: {e}'
            )
            return False
        
    def _make_request(
        self, endpoint: str, payload: Dict[str, Any], stream: bool = False
    ) -> requests.Response:
        """
        Make HTTP request to Ollama 
        """
        url = f"{self.config.base_url}/api/{endpoint}"
        for attempt in range(self.config.max_retries):
            try: 
                response = requests.post(url, json=payload, timeout=self.config.timeout, stream=stream)
                response.raise_for_status()
                return response
            
            except Timeout: 
                logger.warning(f"Request timeout (attempt {attempt+1}/{self.config.max_retries})")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                else:
                    raise 

            except ConnectionError:
                logger.error("Connection Error - is Ollama running?")
                raise

            except RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                else:
                    raise

            except RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                else:
                    raise
        
        raise RequestException("Max retries exceeded")
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, stop_sequences: Optional[List[str]] = None, response_format: Optional[Any] = None) -> Optional[str]:
        """
        Generate text from prompt
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
                "top_p": self.config.top_p,
                "top_k": self.config.top_k
            }
        }

        if response_format is not None:
            payload['format'] = response_format
        
        if system_prompt:
            payload["system"] = system_prompt
        
        if stop_sequences:
            payload["options"]["stop"] = stop_sequences
        
        try:
            logger.info(f"Generating completion (prompt length: {len(prompt)} chars)")
            start_time = time.time()
            
            response = self._make_request("generate", payload)
            result = response.json()
            
            elapsed = time.time() - start_time
            generated_text = result.get("response", "")
            
            logger.info(
                f"Generated {len(generated_text)} chars in {elapsed:.2f}s "
                f"({result.get('eval_count', 0)} tokens)"
            )
            
            return generated_text
            
        except RequestException as e:
            logger.error(f"Generation failed: {e}")
            return None
        
    def generate_stream(
      self, prompt: str, 
      system_prompt: Optional[str] = None,
      temperature: Optional[float] = None,
      max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """
        Generates text with streaming response
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
                "top_p": self.config.top_p,
                "top_k": self.config.top_k
            }
        }

        if system_prompt:
            payload['system'] = system_prompt
        try:
            response = self._make_request('generate', payload, stream=True)
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            yield chunk['response']
                    except json.JSONDecodeError:
                        logger.warning(f'Could not parse chunk: {line}')
                        continue

        except RequestException as e:
            logger.error(f"Streaming generation failed: {e}")
            yield ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """
        Chat completiong with message history
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
                "top_p": self.config.top_p,
                "top_k": self.config.top_k
            }
        }

        try:
            logger.info(f'Chat completion ({len(messages)} messages)')
            response = self._make_request('chat', payload=payload)
            result = response.json()
            message = result.get('message', {})
            content = message.get('content', "")
            logger.info(f'Chat response: {len(content)} chars')
            return content
        
        except RequestException as e:
            logger.error(f"Chat completion failed: {e}")
            return None
        
    def extract_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate and extract JSON from response
        """
        default_system = (
            "You are a helpful assistant that responds only with valid JSON. "
            "Do not include any markdown formatting, code blocks, or explanatory text. "
            "Return only the raw JSON object."
        )

        response = self.generate(
            prompt=prompt,
            system_prompt=system_prompt or default_system,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        if not response:
            return None
        
        cleaned = response.strip()
        
        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "", 1)
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```", "", 1)
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Raw response: {response[:200]}...")
            return None
        
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count (rough approximation)
        """
        return len(text.split()) + len(text) // 4
    
    def truncate_to_tokens(
        self,
        text: str,
        max_tokens: int,
        from_end: bool = False
    ) -> str:
        """
        Truncate text to approximate token limit
        """
        current_tokens = self.count_tokens(text)
        
        if current_tokens <= max_tokens:
            return text
        
        ratio = max_tokens / current_tokens
        target_chars = int(len(text) * ratio * 0.9)
        
        if from_end:
            return "..." + text[-target_chars:]
        else:
            return text[:target_chars] + "..."


