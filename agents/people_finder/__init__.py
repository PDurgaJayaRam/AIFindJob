# Import from the agent implementation in this package
# Note: Do NOT modify sys.path - this would break imports from sister packages

import importlib.util
from pathlib import Path

# Load PeopleFinderAgent from finder.py in this same package
spec = importlib.util.spec_from_file_location(
    "agents.people_finder.finder_module",
    Path(__file__).parent / "finder.py"
)
finder_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finder_module)

# Re-export the agent class
PeopleFinderAgent = finder_module.PeopleFinderAgent

__all__ = ["PeopleFinderAgent"]