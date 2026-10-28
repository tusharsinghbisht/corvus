"""Run with python -m corvus.server.worker. No model processing in this worker yet."""

import logging
import signal
from pathlib import Path
from threading import Event

from ..errors import BackendError
from .database import connect, initialize
from .ingestion import poll
from .settings import Settings

logger = logging.getLogger("corvus.ingestion")


def main():
    settings = Settings.load()
    initialize(settings)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        Path("/tmp/corvus-worker-heartbeat").touch()
        try:
            with connect(settings) as db:
                identifiers = [
                    row["id"]
                    for row in db.execute(
                        "SELECT id FROM connections WHERE enabled ORDER BY created_at"
                    )
                ]
            for identifier in identifiers:
                for _ in range(6):
                    if stop.is_set():
                        break
                    with connect(settings) as db:
                        connection = db.execute(
                            "SELECT * FROM connections WHERE id=%s AND enabled", (identifier,)
                        ).fetchone()
                    if not connection:
                        break
                    try:
                        count = poll(settings, connection)
                        if count:
                            logger.info("Connection %s: %d new alerts", identifier, count)
                    except Exception as exc:
                        code = exc.code if isinstance(exc, BackendError) else "ingestion_error"
                        with connect(settings) as db:
                            db.execute(
                                "UPDATE connections SET last_error=%s WHERE id=%s",
                                (code, identifier),
                            )
                        logger.warning("Connection %s: %s", identifier, code)
                        break
        except Exception:
            logger.error("Ingestion cycle failed; retrying in five seconds")
        stop.wait(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    main()
