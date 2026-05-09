"""Playwright browser management for PDF generation."""

import asyncio
import logging
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)


class PlaywrightManager:
    """Manages Playwright browser lifecycle for PDF generation."""

    def __init__(self):
        self._browser: Browser | None = None

    async def initialize(self) -> None:
        """Initialize Playwright and launch browser."""
        try:
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(headless=True)
            logger.info("Playwright browser initialized")
        except Exception as exc:
            logger.error("Failed to initialize Playwright: %s", exc)
            raise

    async def shutdown(self) -> None:
        """Close Playwright browser."""
        if self._browser:
            try:
                await self._browser.close()
                self._browser = None
                logger.info("Playwright browser closed")
            except Exception as exc:
                logger.error("Error closing Playwright browser: %s", exc)

    async def render_html_to_pdf(
        self,
        html: str,
        format: str = "A4",
        margin: dict | None = None,
        print_background: bool = True,
    ) -> bytes:
        """Render HTML to PDF using Playwright.

        Args:
            html: HTML content to render
            format: Paper format (e.g., "A4")
            margin: Page margins dict with top/bottom/left/right keys
            print_background: Whether to print background colors/images

        Returns:
            PDF bytes
        """
        if not self._browser:
            raise RuntimeError("Playwright browser not initialized")

        page = await self._browser.new_page()
        try:
            await page.set_content(html, wait_until="networkidle")

            # Wait for KaTeX auto-render to finish
            await page.wait_for_function(
                "() => document.querySelectorAll('.katex').length > 0 || "
                "!document.querySelector('script[src*=\"auto-render\"]')"
            )
            await asyncio.sleep(0.3)

            if margin is None:
                margin = {
                    "top": "2.2cm",
                    "bottom": "2.2cm",
                    "left": "2.5cm",
                    "right": "2.5cm",
                }

            pdf_bytes = await page.pdf(
                format=format,
                margin=margin,
                print_background=print_background,
            )
            return pdf_bytes
        finally:
            await page.close()
