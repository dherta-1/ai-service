"""Tests for LaTeX normalization utilities."""

from src.shared.helpers.latex_normalizer import (
    LaTeXNormalizer,
    normalize_question_latex,
)
from src.shared.helpers.to_latex_table_parser import (
    parse_markdown_table,
    parse_html_table,
    table_to_latex,
)


class TestLatexNormalizer:
    """Test LaTeX normalization and repair."""

    def test_normalize_sinrac_to_sin_frac(self):
        r"""Test fixing \sinrac pattern."""
        input_text = r"Cho A và B là hai biến cố. $\sinrac{x}{2}$"
        result = normalize_question_latex(input_text)
        assert r"\sin" in result
        assert r"\frac" in result

    def test_normalize_cosrac_to_cos_frac(self):
        r"""Test fixing \cosrac pattern."""
        input_text = r"Tính $\cosrac{x}{2}$"
        result = normalize_question_latex(input_text)
        assert r"\cos" in result
        assert r"\frac" in result

    def test_normalize_broken_right_delimiter(self):
        """Test fixing broken \\right command."""
        # Missing backslash before 'ight'
        input_text = r"$\left(\sinrac{x}{2}ight)$"
        result = normalize_question_latex(input_text)
        # Should fix to \right)
        assert r"\right)" in result or r"\\right)" in result

    def test_fix_broken_left_delimiter(self):
        """Test fixing broken \\left command."""
        input_text = r"$eft(x+y\right)$"
        result = normalize_question_latex(input_text)
        assert r"\left(" in result

    def test_fix_missing_frac_backslash(self):
        """Test adding missing backslash to frac."""
        input_text = r"rac{a}{b}"
        result = normalize_question_latex(input_text)
        assert r"\frac" in result

    def test_normalize_with_multiplication(self):
        """Test normalization preserves multiplication."""
        input_text = r"$\sin\left(\frac{x}{2}-\cos\left(\frac{x}{2}\right)\right)^2$"
        result = normalize_question_latex(input_text)
        # Should still be valid
        assert r"\sin" in result
        assert r"\cos" in result
        assert r"\frac" in result

    def test_validate_latex_syntax_balanced_braces(self):
        """Test validation of balanced braces."""
        text = r"$\frac{a}{b}$"
        is_valid, issues = LaTeXNormalizer.validate_latex_syntax(text)
        assert is_valid
        assert len(issues) == 0

    def test_validate_latex_syntax_unbalanced_braces(self):
        """Test validation detects unbalanced braces."""
        text = r"$\frac{a}{b$"
        is_valid, issues = LaTeXNormalizer.validate_latex_syntax(text)
        assert not is_valid
        assert any("brace" in issue.lower() for issue in issues)

    def test_validate_latex_syntax_ocr_errors(self):
        """Test validation detects OCR errors."""
        text = r"Some text with rac and ight"
        is_valid, issues = LaTeXNormalizer.validate_latex_syntax(text)
        assert not is_valid
        # Should detect OCR patterns
        detected_ocr = any("ocr" in issue.lower() for issue in issues)
        assert detected_ocr or any("rac" in issue for issue in issues)

    def test_normalize_complex_expression(self):
        """Test normalization of complex LaTeX expression."""
        input_text = (
            r"Cho hàm số $f(x)=\left(\sinrac{x}{2}-\cosrac{x}{2}"
            r"ight)^2$. Khẳng định nào sau đây là đúng?"
        )
        result = normalize_question_latex(input_text)

        # Should fix broken patterns
        assert r"\sin" in result
        assert r"\cos" in result
        assert r"\frac" in result

    def test_normalize_integral_expression(self):
        """Test normalization of integral expression."""
        input_text = (
            r"Ta có $\int_{-1}^{1}\left|e^{x}-1"
            r"ight|dx=ae+be^{-1}+c$ với $a,b,c \in \mathbb{Z}$."
        )
        result = normalize_question_latex(input_text)

        # Should fix broken \right
        assert r"\int" in result
        # Check that normalization was applied
        assert r"\right|" in result or "ight" not in result


class TestTableParser:
    """Test table parsing utilities."""

    def test_parse_markdown_table_basic(self):
        """Test parsing basic markdown table."""
        table_text = """| Header 1 | Header 2 |
|----------|----------|
| Row 1    | Data 1   |
| Row 2    | Data 2   |"""

        result = parse_markdown_table(table_text)
        assert result is not None
        assert len(result) == 3  # header + 2 rows
        assert result[0] == ["Header 1", "Header 2"]
        assert result[1] == ["Row 1", "Data 1"]

    def test_parse_markdown_table_none_on_invalid(self):
        """Test that invalid markdown returns None."""
        invalid_text = "This is not a table"
        result = parse_markdown_table(invalid_text)
        assert result is None

    def test_table_to_latex_basic(self):
        """Test converting table to LaTeX."""
        table = [
            ["Header 1", "Header 2"],
            ["Row 1", "Data 1"],
            ["Row 2", "Data 2"],
        ]
        result = table_to_latex(table)

        assert r"\begin{tabular}" in result
        assert r"\end{tabular}" in result
        assert r"\hline" in result
        assert "Header 1 & Header 2" in result
        assert "Row 1 & Data 1" in result

    def test_table_to_latex_escapes_special_chars(self):
        """Test that special LaTeX characters are escaped."""
        table = [["A & B", "C # D"], ["E % F", "G"]]
        result = table_to_latex(table)

        assert r"\&" in result
        assert r"\#" in result
        assert r"\%" in result

    def test_table_to_latex_preserves_math(self):
        """Test that LaTeX math mode is preserved."""
        table = [
            [r"$\frac{1}{2}$", "Normal text"],
            ["Text", r"$x^2 + y^2$"],
        ]
        result = table_to_latex(table)

        # Math content should be preserved as-is
        assert r"\frac{1}{2}" in result
        assert r"x^2 + y^2" in result

    def test_parse_html_table_basic(self):
        """Test parsing HTML table."""
        html_text = """
        <table>
            <tr><td>A</td><td>B</td></tr>
            <tr><td>C</td><td>D</td></tr>
        </table>
        """
        result = parse_html_table(html_text)

        assert len(result) == 1  # one table
        assert len(result[0]) == 2  # two rows
        assert result[0][0] == ["A", "B"]
        assert result[0][1] == ["C", "D"]

    def test_parse_html_table_with_headers(self):
        """Test parsing HTML table with th elements."""
        html_text = """
        <table>
            <tr><th>Header A</th><th>Header B</th></tr>
            <tr><td>Data 1</td><td>Data 2</td></tr>
        </table>
        """
        result = parse_html_table(html_text)

        assert len(result[0]) == 2
        assert result[0][0] == ["Header A", "Header B"]
