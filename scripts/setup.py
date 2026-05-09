#!/usr/bin/env python3
"""Setup script for downloading required dependencies and models.

This script downloads:
1. Playwright chromium browser
2. PPStructureV3 models (with support for multiple languages and GPU)
"""

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_playwright() -> bool:
    """Download and setup Playwright chromium."""
    logger.info("Setting up Playwright chromium...")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            logger.info("Downloading Playwright chromium...")
            browser = p.chromium.launch()
            browser.close()
            logger.info("✓ Playwright chromium setup complete")
            return True
    except Exception as e:
        logger.error(f"✗ Failed to setup Playwright: {e}")
        return False


def setup_ppstructure(lang: str = "en", use_gpu: bool = False) -> bool:
    """Download and setup PPStructureV3 models.

    Args:
        lang: Language code (e.g., 'en', 'ch', 'ja')
        use_gpu: Whether to setup GPU variant

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Setting up PPStructureV3 models (lang={lang}, gpu={use_gpu})...")

    # Disable model source checks to avoid network issues
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    try:
        from paddleocr import PPStructureV3

        device = "gpu" if use_gpu else "cpu"
        logger.info(f"Initializing PPStructureV3 (device={device}, lang={lang})...")

        # Initialize the engine which triggers model downloads
        PPStructureV3(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
            lang=lang,
            enable_mkldnn=False,
        )

        logger.info(f"✓ PPStructureV3 models setup complete ({lang}, {device})")
        return True

    except ImportError:
        logger.error(
            "✗ paddleocr not installed. Install with: pip install paddleocr[all]"
        )
        return False
    except Exception as e:
        logger.error(f"✗ Failed to setup PPStructureV3: {e}")
        return False


def setup_dependencies(args: argparse.Namespace) -> int:
    """Run all dependency setups.

    Args:
        args: Parsed command line arguments

    Returns:
        0 if all succeeded, 1 if any failed
    """
    results = {
        "playwright": False,
        "ppstructure": False,
    }

    # Setup Playwright
    if args.playwright:
        results["playwright"] = setup_playwright()

    # Setup PPStructureV3
    if args.ppstructure:
        for lang in args.languages:
            if not setup_ppstructure(lang=lang, use_gpu=args.gpu):
                results["ppstructure"] = False
                break
        else:
            results["ppstructure"] = True

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Setup Summary:")
    logger.info("=" * 60)
    for component, success in results.items():
        status = "✓" if success else "✗"
        logger.info(f"{status} {component.capitalize()}")

    all_success = all(results.values())
    if all_success:
        logger.info("=" * 60)
        logger.info("All dependencies setup successfully!")
        return 0
    else:
        logger.error("=" * 60)
        logger.error("Some dependencies failed to setup. See errors above.")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Setup script for downloading required dependencies and models"
    )

    parser.add_argument(
        "--playwright",
        action="store_true",
        default=True,
        help="Setup Playwright chromium (default: True)",
    )

    parser.add_argument(
        "--ppstructure",
        action="store_true",
        default=True,
        help="Setup PPStructureV3 models (default: True)",
    )

    parser.add_argument(
        "--languages",
        nargs="+",
        default=["en", "vi"],
        help="Languages for PPStructureV3 (default: en). Examples: en, ch, ja",
    )

    parser.add_argument(
        "--gpu",
        action="store_true",
        default=False,
        help="Use GPU for PPStructureV3 (default: False)",
    )

    parser.add_argument(
        "--skip-playwright",
        dest="playwright",
        action="store_false",
        help="Skip Playwright setup",
    )

    parser.add_argument(
        "--skip-ppstructure",
        dest="ppstructure",
        action="store_false",
        help="Skip PPStructureV3 setup",
    )

    args = parser.parse_args()

    return setup_dependencies(args)


if __name__ == "__main__":
    sys.exit(main())
