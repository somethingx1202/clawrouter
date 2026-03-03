"""Tests for the query complexity classifier."""

import pytest
from solutions.complexity import classify_complexity


class TestClassifyComplexity:
    """Test heuristic complexity classification."""

    def test_simple_short_factual(self):
        assert classify_complexity("What color do you get when you mix red and blue?") == "simple"

    def test_simple_one_word_answer(self):
        assert classify_complexity("What planet is closest to the Sun?") == "simple"

    def test_moderate_explain(self):
        assert classify_complexity(
            "How does a blockchain work and what are its main use cases?"
        ) == "moderate"

    def test_moderate_difference(self):
        assert classify_complexity(
            "What is the difference between a recession and a depression, "
            "and how do economists distinguish between them?"
        ) == "moderate"

    def test_complex_design(self):
        assert classify_complexity(
            "Design a distributed system architecture for a real-time chat application "
            "that needs to handle 1 million concurrent users with sub-100ms latency."
        ) == "complex"

    def test_complex_mathematical_foundations(self):
        assert classify_complexity(
            "Explain the mathematical foundations of transformer attention mechanisms "
            "and their computational complexity implications."
        ) == "complex"

    def test_reasoning_puzzle(self):
        assert classify_complexity(
            "A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. "
            "How much does the ball cost?"
        ) == "reasoning"

    def test_reasoning_trick_question(self):
        assert classify_complexity(
            "If you're running a race and you pass the person in second place, "
            "what place are you in now?"
        ) == "reasoning"

    def test_coding_implement(self):
        assert classify_complexity(
            "Implement a rate limiter using the token bucket algorithm in Python."
        ) == "coding"

    def test_coding_sql(self):
        assert classify_complexity(
            "Create a SQL query to find all employees who earn more than their direct manager."
        ) == "coding"

    def test_coding_write_function(self):
        assert classify_complexity(
            "Write a Python function that merges two sorted linked lists into a single sorted linked list."
        ) == "coding"

    def test_long_query_defaults_complex(self):
        long_query = "word " * 85
        assert classify_complexity(long_query) == "complex"

    def test_medium_length_defaults_moderate(self):
        medium_query = "word " * 35
        assert classify_complexity(medium_query) == "moderate"

    def test_empty_query_is_simple(self):
        assert classify_complexity("") == "simple"

    def test_returns_valid_category(self):
        queries = [
            "Hello",
            "Explain quantum computing",
            "Write a function to sort a list",
            "What is 2+2?",
            "Design a microservices architecture for an e-commerce platform",
        ]
        valid = {"simple", "moderate", "complex", "reasoning", "coding"}
        for q in queries:
            assert classify_complexity(q) in valid, f"Invalid category for: {q}"
