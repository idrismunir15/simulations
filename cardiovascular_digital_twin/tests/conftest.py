"""
conftest.py — ensure the repository root is on sys.path so tests can
import the cardiovascular_digital_twin package by its full name.
"""

import sys
import os

# Insert the repository root (parent of cardiovascular_digital_twin/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
