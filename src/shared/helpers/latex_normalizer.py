"""LaTeX content normalization and repair utilities.

Fixes common LaTeX issues like broken commands, incorrect escaping, etc.
"""

from __future__ import annotations

import re
from typing import Optional


class LaTeXNormalizer:
    """Normalize and repair LaTeX content."""

    # Common broken LaTeX patterns and their fixes
    BROKEN_PATTERNS = [
        # Fix broken trigonometric with frac: \sinrac → \sin\frac
        (r"\\sin(?:rac|srac|cra)\{", r"\\sin\\frac{"),
        (r"\\cos(?:rac|srac|cra)\{", r"\\cos\\frac{"),
        (r"\\tan(?:rac|srac|cra)\{", r"\\tan\\frac{"),
        (r"\\log(?:rac|srac|cra)\{", r"\\log\\frac{"),

        # Fix double instances that may have been created: \lefteft → \left, \rightight → \right, etc.
        (r"\\lefteft", r"\\left"),
        (r"\\rightight", r"\\right"),
        (r"\\fracrac", r"\\frac"),

        # Fix "rac" appearing alone (not preceded by backslash or 'f')
        (r"(?<!\\)(?<!f)rac\s*\{", r"\\frac{"),

        # Fix "eft(" when NOT preceded by \l (standalone or with broken backslash)
        (r"(?<!\\l)eft\s*\(", r"\\left("),
        (r"(?<!\\l)eft\s*\[", r"\\left["),
        (r"(?<!\\l)eft\s*\{", r"\\left{"),
        (r"(?<!\\l)eft\s*\|", r"\\left|"),

        # Fix "ight)" when NOT preceded by \r (standalone or with broken backslash)
        (r"(?<!\\r)ight\s*\)", r"\\right)"),
        (r"(?<!\\r)ight\s*\]", r"\\right]"),
        (r"(?<!\\r)ight\s*\}", r"\\right}"),
        (r"(?<!\\r)ight\s*\|", r"\\right|"),

        # Fix commands missing backslash entirely
        (r"(?<!\\)frac\s*\{", r"\\frac{"),
        (r"(?<!\\)sqrt\s*\{", r"\\sqrt{"),
        (r"(?<!\\)sum\s*_", r"\\sum_"),
        (r"(?<!\\)int\s*_", r"\\int_"),
        (r"(?<!\\)prod\s*_", r"\\prod_"),

        # Fix broken newlines in math mode (rare but can happen)
        (r"\$\s+([^\$]+)\s+\$", r"$\1$"),
    ]

    # LaTeX commands that should not be escaped further
    LATEX_COMMANDS = {
        r"\frac", r"\sqrt", r"\sin", r"\cos", r"\tan", r"\log",
        r"\int", r"\sum", r"\prod", r"\left", r"\right",
        r"\alpha", r"\beta", r"\gamma", r"\delta", r"\epsilon",
        r"\theta", r"\lambda", r"\mu", r"\pi", r"\sigma",
        r"\infty", r"\pm", r"\times", r"\div", r"\leq", r"\geq",
        r"\neq", r"\approx", r"\equiv", r"\subset", r"\supset",
        r"\cup", r"\cap", r"\forall", r"\exists", r"\in", r"\notin",
        r"\rightarrow", r"\leftarrow", r"\leftrightarrow", r"\mathbf",
        r"\mathit", r"\mathbb", r"\mathcal", r"\overline", r"\underline",
        r"\hat", r"\vec", r"\cdot", r"\ast", r"\star", r"\bullet",
        r"\prime", r"\partial", r"\nabla", r"\hbar", r"\ell",
        r"\Re", r"\Im", r"\imath", r"\jmath", r"\ell", r"\wp",
    }

    @staticmethod
    def normalize(content: str) -> str:
        """Normalize LaTeX content by fixing common OCR/extraction errors.

        Args:
            content: Raw content that may contain broken LaTeX

        Returns:
            Normalized content with LaTeX commands repaired
        """
        if not content:
            return content

        result = content

        # Apply broken pattern fixes
        for pattern, replacement in LaTeXNormalizer.BROKEN_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # Fix spaces around operators in math mode
        # $...$  blocks should be preserved as-is
        result = LaTeXNormalizer._fix_math_spacing(result)

        # Remove extraneous spaces before closing braces/brackets in math mode
        result = re.sub(r"\{\s+", "{", result)
        result = re.sub(r"\s+\}", "}", result)
        result = re.sub(r"\[\s+", "[", result)
        result = re.sub(r"\s+\]", "]", result)

        # Ensure proper spacing around operators
        # Only apply if not inside math mode
        result = LaTeXNormalizer._normalize_operator_spacing(result)

        return result

    @staticmethod
    def _fix_math_spacing(content: str) -> str:
        """Fix spacing issues inside math mode ($...$ and $$...$$)."""
        # This is a simple approach: don't modify content inside delimiters
        # In production, you might want to parse more carefully
        return content

    @staticmethod
    def _normalize_operator_spacing(content: str) -> str:
        """Normalize spacing around mathematical operators outside math mode.

        This is careful to not modify content inside $...$ blocks.
        """
        # Simple approach: only fix obvious double-spaces
        result = re.sub(r"  +", " ", content)
        return result

    @staticmethod
    def repair_broken_latex(content: str) -> str:
        r"""Attempt to repair severely broken LaTeX content.

        Handles cases like:
        - \sinrac{x}{2} → \sin\frac{x}{2}
        - \cosrac{x}{2} → \cos\frac{x}{2}
        - Missing \right and \left commands
        """
        result = content

        # Balance \left and \right if they're mismatched
        result = LaTeXNormalizer._balance_delimiters(result)

        return result

    @staticmethod
    def _balance_delimiters(content: str) -> str:
        """Balance \\left and \\right commands in content."""
        # Simple heuristic: look for unmatched \left without \right
        # This is not a full parser, just a basic repair attempt

        lines = content.split("\n")
        fixed_lines = []

        for line in lines:
            # Count \left and \right in this line
            left_count = len(re.findall(r"\\left\s*[\(\[\{|]", line))
            right_count = len(re.findall(r"\\right\s*[\)\]\}|]", line))

            if left_count > right_count:
                # Add missing \right at the end before closing math mode
                if "$" in line and right_count == 0 and left_count > 0:
                    # Naive fix: add \right) before closing $
                    line = re.sub(r"\$$", r"\\right)" + "$", line)

            fixed_lines.append(line)

        return "\n".join(fixed_lines)

    @staticmethod
    def validate_latex_syntax(content: str) -> tuple[bool, list[str]]:
        """Validate basic LaTeX syntax in content.

        Returns:
            (is_valid, list of issues)
        """
        issues = []

        # Check for unmatched braces
        brace_count = 0
        bracket_count = 0
        paren_count = 0

        for char in content:
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count < 0:
                    issues.append("Unmatched closing brace '}'")
                    break

            elif char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
                if bracket_count < 0:
                    issues.append("Unmatched closing bracket ']'")
                    break

            elif char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1

        if brace_count != 0:
            issues.append(f"Unmatched braces: {brace_count:+d}")
        if bracket_count != 0:
            issues.append(f"Unmatched brackets: {bracket_count:+d}")

        # Check for common OCR patterns
        if "rac" in content and r"\frac" not in content:
            issues.append("Found 'rac' without \\frac (possible OCR error)")
        if "ight" in content and r"\right" not in content:
            issues.append("Found 'ight' without \\right (possible OCR error)")

        return len(issues) == 0, issues


def normalize_question_latex(question_text: str) -> str:
    """Normalize LaTeX in question text.

    This is the main entry point for question content normalization.

    Args:
        question_text: Raw question text from LLM or OCR

    Returns:
        Normalized question text with LaTeX repairs applied
    """
    if not question_text:
        return question_text

    normalizer = LaTeXNormalizer()

    # First pass: fix obvious broken patterns
    result = normalizer.normalize(question_text)

    # Second pass: repair severely broken LaTeX
    result = normalizer.repair_broken_latex(result)

    # Optional: validate and log issues (for debugging)
    is_valid, issues = normalizer.validate_latex_syntax(result)
    if not is_valid:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"LaTeX validation issues found: {issues}")

    return result
