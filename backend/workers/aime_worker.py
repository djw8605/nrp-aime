"""AIME background worker.

Polls the AMIE endpoint for new allocation packets and delegates
processing to the :class:`~app.services.aime.service.AIMEService`.

This worker can be run as a standalone process::

    python -m workers.aime_worker

or integrated into a task queue such as Celery.
"""

import logging
import time

from app.config import settings
from app.database import SessionLocal
from app.services.aime.service import AIMEService

logger = logging.getLogger(__name__)


def process_packets(aime_svc: AIMEService, packets: list[dict]) -> None:
    """Persist a list of allocation packets to the database."""
    with SessionLocal() as db:
        for packet in packets:
            try:
                project = aime_svc.ingest_packet(db, packet)
                logger.info("Ingested allocation for project: %s", project.name)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to ingest packet %s", packet)


def run_worker(poll_interval: int = 60) -> None:
    """Poll AMIE for new packets indefinitely.

    Args:
        poll_interval: Seconds to wait between polling cycles.
    """
    aime_svc = AIMEService(site_name=settings.amie_site_name)
    logger.info("AIME worker started (site=%s)", settings.amie_site_name)

    while True:
        try:
            # TODO: replace with actual amieclient call once API key is configured
            # Example:
            #   import amieclient
            #   client = amieclient.AMIEClient(
            #       site_name=settings.amie_site_name,
            #       api_key=settings.amie_api_key,
            #   )
            #   packets = client.get_packets()
            packets: list[dict] = []  # placeholder
            if packets:
                process_packets(aime_svc, packets)
        except Exception:  # noqa: BLE001
            logger.exception("AIME worker error")

        time.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
