import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Modules use paths relative to the repo root (conf/, data/), so make sure
# imports and file loading work no matter where pytest is invoked from.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture(scope="session", autouse=True)
def repo_root_cwd():
    os.chdir(REPO_ROOT)


@pytest.fixture(scope="session")
def word_db(repo_root_cwd):
    """Shared WordDatabaseManager instance (loading the DB once per session)."""
    from src.gridgpt.word_database_manager import WordDatabaseManager

    return WordDatabaseManager()


@pytest.fixture(scope="session")
def templates(repo_root_cwd):
    """All grid templates as a list."""
    from src.gridgpt.template_manager import load_templates

    return load_templates()["templates"]
