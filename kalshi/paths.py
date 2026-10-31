"""Where things live. DATA is git-ignored caches; PAPER_DATA is tracked forward-test logs."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PAPER = os.path.join(ROOT, "paper")
PAPER_DATA = os.path.join(PAPER, "data")
