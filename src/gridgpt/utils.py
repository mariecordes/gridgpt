import os
import logging
import logging.config
import yaml
from typing import Dict


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
LOGGING_CONFIG_PATH = os.path.join(BASE_DIR, 'conf', 'logging.yml')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'info.log')
_LOGGING_ALREADY_CONFIGURED = False


def init_logging(overwrite: bool = False):
    global _LOGGING_ALREADY_CONFIGURED
    if _LOGGING_ALREADY_CONFIGURED:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        if os.path.exists(LOGGING_CONFIG_PATH):
            with open(LOGGING_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                raise ValueError('Logging config YAML did not parse to a dict')
            # Force absolute path
            if 'handlers' in config and 'info_file' in config['handlers']:
                handler_cfg = config['handlers']['info_file']
                handler_cfg['filename'] = LOG_FILE  # ensure absolute path
                # Only plain FileHandler uses mode; TimedRotatingFileHandler ignores it
                if handler_cfg.get('class') == 'logging.FileHandler':
                    handler_cfg['mode'] = 'w' if overwrite else 'a'
            logging.config.dictConfig(config)
        else:
            logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a')
    except Exception as e:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            f"Falling back to basicConfig due to logging setup error: {e} | Config path: {LOGGING_CONFIG_PATH}"
        )
    logging.getLogger(__name__).info('Logging initialized.')
    _LOGGING_ALREADY_CONFIGURED = True


def clear_log():
    """Truncate the log file manually when desired."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, 'w', encoding='utf-8'):
            pass
        logging.getLogger(__name__).info('Log file cleared.')
    except Exception as e:
        logging.getLogger(__name__).warning(f'Failed to clear log file: {e}')


def load_catalog(path="conf/base/catalog.yml") -> Dict:
    """
    Load catalog from YAML files.

    Returns:
        A dict containing file paths and their corresponding params
    """
    with open(path, "r") as file:
        catalog = yaml.safe_load(file)
    return catalog


def load_parameters(path="conf/base/parameters.yml") -> Dict:
    """
    Load parameters from YAML files.

    Returns:
        A dict containing general parameters
    """
    with open(path, "r") as file:
        params = yaml.safe_load(file)
    return params


def load_prompts(path="conf/base/prompts.yml") -> Dict:
    """
    Load prompt templates from YAML files.
    
    Returns:
        A dict containing prompt templates depending on the input path
    """
    with open(path, "r") as file:
        prompt_lib = yaml.safe_load(file)
    return prompt_lib
