"""Run as python -m lms_svc.worker; jobs survive worker/API restarts."""
import logging
import signal
from threading import Event

from . import create_app


def run_due(service, logger):
    for college_id in service.connections.due(service.clock()):
        try:
            service.synchronize(college_id)
        except Exception as error:
            logger.warning("LMS synchronization did not complete (%s).", type(error).__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("lms_worker")
    stopping = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    service = create_app().extensions["lms_sync"]
    while not stopping.is_set():
        try:
            run_due(service, logger)
        except Exception as error:
            logger.error("LMS scheduler temporarily unavailable (%s).", type(error).__name__)
        stopping.wait(30)


if __name__ == "__main__":
    main()
