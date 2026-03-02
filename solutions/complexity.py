"""
Query Complexity Classification.

Heuristic classifier using keyword matching and structural analysis.
Classifies queries into: simple, moderate, complex, reasoning, coding.
"""

import re
from typing import Literal

ComplexityClass = Literal["simple", "moderate", "complex", "reasoning", "coding"]

_SENTENCE_SPLIT = re.compile(r'[.!?]')

CODING_KEYWORDS = (
    "implement ", "write a function", "write a python", "write code",
    "sql query", "create a sql", "create a query",
    "function that", "data structure",
    "trie", "linked list", "binary tree", "hash map",
    "thread-safe", "producer-consumer",
    r"\bserialize and deserialize\b",
    r"\blru cache\b",
    r"\bimplement a\b",
    r"\bwrite a .*\b(function|class|method|script|program)",
)

REASONING_KEYWORDS = (
    "how much does", "what place",
    "how long does it take", "measure exactly",
    "puzzle", "riddle", "trick question",
    "most people assume", "most people say",
    "counterintuitive", "where did the",
    "if you're running a race",
    "look up the current", "search for the current",
)

COMPLEX_KEYWORDS = (
    "design a", "analyze the", "compare the",
    "trade-offs", "tradeoffs", "trade offs",
    "derive", "prove that", "mathematical foundations",
    "architecture", "distributed system",
    "game-theoretic", "bayesian", "equilibrium",
    "computational complexity",
    "explain how .* work.* and",
    "what are the .* consequences",
)

MODERATE_KEYWORDS = (
    "explain", "describe", "what is the difference",
    "what are the key differences",
    "how does .* work", "how do .* work",
    "why does", "why do",
    "what makes",
)


def classify_complexity(query: str) -> ComplexityClass:
    """
    Classify query complexity using fast heuristics.

    Priority order (most specific first): coding > reasoning > complex > moderate > simple.
    Falls back to structural heuristics (word count, punctuation) if no keywords match.
    """
    query_lower = query.lower().strip()
    word_count = len(query_lower.split())

    if _matches_any(query_lower, CODING_KEYWORDS):
        return "coding"

    if _matches_any(query_lower, REASONING_KEYWORDS):
        return "reasoning"

    if _matches_any(query_lower, COMPLEX_KEYWORDS):
        return "complex"

    if _matches_any(query_lower, MODERATE_KEYWORDS):
        return "moderate"

    question_marks = query.count("?")
    dashes = query.count("\u2014") + query.count("--")
    sentence_count = len([s for s in _SENTENCE_SPLIT.split(query) if s.strip()])

    if word_count > 80 or (question_marks >= 2 and word_count > 40):
        return "complex"

    if word_count > 30 or dashes >= 1 or sentence_count >= 3:
        return "moderate"

    return "simple"


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Check if text matches any pattern. Patterns with regex metacharacters are compiled."""
    for pattern in patterns:
        if "\\" in pattern or ".*" in pattern:
            if re.search(pattern, text):
                return True
        else:
            if pattern in text:
                return True
    return False
