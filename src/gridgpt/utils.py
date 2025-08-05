import yaml
from typing import Dict


def load_catalog(path="conf/base/catalog.yml") -> Dict:
    """
    Load catalog from YAML files.

    Returns:
        A dict containing file paths and their corresponding params
    """
    with open(path, "r") as file:
        catalog = yaml.safe_load(file)
    return catalog
