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
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_playwright() -> bool:
    """Download and setup Playwright chromium via CLI."""
    logger.info("Setting up Playwright chromium...")
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if browsers_path:
        logger.info("Playwright browsers path: %s", browsers_path)
    try:
        logger.info("Downloading Playwright chromium...")
        # Pass full env including PLAYWRIGHT_BROWSERS_PATH so browser lands in the volume
        result = subprocess.run(
            ["playwright", "install", "chromium", "--with-deps"],
            text=True,
            timeout=600,
            env=os.environ.copy(),
        )
        if result.returncode == 0:
            logger.info("✓ Playwright chromium setup complete")
            return True
        else:
            logger.error("✗ Playwright install failed (exit %d)", result.returncode)
            return False
    except FileNotFoundError:
        logger.error("✗ playwright CLI not found. Install with: pip install playwright")
        return False
    except Exception as e:
        logger.error(f"✗ Failed to setup Playwright: {e}")
        return False


def setup_ppstructure(lang: str = "vi", use_gpu: bool = False) -> bool:
    """Download and setup PPStructureV3 models.

    Args:
        lang: Language code (e.g., 'en', 'ch', 'ja')
        use_gpu: Whether to setup GPU variant

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Setting up PPStructureV3 models (lang={lang}, gpu={use_gpu})...")

    paddle_home = os.environ.get("PADDLE_PDX_CACHE_HOME")
    if paddle_home:
        logger.info("Paddle model cache home: %s", paddle_home)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["DISABLE_MODEL_SOURCE_CHECK"] = "True"

    try:
        from paddleocr import PPStructureV3

        device = "gpu" if use_gpu else "cpu"
        logger.info(f"Initializing PPStructureV3 (device={device}, lang={lang})...")

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

    except ImportError as e:
        logger.error(f"✗ paddleocr import failed: {e}")
        logger.error("Install with: pip install paddleocr[all]")
        return False
    except Exception as e:
        logger.error(f"✗ Failed to setup PPStructureV3 ({lang}, {device}): {e}")
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
        default=os.getenv("OCR_USE_GPU", "false").lower() == "true",
        help="Use GPU for PPStructureV3 (default: False, or from OCR_USE_GPU env)",
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
