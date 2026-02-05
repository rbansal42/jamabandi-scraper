#!/usr/bin/env python3
"""
Jamabandi Land Records Scraper - HTTP Version
==============================================
Uses pure HTTP requests (no browser) for faster scraping.

Requires manual authentication first to get session cookie.

Usage:
    1. Open browser, login to jamabandi.nic.in/PublicNakal
    2. Get your session cookie (jamabandiID) from browser dev tools
    3. Run: python main_http.py --cookie "your_cookie_value"
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

# Ensure sibling modules are importable when run as a standalone script
sys.path.insert(0, str(Path(__file__).parent))

import requests
from bs4 import BeautifulSoup

from .config import get_config
from .logger import (
    get_logger,
    setup_logging,
    log_http_request,
    log_download,
    log_session_event,
)
from .rate_limiter import RateLimiter
from .retry_manager import RetryManager
from .validator import PDFValidator, ValidationStatus

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "district_code": "17",
    "tehsil_code": "102",
    "village_code": "02532",
    "period": "2023-2024",
    "khewat_start": 1,
    "khewat_end": 1099,
    "min_delay": 1.0,
    "max_delay": 2.5,
    "max_retries": 3,
    "page_load_timeout": 30,
    "form_postback_sleep": 0.25,
    "downloads_dir": "/Volumes/Code/script/downloads_02532",
    "progress_file": "/Volumes/Code/script/downloads_02532/progress_02532.json",
}


def _get_urls() -> tuple:
    """Get URLs from config."""
    config = get_config()
    base = config.urls.get("base_url", "https://jamabandi.nic.in")
    form_path = config.urls.get("form_path", "/PublicNakal/CreateNewRequest")
    return base, f"{base}{form_path}"


def _build_headers() -> dict:
    """Build HTTP headers from config."""
    config = get_config()
    return {
        "User-Agent": config.http.get("user_agent", "Mozilla/5.0"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }


# Module-level cached values (computed on first access)
_BASE_URL = None
_FORM_URL = None
_HEADERS = None


def _get_base_url() -> str:
    """Get cached base URL."""
    global _BASE_URL
    if _BASE_URL is None:
        _BASE_URL, _ = _get_urls()
    return _BASE_URL


def _get_form_url() -> str:
    """Get cached form URL."""
    global _FORM_URL
    if _FORM_URL is None:
        _, _FORM_URL = _get_urls()
    return _FORM_URL


def _get_headers() -> dict:
    """Get cached headers."""
    global _HEADERS
    if _HEADERS is None:
        _HEADERS = _build_headers()
    return _HEADERS


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


class ProgressTracker:
    """Thread-safe tracker for downloaded khewat numbers with resume capability.

    Features:
    - Atomic saves using temp file + rename to prevent corruption
    - Configurable save interval to reduce I/O overhead
    - Metadata tracking (start_time, stats)
    - Thread-safe operations with locking
    """

    def __init__(self, filepath: str, save_interval: int = 5):
        """Initialize the progress tracker.

        Args:
            filepath: Path to the progress JSON file
            save_interval: Number of downloads between automatic saves (default 5)
        """
        self.filepath = Path(filepath)
        self.save_interval = save_interval
        self._unsaved_count = 0
        self._lock = threading.Lock()

        # Resolve relative paths against the script's directory so that
        # "progress.json" doesn't land in an arbitrary CWD.
        if not self.filepath.is_absolute():
            self.filepath = Path(__file__).parent / self.filepath

        self.data = {
            "config": {},
            "completed": [],
            "failed": {},
            "last_updated": None,
            "stats": {
                "start_time": None,
                "total_time": 0,
                "download_count": 0,
                "bytes_downloaded": 0,
            },
        }
        self.load()

    def load(self):
        """Load progress from file if it exists."""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                # Merge with defaults to handle missing keys from older versions
                for key in self.data:
                    if key in loaded_data:
                        self.data[key] = loaded_data[key]
                # Ensure stats dict has all required keys
                if "stats" not in self.data or not isinstance(self.data["stats"], dict):
                    self.data["stats"] = {
                        "start_time": None,
                        "total_time": 0,
                        "download_count": 0,
                        "bytes_downloaded": 0,
                    }
                else:
                    # Fill in missing stats keys
                    defaults = {
                        "start_time": None,
                        "total_time": 0,
                        "download_count": 0,
                        "bytes_downloaded": 0,
                    }
                    for k, v in defaults.items():
                        if k not in self.data["stats"]:
                            self.data["stats"][k] = v
                print(
                    f"Loaded progress: {len(self.data['completed'])} completed, "
                    f"{len(self.data['failed'])} failed"
                )
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load progress file: {e}")

    def _atomic_save(self) -> None:
        """Save atomically: write temp file, then rename.

        This prevents data corruption if the process is interrupted during save.
        """
        self.data["last_updated"] = datetime.now().isoformat()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self.filepath.with_suffix(".json.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        temp_path.replace(self.filepath)  # Atomic rename on POSIX systems

    def flush(self) -> None:
        """Force save pending changes."""
        with self._lock:
            if self._unsaved_count > 0:
                self._atomic_save()
                self._unsaved_count = 0

    def set_config(self, config: dict):
        """Set the scraping configuration and initialize stats."""
        with self._lock:
            self.data["config"] = {
                "district": config["district_code"],
                "tehsil": config["tehsil_code"],
                "village": config["village_code"],
                "period": config["period"],
            }
            # Record start time if not already set
            if self.data["stats"]["start_time"] is None:
                self.data["stats"]["start_time"] = datetime.now().isoformat()
            self._atomic_save()
            self._unsaved_count = 0

    def mark_complete(self, khewat: int, bytes_downloaded: int = 0):
        """Mark a khewat as successfully downloaded.

        Args:
            khewat: The khewat number that was downloaded
            bytes_downloaded: Number of bytes in the downloaded file
        """
        with self._lock:
            if khewat not in self.data["completed"]:
                self.data["completed"].append(khewat)
                self.data["completed"].sort()
                self.data["stats"]["download_count"] += 1
                self.data["stats"]["bytes_downloaded"] += bytes_downloaded
            self.data["failed"].pop(str(khewat), None)
            self._unsaved_count += 1
            if self._unsaved_count >= self.save_interval:
                self._atomic_save()
                self._unsaved_count = 0

    def mark_failed(self, khewat: int, error: str):
        """Mark a khewat as failed with an error message.

        Args:
            khewat: The khewat number that failed
            error: Description of the error
        """
        with self._lock:
            self.data["failed"][str(khewat)] = error
            self._unsaved_count += 1
            if self._unsaved_count >= self.save_interval:
                self._atomic_save()
                self._unsaved_count = 0

    def get_pending(self, start: int, end: int) -> list:
        """Get list of khewat numbers that haven't been downloaded yet."""
        with self._lock:
            completed_set = set(self.data["completed"])
            return [k for k in range(start, end + 1) if k not in completed_set]

    def get_summary(self) -> str:
        """Get a human-readable summary of progress."""
        with self._lock:
            total = CONFIG["khewat_end"] - CONFIG["khewat_start"] + 1
            return (
                f"Completed: {len(self.data['completed'])}, "
                f"Failed: {len(self.data['failed'])}, "
                f"Pending: {total - len(self.data['completed'])}"
            )

    def get_stats(self) -> dict:
        """Get download statistics."""
        with self._lock:
            return self.data["stats"].copy()


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP SCRAPER
# ═══════════════════════════════════════════════════════════════════════════════


class JamabandiHTTPScraper:
    """
    HTTP-based scraper for Jamabandi land records.
    Uses requests library with session cookies from manual authentication.
    """

    def __init__(self, session_cookie: str, config: dict, progress: ProgressTracker):
        # Initialize logging
        setup_logging()
        self.logger = get_logger()
        log_session_event("Scraper initialized")

        self.config = config
        self.progress = progress
        self.downloads_dir = Path(config["downloads_dir"])
        self.downloads_dir.mkdir(exist_ok=True)

        # Get config-based values
        self._app_config = get_config()
        headers = _get_headers()

        # Send cookie as a raw header instead of using the cookie jar.
        # On Windows, system proxies / cookie-jar domain matching can
        # silently strip cookies. A raw header is always forwarded.
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.session.headers["Cookie"] = f"jamabandiID={session_cookie}"

        # Disable SSL verification (site has certificate issues).
        # trust_env=False stops requests from picking up Windows system
        # proxy settings that can intercept/modify HTTPS traffic.
        self.session.verify = self._app_config.http.get("verify_ssl", False)
        self.session.trust_env = False
        # Suppress SSL warnings
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # ASP.NET form state
        self.viewstate = None
        self.viewstate_generator = None
        self.event_validation = None
        self.form_initialized = False

        # Adaptive rate limiter
        self.rate_limiter = RateLimiter()

        # Content validator
        self.validator = PDFValidator()

    def _parse_asp_tokens(self, html: str) -> bool:
        """Extract ASP.NET hidden form tokens from HTML."""
        soup = BeautifulSoup(html, "html.parser")

        vs = soup.find("input", {"name": "__VIEWSTATE"})
        vsg = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})
        ev = soup.find("input", {"name": "__EVENTVALIDATION"})

        if vs and vsg:
            self.viewstate = vs.get("value", "")
            self.viewstate_generator = vsg.get("value", "")
            self.event_validation = ev.get("value", "") if ev else ""
            return True
        return False

    def _check_logged_in(self, html: str) -> bool:
        """Check if the response indicates we're still logged in."""
        if "login.aspx" in html.lower() or "enter mobile" in html.lower():
            return False
        if "ddldname" in html:  # Form dropdown present = logged in
            return True
        return False

    def _make_postback(
        self, event_target: str, extra_data: dict = None
    ) -> requests.Response:
        """Make an ASP.NET postback request."""
        form_url = _get_form_url()
        headers = _get_headers()
        timeout = self._app_config.http.get("timeout", 30)

        data = {
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": self.viewstate,
            "__VIEWSTATEGENERATOR": self.viewstate_generator,
            "__VIEWSTATEENCRYPTED": "",
        }
        if self.event_validation:
            data["__EVENTVALIDATION"] = self.event_validation

        if extra_data:
            data.update(extra_data)

        self.rate_limiter.wait()
        response = self.session.post(
            form_url,
            data=data,
            headers={**headers, "Referer": form_url},
            allow_redirects=True,
            timeout=timeout,
        )
        elapsed_ms = response.elapsed.total_seconds() * 1000
        self.rate_limiter.record_response(response.status_code, elapsed_ms)
        log_http_request("POST", form_url, response.status_code, elapsed_ms)

        return response

    def initialize_form(self) -> bool:
        """Load the form page and extract initial tokens."""
        form_url = _get_form_url()
        headers = _get_headers()
        timeout = self._app_config.http.get("timeout", 30)

        self.logger.info("Loading form page...")

        self.rate_limiter.wait()
        response = self.session.get(form_url, headers=headers, timeout=timeout)
        elapsed_ms = response.elapsed.total_seconds() * 1000
        self.rate_limiter.record_response(response.status_code, elapsed_ms)
        log_http_request("GET", form_url, response.status_code, elapsed_ms)

        if response.status_code != 200:
            self.logger.error(f"Failed to load form: HTTP {response.status_code}")
            return False

        if not self._check_logged_in(response.text):
            # Show diagnostic info to help debug cookie / redirect issues
            self.logger.error("Session invalid - not logged in!")
            self.logger.debug(f"Final URL: {response.url}")
            if response.history:
                self.logger.debug(
                    f"Redirects: {' -> '.join(r.url for r in response.history)}"
                )
            snippet = response.text[:500].replace("\n", " ").strip()
            self.logger.debug(f"Response snippet: {snippet[:200]}...")
            return False

        if not self._parse_asp_tokens(response.text):
            self.logger.error("Failed to parse ASP.NET tokens")
            return False

        self.logger.info("Form loaded successfully")
        log_session_event("Form initialized")
        return True

    def setup_form_selections(self) -> bool:
        """Set up all form selections (district, tehsil, village, period)."""
        self.logger.info("Setting up form selections...")
        # Use config-based delay, fall back to local config, then default
        postback_sleep = self._app_config.delays.get(
            "form_postback_sleep", self.config.get("form_postback_sleep", 0.25)
        )

        # Step 1: Select "By Khewat" radio
        self.logger.debug("Selecting: By Khewat")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": "-1",
            "ddltname": "",
            "ddlvname": "",
            "ddlPeriod": "",
        }
        response = self._make_postback("RdobtnKhewat", form_data)
        if not self._parse_asp_tokens(response.text):
            self.logger.error("Failed after radio selection")
            return False
        time.sleep(postback_sleep)

        # Step 2: Select District
        self.logger.debug(f"Selecting district: {self.config['district_code']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": "",
            "ddlvname": "",
            "ddlPeriod": "",
        }
        response = self._make_postback("ddldname", form_data)
        if not self._parse_asp_tokens(response.text):
            self.logger.error("Failed after district selection")
            return False
        time.sleep(postback_sleep)

        # Step 3: Select Tehsil
        self.logger.debug(f"Selecting tehsil: {self.config['tehsil_code']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": "",
            "ddlPeriod": "",
        }
        response = self._make_postback("ddltname", form_data)
        if not self._parse_asp_tokens(response.text):
            self.logger.error("Failed after tehsil selection")
            return False
        time.sleep(postback_sleep)

        # Step 4: Select Village
        self.logger.debug(f"Selecting village: {self.config['village_code']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": self.config["village_code"],
            "ddlPeriod": "",
        }
        response = self._make_postback("ddlvname", form_data)
        if not self._parse_asp_tokens(response.text):
            self.logger.error("Failed after village selection")
            return False
        time.sleep(postback_sleep)

        # Step 5: Select Period
        self.logger.debug(f"Selecting period: {self.config['period']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": self.config["village_code"],
            "ddlPeriod": self.config["period"],
        }
        response = self._make_postback("ddlPeriod", form_data)
        if not self._parse_asp_tokens(response.text):
            self.logger.error("Failed after period selection")
            return False

        # Check if khewat dropdown is now available
        if "ddlkhewat" in response.text.lower():
            self.logger.info("Form setup complete!")
            log_session_event("Form selections complete")
            self.form_initialized = True
            return True
        else:
            self.logger.warning("Khewat dropdown not found after setup")
            # Save response for debugging
            debug_path = self.downloads_dir / "debug_form.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            self.logger.debug(f"Saved response to {debug_path}")
            return False

    def download_nakal(self, khewat: int) -> bool:
        """Download Nakal for a specific khewat number."""
        self.logger.info(f"Processing khewat {khewat}...")

        form_url = _get_form_url()
        headers = _get_headers()
        timeout = self._app_config.http.get("timeout", 30)

        # Build form data for Nakal submission
        form_data = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": self.viewstate,
            "__VIEWSTATEGENERATOR": self.viewstate_generator,
            "__VIEWSTATEENCRYPTED": "",
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": self.config["village_code"],
            "ddlPeriod": self.config["period"],
            "ddlkhewat": str(khewat),
            "Cmdnakal": "Nakal",  # Submit button
        }
        if self.event_validation:
            form_data["__EVENTVALIDATION"] = self.event_validation

        try:
            self.rate_limiter.wait()
            response = self.session.post(
                form_url,
                data=form_data,
                headers={**headers, "Referer": form_url},
                allow_redirects=True,
                timeout=timeout,
            )
            elapsed_ms = response.elapsed.total_seconds() * 1000
            self.rate_limiter.record_response(response.status_code, elapsed_ms)
            log_http_request("POST", form_url, response.status_code, elapsed_ms)

            # Check response
            if response.status_code != 200:
                self.logger.error(
                    f"HTTP Error: {response.status_code} for khewat {khewat}"
                )
                self.progress.mark_failed(khewat, f"HTTP {response.status_code}")
                log_download(khewat, False, f"HTTP {response.status_code}")
                return True  # Continue to next

            # Check if session expired
            if (
                "login.aspx" in response.url.lower()
                or "login.aspx" in response.text.lower()
            ):
                self.logger.error("Session expired!")
                log_session_event("Session expired")
                return False  # Need re-auth

            # Check for "no record" message
            if (
                "no record" in response.text.lower()
                or "record not found" in response.text.lower()
            ):
                self.logger.warning(f"No record found for khewat {khewat}")
                self.progress.mark_failed(khewat, "No record found")
                log_download(khewat, False, "No record found")
                self._parse_asp_tokens(response.text)  # Update tokens
                return True

            # Check for error page
            if (
                "error page" in response.text.lower()
                or "some error has occured" in response.text.lower()
            ):
                self.logger.warning(
                    f"Error page returned for khewat {khewat} - will retry after form refresh"
                )
                self.progress.mark_failed(khewat, "Error page - needs retry")
                log_download(khewat, False, "Error page - needs retry")
                # Need to re-setup the form
                self.form_initialized = False
                return True

            # Check content type - might be PDF directly or HTML
            content_type = response.headers.get("Content-Type", "")

            if "pdf" in content_type.lower():
                # Direct PDF response
                filename = f"nakal_khewat_{khewat:04d}.pdf"
                filepath = self.downloads_dir / filename
                with open(filepath, "wb") as f:
                    f.write(response.content)
                self.logger.info(f"Saved: {filename} ({len(response.content)} bytes)")
                self.progress.mark_complete(khewat)
                log_download(
                    khewat, True, f"{filename} ({len(response.content)} bytes)"
                )
            else:
                # HTML response - check if it's actual Nakal content (should be large)
                if len(response.text) > 10000 and "nakal" in response.text.lower():
                    # Save as HTML
                    filename = f"nakal_khewat_{khewat:04d}.html"
                    filepath = self.downloads_dir / filename
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(response.text)
                    self.logger.info(f"Saved: {filename} ({len(response.text)} bytes)")
                    self.progress.mark_complete(khewat)
                    log_download(
                        khewat, True, f"{filename} ({len(response.text)} bytes)"
                    )
                else:
                    # Probably an error or empty response
                    self.logger.warning(
                        f"Unexpected small response ({len(response.text)} bytes) for khewat {khewat}"
                    )
                    self.progress.mark_failed(
                        khewat, f"Small response: {len(response.text)} bytes"
                    )
                    log_download(
                        khewat, False, f"Small response: {len(response.text)} bytes"
                    )

            # After viewing Nakal, we're on a different page - need to re-setup form
            self.form_initialized = False
            return True

        except requests.Timeout:
            self.logger.error(f"Timeout for khewat {khewat}")
            self.progress.mark_failed(khewat, "Timeout")
            log_download(khewat, False, "Timeout")
            return True
        except Exception as e:
            self.logger.exception(f"Error downloading khewat {khewat}: {e}")
            self.progress.mark_failed(khewat, str(e))
            log_download(khewat, False, str(e))
            return True

    def run(self):
        """Main scraping loop."""
        log_session_event("Scraping started")
        self.progress.set_config(self.config)

        # Initialize form
        if not self.initialize_form():
            self.logger.error("Failed to initialize. Please check your session cookie.")
            return

        # Setup form selections
        if not self.setup_form_selections():
            self.logger.error("Failed to setup form. Session may have expired.")
            return

        # Get pending khewat numbers
        pending = self.progress.get_pending(
            self.config["khewat_start"], self.config["khewat_end"]
        )

        self.logger.info(f"Processing {len(pending)} khewat numbers...")
        self.logger.info(f"Progress: {self.progress.get_summary()}")

        # Get delays from config
        min_delay = self._app_config.delays.get(
            "min_delay", self.config.get("min_delay", 1.0)
        )
        max_delay = self._app_config.delays.get(
            "max_delay", self.config.get("max_delay", 2.5)
        )

        for i, khewat in enumerate(pending):
            # Check if we need to re-setup the form (after errors)
            if not self.form_initialized:
                self.logger.info("Re-initializing form...")
                if not self.initialize_form():
                    self.logger.error(
                        "Session expired during re-init. Please get new cookie."
                    )
                    break
                if not self.setup_form_selections():
                    self.logger.error(
                        "Failed to re-setup form. Session may have expired."
                    )
                    break

            success = self.download_nakal(khewat)

            if not success:
                self.logger.error(
                    "Session expired. Please get a new cookie and restart."
                )
                break

            # Rate limiting
            if i < len(pending) - 1:  # Don't wait after last one
                delay = random.uniform(min_delay, max_delay)
                self.logger.debug(f"Waiting {delay:.1f}s...")
                time.sleep(delay)

        # Summary
        log_session_event("Scraping complete", self.progress.get_summary())
        self.logger.info("=" * 60)
        self.logger.info("SCRAPING COMPLETE")
        self.logger.info("=" * 60)
        self.logger.info(f"Final status: {self.progress.get_summary()}")

        if self.progress.data["failed"]:
            self.logger.warning("Failed khewat numbers:")
            for k, error in list(self.progress.data["failed"].items())[:10]:
                self.logger.warning(f"  - Khewat {k}: {error}")
            if len(self.progress.data["failed"]) > 10:
                self.logger.warning(
                    f"  ... and {len(self.progress.data['failed']) - 10} more"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# CONCURRENT WORKER
# ═══════════════════════════════════════════════════════════════════════════════


def _worker_run(
    worker_id: int,
    batch: list,
    session_cookie: str,
    config: dict,
    progress: ProgressTracker,
):
    """
    Worker function for concurrent downloads.
    Each worker creates its own HTTP session and processes its batch independently.
    """
    logger = get_logger(f"worker-{worker_id}")
    tag = f"[W{worker_id}]"
    logger.info(f"{tag} Starting with {len(batch)} khewats: {batch[0]}-{batch[-1]}")

    # Create an independent scraper with its own session
    scraper = JamabandiHTTPScraper(session_cookie, config, progress)

    # Get delays from config
    app_config = get_config()
    min_delay = app_config.delays.get("min_delay", config.get("min_delay", 1.0))
    max_delay = app_config.delays.get("max_delay", config.get("max_delay", 2.5))

    for i, khewat in enumerate(batch):
        # Skip if already completed (another worker or previous run)
        with progress._lock:
            if khewat in progress.data["completed"]:
                continue

        # Initialize form if needed
        if not scraper.form_initialized:
            logger.info(f"{tag} Initializing form...")
            if not scraper.initialize_form():
                logger.error(f"{tag} Session expired during init. Stopping worker.")
                return
            if not scraper.setup_form_selections():
                logger.error(f"{tag} Form setup failed. Stopping worker.")
                return

        success = scraper.download_nakal(khewat)

        if not success:
            logger.error(f"{tag} Session expired. Stopping worker.")
            return

        # Rate limiting
        if i < len(batch) - 1:
            delay = random.uniform(min_delay, max_delay)
            time.sleep(delay)

    logger.info(f"{tag} Finished batch.")


def run_concurrent(session_cookie: str, config: dict, num_workers: int):
    """
    Run the scraper with multiple concurrent workers.
    Splits pending khewats into batches and assigns each to a worker thread.
    """
    # Initialize logging for concurrent mode
    setup_logging()
    logger = get_logger()
    log_session_event("Concurrent scraping started", f"{num_workers} workers requested")

    progress = ProgressTracker(config["progress_file"])
    progress.set_config(config)
    retry_manager = RetryManager()

    pending = progress.get_pending(config["khewat_start"], config["khewat_end"])
    if not pending:
        logger.info("All khewat numbers already processed!")
        return

    # Cap workers to number of pending items
    actual_workers = min(num_workers, len(pending))

    logger.info(
        f"Concurrent mode: {actual_workers} workers for {len(pending)} pending khewats"
    )
    logger.info(f"Progress: {progress.get_summary()}")

    # Split into contiguous chunk-based batches (no round-robin so each worker
    # handles a contiguous range, reducing form re-init overhead)
    batch_size = len(pending) // actual_workers
    remainder = len(pending) % actual_workers
    batches = []
    start = 0
    for w in range(actual_workers):
        end = start + batch_size + (1 if w < remainder else 0)
        batches.append(pending[start:end])
        start = end

    # Log batch assignments
    logger.info("Batch assignments:")
    for idx, batch in enumerate(batches):
        if batch:
            logger.info(
                f"  Worker {idx}: khewat {batch[0]}-{batch[-1]} ({len(batch)} items)"
            )

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {}
        for worker_id, batch in enumerate(batches):
            if not batch:
                continue
            future = executor.submit(
                _worker_run, worker_id, batch, session_cookie, config, progress
            )
            futures[future] = worker_id

        for future in as_completed(futures):
            wid = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.exception(f"[W{wid}] Worker crashed: {e}")

    elapsed = time.time() - start_time

    log_session_event("Concurrent scraping complete", f"elapsed={elapsed:.1f}s")
    logger.info("=" * 60)
    logger.info("CONCURRENT SCRAPING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Time elapsed: {elapsed:.1f}s")
    logger.info(f"Final status: {progress.get_summary()}")

    if progress.data["failed"]:
        logger.warning("Failed khewat numbers:")
        for k, error in list(progress.data["failed"].items())[:10]:
            logger.warning(f"  - Khewat {k}: {error}")
        if len(progress.data["failed"]) > 10:
            logger.warning(f"  ... and {len(progress.data['failed']) - 10} more")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Jamabandi Land Records Scraper (HTTP version)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How to get your session cookie:
  1. Open Firefox/Chrome
  2. Go to https://jamabandi.nic.in/PublicNakal/login.aspx
  3. Complete OTP authentication
  4. Open Developer Tools (F12) > Application/Storage > Cookies
  5. Copy the value of 'jamabandiID' cookie
  6. Run: python main_http.py --cookie "your_cookie_value"
        """,
    )
    parser.add_argument(
        "--cookie", "-c", required=True, help="jamabandiID session cookie value"
    )
    parser.add_argument(
        "--start", type=int, default=None, help="Start khewat number (default: 1)"
    )
    parser.add_argument(
        "--end", type=int, default=None, help="End khewat number (default: 923)"
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=1,
        help="Number of concurrent download workers (1=sequential, 3-8 for concurrent)",
    )
    args = parser.parse_args()

    # Override config if provided
    if args.start:
        CONFIG["khewat_start"] = args.start
    if args.end:
        CONFIG["khewat_end"] = args.end

    num_workers = max(1, min(args.workers, 8))  # Clamp to 1-8

    print("=" * 60)
    print("JAMABANDI LAND RECORDS SCRAPER (HTTP)")
    print("=" * 60)
    print(
        f"Target: District {CONFIG['district_code']}, "
        f"Tehsil {CONFIG['tehsil_code']}, "
        f"Village {CONFIG['village_code']}"
    )
    print(f"Period: {CONFIG['period']}")
    print(f"Khewat range: {CONFIG['khewat_start']} - {CONFIG['khewat_end']}")
    print(f"Output directory: {CONFIG['downloads_dir']}/")
    print(f"Workers: {num_workers}")
    print("=" * 60)

    try:
        if num_workers > 1:
            # Concurrent mode
            run_concurrent(args.cookie, CONFIG, num_workers)
        else:
            # Sequential mode (original behavior)
            progress = ProgressTracker(CONFIG["progress_file"])
            print(f"\nCurrent status: {progress.get_summary()}")

            pending = progress.get_pending(CONFIG["khewat_start"], CONFIG["khewat_end"])
            if not pending:
                print("\nAll khewat numbers already processed!")
                print("To re-download, delete progress.json and run again.")
                return

            scraper = JamabandiHTTPScraper(args.cookie, CONFIG, progress)
            scraper.run()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()

    # ── Auto-convert HTML to PDF after scraping ──────────────────────
    auto_convert_to_pdf(CONFIG["downloads_dir"])


def auto_convert_to_pdf(downloads_dir: str):
    """Automatically convert all downloaded HTML files to PDF."""
    dl_path = Path(downloads_dir)
    html_files = sorted(dl_path.glob("nakal_khewat_*.html"))
    if not html_files:
        return

    # Count how many still need conversion
    pending = [f for f in html_files if not (dl_path / (f.stem + ".pdf")).exists()]
    if not pending:
        print("\nAll HTML files already converted to PDF.")
        return

    print("\n" + "=" * 60)
    print("AUTO-CONVERTING HTML TO PDF")
    print("=" * 60)
    print(f"Directory: {dl_path}/")
    print(
        f"Files to convert: {len(pending)} (skipping {len(html_files) - len(pending)} existing)"
    )
    print()

    try:
        from pdf_converter import convert_html_to_pdf as _convert

        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        # Use the parallel converter if available, otherwise fall back to sequential
        from pdf_converter import process_batch, split_into_batches, _init_worker

        file_pairs = [(str(f), str(dl_path / (f.stem + ".pdf"))) for f in pending]
        pdf_workers = min(4, len(file_pairs))

        shared_counter = multiprocessing.Value("i", 0)
        shared_total = multiprocessing.Value("i", len(file_pairs))
        batches = split_into_batches(file_pairs, pdf_workers)

        start_time = time.time()

        results = []
        with ProcessPoolExecutor(
            max_workers=pdf_workers,
            initializer=_init_worker,
            initargs=(shared_counter, shared_total, True),
        ) as executor:
            futures = {}
            for wid, batch in enumerate(batches):
                if not batch:
                    continue
                futures[executor.submit(process_batch, wid, batch)] = wid

            for future in as_completed(futures):
                wid = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    print(f"  [PDF Worker {wid}] crashed: {e}")

        elapsed = time.time() - start_time
        total_ok = sum(r["success_count"] for r in results)
        total_fail = sum(r["fail_count"] for r in results)

        print(
            f"\nPDF conversion done in {elapsed:.1f}s: "
            f"{total_ok} succeeded, {total_fail} failed"
        )

    except ImportError:
        print("WARNING: pdf_converter.py not found, skipping auto-conversion.")
    except Exception as e:
        print(f"WARNING: PDF conversion failed: {e}")
        print(
            f"You can convert manually: python pdf_converter.py --input {downloads_dir}"
        )


if __name__ == "__main__":
    main()
