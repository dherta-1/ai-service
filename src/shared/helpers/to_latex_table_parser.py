"""LaTeX table and markdown conversion utilities.

Converts HTML tables, markdown tables, and other formats to LaTeX tabular format.
"""

from __future__ import annotations

import re
from typing import List, Optional
from html.parser import HTMLParser


class TableHTMLParser(HTMLParser):
    """Parse HTML tables into structured data."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.current_table: Optional[list[list[str]]] = None
        self.current_row: Optional[list[str]] = None
        self.current_cell: str = ""
        self.in_table = False
        self.in_row = False
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self.in_table = True
            self.current_table = []
        elif tag in ("tr", "thead", "tbody", "tfoot"):
            if tag == "tr" and self.in_table:
                self.in_row = True
                self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.in_table:
            self.in_table = False
            if self.current_table is not None:
                self.tables.append(self.current_table)
            self.current_table = None
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row is not None and self.current_table is not None:
                self.current_table.append(self.current_row)
            self.current_row = None
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            if self.current_row is not None:
                self.current_row.append(self.current_cell.strip())
            self.current_cell = ""

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell += data


def parse_markdown_table(text: str) -> Optional[list[list[str]]]:
    """Parse a markdown table into structured data.

    Markdown table format:
    | Header 1 | Header 2 |
    |----------|----------|
    | Row 1    | Data 1   |
    | Row 2    | Data 2   |

    Returns list of rows (each row is a list of cells), or None if not a valid table.
    """
    lines = text.strip().split("\n")
    if len(lines) < 3:
        return None

    # Check if first line looks like a markdown table header
    first_line = lines[0].strip()
    if not (first_line.startswith("|") and first_line.endswith("|")):
        return None

    # Parse header row
    header_cells = [cell.strip() for cell in first_line.split("|")[1:-1]]

    # Check separator line (should be all dashes and pipes)
    sep_line = lines[1].strip()
    if not re.match(r"^\|[\s\-|:]+\|$", sep_line):
        return None

    table_data = [header_cells]

    # Parse body rows
    for line in lines[2:]:
        line = line.strip()
        if not line or not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        table_data.append(cells)

    return table_data if len(table_data) > 1 else None


def parse_html_table(html_text: str) -> list[list[list[str]]]:
    """Parse HTML tables from text.

    Returns list of tables (each table is list of rows, each row is list of cells).
    """
    parser = TableHTMLParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass
    return parser.tables


def table_to_latex(table: list[list[str]]) -> str:
    """Convert a table (list of rows) to LaTeX tabular format.

    Args:
        table: List of rows, where each row is a list of cells (strings)

    Returns:
        LaTeX tabular environment code
    """
    if not table or not table[0]:
        return ""

    num_cols = len(table[0])
    col_spec = "c" * num_cols  # Center alignment for all columns

    # Escape LaTeX special characters in cells
    def escape_cell(cell: str) -> str:
        # Don't escape LaTeX math mode content
        if "$" in cell or "\\" in cell:
            return cell
        # Escape special LaTeX characters
        cell = cell.replace("&", r"\&")
        cell = cell.replace("#", r"\#")
        cell = cell.replace("%", r"\%")
        cell = cell.replace("_", r"\_")
        cell = cell.replace("{", r"\{")
        cell = cell.replace("}", r"\}")
        cell = cell.replace("~", r"\textasciitilde{}")
        cell = cell.replace("^", r"\^{}")
        return cell

    # Build LaTeX table
    latex_lines = [
        r"\begin{tabular}{" + col_spec + "}",
        r"\hline",
    ]

    for row_idx, row in enumerate(table):
        # Pad row with empty cells if needed
        padded_row = row + [""] * (num_cols - len(row))
        escaped_row = [escape_cell(cell) for cell in padded_row[:num_cols]]
        latex_lines.append(" & ".join(escaped_row) + r" \\")

        # Add horizontal line after header (first row)
        if row_idx == 0:
            latex_lines.append(r"\hline")

    latex_lines.append(r"\hline")
    latex_lines.append(r"\end{tabular}")

    return "\n".join(latex_lines)


def convert_tables_in_text(text: str) -> str:
    """Find and convert tables (HTML or markdown) in text to LaTeX format.

    Args:
        text: Text that may contain HTML or markdown tables

    Returns:
        Text with tables converted to LaTeX tabular format
    """
    result = text

    # Try to find and convert HTML tables
    html_tables = parse_html_table(text)
    if html_tables:
        for table in html_tables:
            latex_table = table_to_latex(table)
            # Find the HTML table in the original text and replace it
            # This is a simplification; in production, you might want more precise matching
            result = result.replace(text, result)  # Placeholder for actual replacement

    # Try to find and convert markdown tables
    lines = result.split("\n")
    i = 0
    new_lines = []
    while i < len(lines):
        # Try to parse table starting at this line
        remaining_text = "\n".join(lines[i:])
        markdown_table = parse_markdown_table(remaining_text)

        if markdown_table:
            latex_table = table_to_latex(markdown_table)
            new_lines.append(latex_table)
            # Skip the lines that made up the table
            i += len(markdown_table) + 2  # +2 for header and separator
        else:
            new_lines.append(lines[i])
            i += 1

    return "\n".join(new_lines)
