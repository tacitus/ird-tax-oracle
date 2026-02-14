"""Apply database migrations using yoyo-migrations."""

import logging
import sys
from pathlib import Path

from yoyo import get_backend, read_migrations

# Add project root to path so config is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Apply all pending migrations."""
    db_url = settings.database_url_sync
    migrations_dir = str(Path(__file__).resolve().parent.parent / "migrations")

    logger.info("Connecting to database...")
    backend = get_backend(db_url)
    migrations = read_migrations(migrations_dir)

    with backend.lock():
        to_apply = backend.to_apply(migrations)
        if not to_apply:
            logger.info("No pending migrations.")
            return

        logger.info("Applying %d migration(s)...", len(to_apply))
        backend.apply_migrations(to_apply)
        logger.info("Migrations applied successfully.")


if __name__ == "__main__":
    main()
