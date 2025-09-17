import os
import logging
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")


class LLMConnection:
    def __init__(self):
        self.llm: Optional[OpenAI] = None
        self.model_name = DEFAULT_MODEL
        self.llm_connection_success = self.init_llm_connection()

    def init_llm_connection(self):
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")  # optional custom gateway
            if not api_key:
                raise ValueError("Missing OPENAI_API_KEY environment variable.")
            if base_url:
                self.llm = OpenAI(api_key=api_key, base_url=base_url)
            else:
                self.llm = OpenAI(api_key=api_key)
            logger.info("Connected to OpenAI API.")
            return True
        except Exception as e:
            logger.error(f"Error connecting to OpenAI: {e}")
            return False