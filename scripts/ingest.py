"""CLI script for running the ingestion pipeline.

Usage:
    # Process all sources from config/sources.yaml
    python scripts/ingest.py

    # Process a single URL
    python scripts/ingest.py --url "https://www.ird.govt.nz/..."

    # Force re-processing (ignore content hash)
    python scripts/ingest.py --force

    # Dry run (crawl, parse, chunk but don't embed or store)
    python scripts/ingest.py --dry-run

    # Verbose logging
    python scripts/ingest.py -v
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_yaml_config
from src.db.session import close_pool
from src.ingestion.crawler import Crawler
from src.ingestion.pipeline import IngestionPipeline
from src.rag.embedder import GeminiEmbedder

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NZ Tax RAG ingestion pipeline")
    parser.add_argument("--url", help="Process a single URL instead of all sources")
    parser.add_argument(
        "--source-type",
        default="ird_guidance",
        help="Source type for --url mode (default: ird_guidance)",
    )
    parser.add_argument("--force", action="store_true", help="Re-process even if unchanged")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl and parse but don't embed or store",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    embedder = GeminiEmbedder()
    crawler = Crawler()
    pipeline = IngestionPipeline(embedder=embedder, crawler=crawler)

    results: list[dict] = []

    try:
        if args.url:
            # Single URL mode
            result = await pipeline.process_url(
                url=args.url,
                source_type=args.source_type,
                force=args.force,
                dry_run=args.dry_run,
            )
            results.append(result)
        else:
            # Process all sources from config
            config = load_yaml_config("sources.yaml")
            sources = config.get("sources", [])
            logger.info("Processing %d sources from config/sources.yaml", len(sources))

            for source in sources:
                try:
                    result = await pipeline.process_url(
                        url=source["url"],
                        source_type=source.get("source_type", "ird_guidance"),
                        title=source.get("title"),
                        force=args.force,
                        dry_run=args.dry_run,
                    )
                    results.append(result)
                except Exception:
                    logger.exception("Failed to process %s", source["url"])
                    results.append({"url": source["url"], "error": True})

        # Summary
        total = len(results)
        skipped = sum(1 for r in results if r.get("skipped"))
        errors = sum(1 for r in results if r.get("error"))
        processed = total - skipped - errors
        total_chunks = sum(r.get("chunks", 0) for r in results if isinstance(r.get("chunks"), int))

        logger.info("=" * 60)
        logger.info(
            "Done: %d processed, %d skipped, %d errors, %d total chunks",
            processed,
            skipped,
            errors,
            total_chunks,
        )
    finally:
        await close_pool()


def main() -> None:
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
