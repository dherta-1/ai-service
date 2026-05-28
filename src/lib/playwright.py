"""Playwright browser management for PDF generation."""

import asyncio
import logging
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_KATEX_DIR = _TEMPLATES_DIR / "katex"

_CDN_ROUTE_MAP = {
    "katex.min.css": _KATEX_DIR / "katex.min.css",
    "katex.min.js": _KATEX_DIR / "katex.min.js",
    "auto-render.min.js": _KATEX_DIR / "auto-render.min.js",
}


class PlaywrightManager:
    """Manages Playwright browser lifecycle for PDF generation."""

    def __init__(self):
        self._browser: Browser | None = None

    async def initialize(self) -> None:
        """Initialize Playwright and launch browser."""
        try:
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
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

        Writes HTML to a temp file inside _TEMPLATES_DIR so relative asset
        URLs (fonts, KaTeX) resolve correctly via file:// origin.
        CDN KaTeX requests are intercepted and served from local copies.
        """
        if not self._browser:
            raise RuntimeError("Playwright browser not initialized")

        page = await self._browser.new_page()
        tmp_path = None
        try:
            async def _route_handler(route, request):
                for filename, local_path in _CDN_ROUTE_MAP.items():
                    if filename in request.url:
                        if local_path.exists():
                            content_type = (
                                "text/css"
                                if request.url.endswith(".css")
                                else "application/javascript"
                            )
                            await route.fulfill(
                                status=200,
                                content_type=content_type,
                                body=local_path.read_bytes(),
                            )
                            return
                await route.continue_()

            await page.route("**/*", _route_handler)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", encoding="utf-8",
                dir=str(_TEMPLATES_DIR), delete=False,
            ) as f:
                f.write(html)
                tmp_path = Path(f.name)

            await page.goto(tmp_path.as_uri(), wait_until="domcontentloaded")

            # Wait for KaTeX auto-render to complete (up to 8s)
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('.katex').length > 0 || "
                    "!document.querySelector('script[src*=\"auto-render\"]')",
                    timeout=8000,
                )
            except Exception:
                logger.warning("KaTeX wait timed out, proceeding without math render")

            try:
                await page.evaluate("() => document.fonts.ready")
            except Exception:
                pass

            await asyncio.sleep(0.2)

            if margin is None:
                margin = {
                    "top": "2.2cm",
                    "bottom": "2.2cm",
                    "left": "2.5cm",
                    "right": "2.5cm",
                }

            return await page.pdf(
                format=format,
                margin=margin,
                print_background=print_background,
            )
        finally:
            await page.close()
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
