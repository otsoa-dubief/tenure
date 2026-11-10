"""Test setup: tenure is imported as a package from the repository's tenure/ directory."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
