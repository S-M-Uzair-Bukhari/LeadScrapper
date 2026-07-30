"""Idempotent cleanup for undetected-chromedriver on Windows."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def close_chrome_safely(driver: object | None) -> None:
    """Quit Chrome once, then make uc.Chrome.__del__ harmless.

    undetected-chromedriver 3.5.5 calls quit() unconditionally from __del__.
    On Windows/Python 3.14 that second call can raise WinError 6 while the
    interpreter is shutting down.
    """
    if driver is None:
        return

    try:
        driver.quit()
    except Exception as exc:
        logger.debug("Chrome quit raised during cleanup: %s", exc)
        try:
            driver.close()
        except Exception:
            pass
    finally:
        # The library destructor first tries service.process.kill(), then calls
        # self.quit() again. Neutralize both operations on this closed instance.
        try:
            driver.service.process = None
        except Exception:
            pass
        try:
            driver.reactor = None
        except Exception:
            pass
        try:
            driver.keep_user_data_dir = True
        except Exception:
            pass
        try:
            driver.quit = lambda: None
        except Exception:
            pass
