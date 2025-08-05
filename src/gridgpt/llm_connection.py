import os
import logging

from openai import AzureOpenAI

# Required environment variables for Azure OpenAI:
# AZURE_API_KEY - Your Azure OpenAI API key
# AZURE_ENDPOINT - Your Azure OpenAI endpoint URL
# AZURE_API_VERSION - API version (default: 2023-05-15)
# 
# Optional:
# AZURE_GPT4_DEPLOYMENT - Deployment name for GPT-4 model (default: "gpt-4o-mini")

# Alternatively, load from .env file
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LLMConnection:
    def __init__(self):
        """Initialize the LLM connection."""
        self.llm_connection_success = self.init_llm_connection()
    
    def init_llm_connection(self, provider: str = "azure-openai"):
        """Initialize the connection to the LLM."""
        
        # TODO: Add support for other providers in the future
        if provider.lower() != "azure-openai":
            raise ValueError("Currently, only 'azure-openai' provider is supported.")
        
        try:
            # Get Azure OpenAI credentials from environment variables
            azure_api_key = os.environ.get("AZURE_API_KEY")
            azure_endpoint = os.environ.get("AZURE_ENDPOINT")
            azure_api_version = os.environ.get("AZURE_API_VERSION", "2023-05-15")
            
            if not azure_api_key or not azure_endpoint:
                raise ValueError("Missing Azure OpenAI credentials. Please set AZURE_API_KEY and AZURE_ENDPOINT environment variables.")
            
            self.llm = AzureOpenAI(
                api_key=azure_api_key,
                azure_endpoint=azure_endpoint,
                api_version=azure_api_version
            )
            logger.info(f"Connected to Azure OpenAI.")
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to LLM: {e}")
            return False