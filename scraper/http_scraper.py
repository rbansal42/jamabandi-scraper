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

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "district_code": "17",
    "tehsil_code": "102",
    "village_code": "02556",
    "period": "2022-2023",
    "khewat_start": 1,
    "khewat_end": 100,
    "min_delay": 1.0,
    "max_delay": 2.5,
    "max_retries": 3,
    "page_load_timeout": 30,
    "form_postback_sleep": 0.25,
    "downloads_dir": "/Volumes/Code/script/downloads_02556",
    "progress_file": "progress.json",
}

# URLs
BASE_URL = "https://jamabandi.nic.in"
FORM_URL = f"{BASE_URL}/PublicNakal/CreateNewRequest"

# Headers to mimic browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
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


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


class ProgressTracker:
    """Thread-safe tracker for downloaded khewat numbers with resume capability."""

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.data = {"config": {}, "completed": [], "failed": {}, "last_updated": None}
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                print(
                    f"Loaded progress: {len(self.data['completed'])} completed, "
                    f"{len(self.data['failed'])} failed"
                )
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load progress file: {e}")

    def save(self):
        self.data["last_updated"] = datetime.now().isoformat()
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def set_config(self, config: dict):
        with self._lock:
            self.data["config"] = {
                "district": config["district_code"],
                "tehsil": config["tehsil_code"],
                "village": config["village_code"],
                "period": config["period"],
            }
            self.save()

    def mark_complete(self, khewat: int):
        with self._lock:
            if khewat not in self.data["completed"]:
                self.data["completed"].append(khewat)
                self.data["completed"].sort()
            self.data["failed"].pop(str(khewat), None)
            self.save()

    def mark_failed(self, khewat: int, error: str):
        with self._lock:
            self.data["failed"][str(khewat)] = error
            self.save()

    def get_pending(self, start: int, end: int) -> list:
        with self._lock:
            completed_set = set(self.data["completed"])
            return [k for k in range(start, end + 1) if k not in completed_set]

    def get_summary(self) -> str:
        with self._lock:
            total = CONFIG["khewat_end"] - CONFIG["khewat_start"] + 1
            return (
                f"Completed: {len(self.data['completed'])}, "
                f"Failed: {len(self.data['failed'])}, "
                f"Pending: {total - len(self.data['completed'])}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP SCRAPER
# ═══════════════════════════════════════════════════════════════════════════════


class JamabandiHTTPScraper:
    """
    HTTP-based scraper for Jamabandi land records.
    Uses requests library with session cookies from manual authentication.
    """

    def __init__(self, session_cookie: str, config: dict, progress: ProgressTracker):
        self.config = config
        self.progress = progress
        self.downloads_dir = Path(config["downloads_dir"])
        self.downloads_dir.mkdir(exist_ok=True)

        # Create session with cookie
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.cookies.set(
            "jamabandiID", session_cookie, domain="jamabandi.nic.in"
        )

        # Disable SSL verification (site has certificate issues)
        self.session.verify = False
        # Suppress SSL warnings
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # ASP.NET form state
        self.viewstate = None
        self.viewstate_generator = None
        self.event_validation = None
        self.form_initialized = False

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

        response = self.session.post(
            FORM_URL,
            data=data,
            headers={**HEADERS, "Referer": FORM_URL},
            allow_redirects=True,
        )
        return response

    def initialize_form(self) -> bool:
        """Load the form page and extract initial tokens."""
        print("Loading form page...")

        response = self.session.get(FORM_URL, headers=HEADERS)

        if response.status_code != 200:
            print(f"  Failed to load form: HTTP {response.status_code}")
            return False

        if not self._check_logged_in(response.text):
            print("  Session invalid - not logged in!")
            return False

        if not self._parse_asp_tokens(response.text):
            print("  Failed to parse ASP.NET tokens")
            return False

        print("  Form loaded successfully")
        return True

    def setup_form_selections(self) -> bool:
        """Set up all form selections (district, tehsil, village, period)."""
        print("Setting up form selections...")
        postback_sleep = self.config.get("form_postback_sleep", 0.25)

        # Step 1: Select "By Khewat" radio
        print("  Selecting: By Khewat")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": "-1",
            "ddltname": "",
            "ddlvname": "",
            "ddlPeriod": "",
        }
        response = self._make_postback("RdobtnKhewat", form_data)
        if not self._parse_asp_tokens(response.text):
            print("    Failed after radio selection")
            return False
        time.sleep(postback_sleep)

        # Step 2: Select District
        print(f"  Selecting district: {self.config['district_code']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": "",
            "ddlvname": "",
            "ddlPeriod": "",
        }
        response = self._make_postback("ddldname", form_data)
        if not self._parse_asp_tokens(response.text):
            print("    Failed after district selection")
            return False
        time.sleep(postback_sleep)

        # Step 3: Select Tehsil
        print(f"  Selecting tehsil: {self.config['tehsil_code']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": "",
            "ddlPeriod": "",
        }
        response = self._make_postback("ddltname", form_data)
        if not self._parse_asp_tokens(response.text):
            print("    Failed after tehsil selection")
            return False
        time.sleep(postback_sleep)

        # Step 4: Select Village
        print(f"  Selecting village: {self.config['village_code']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": self.config["village_code"],
            "ddlPeriod": "",
        }
        response = self._make_postback("ddlvname", form_data)
        if not self._parse_asp_tokens(response.text):
            print("    Failed after village selection")
            return False
        time.sleep(postback_sleep)

        # Step 5: Select Period
        print(f"  Selecting period: {self.config['period']}")
        form_data = {
            "a": "RdobtnKhewat",
            "ddldname": self.config["district_code"],
            "ddltname": self.config["tehsil_code"],
            "ddlvname": self.config["village_code"],
            "ddlPeriod": self.config["period"],
        }
        response = self._make_postback("ddlPeriod", form_data)
        if not self._parse_asp_tokens(response.text):
            print("    Failed after period selection")
            return False

        # Check if khewat dropdown is now available
        if "ddlkhewat" in response.text.lower():
            print("  Form setup complete!")
            self.form_initialized = True
            return True
        else:
            print("  Warning: Khewat dropdown not found after setup")
            # Save response for debugging
            with open("debug_form.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("  Saved response to debug_form.html")
            return False

    def download_nakal(self, khewat: int) -> bool:
        """Download Nakal for a specific khewat number."""
        print(f"  Processing khewat {khewat}...")

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
            response = self.session.post(
                FORM_URL,
                data=form_data,
                headers={**HEADERS, "Referer": FORM_URL},
                allow_redirects=True,
                timeout=30,
            )

            # Check response
            if response.status_code != 200:
                print(f"    HTTP Error: {response.status_code}")
                self.progress.mark_failed(khewat, f"HTTP {response.status_code}")
                return True  # Continue to next

            # Check if session expired
            if (
                "login.aspx" in response.url.lower()
                or "login.aspx" in response.text.lower()
            ):
                print("    Session expired!")
                return False  # Need re-auth

            # Check for "no record" message
            if (
                "no record" in response.text.lower()
                or "record not found" in response.text.lower()
            ):
                print(f"    No record found for khewat {khewat}")
                self.progress.mark_failed(khewat, "No record found")
                self._parse_asp_tokens(response.text)  # Update tokens
                return True

            # Check for error page
            if (
                "error page" in response.text.lower()
                or "some error has occured" in response.text.lower()
            ):
                print(
                    f"    Error page returned for khewat {khewat} - will retry after form refresh"
                )
                self.progress.mark_failed(khewat, "Error page - needs retry")
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
                print(f"    Saved: {filename} ({len(response.content)} bytes)")
                self.progress.mark_complete(khewat)
            else:
                # HTML response - check if it's actual Nakal content (should be large)
                if len(response.text) > 10000 and "nakal" in response.text.lower():
                    # Save as HTML
                    filename = f"nakal_khewat_{khewat:04d}.html"
                    filepath = self.downloads_dir / filename
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(response.text)
                    print(f"    Saved: {filename} ({len(response.text)} bytes)")
                    self.progress.mark_complete(khewat)
                else:
                    # Probably an error or empty response
                    print(
                        f"    Unexpected small response ({len(response.text)} bytes) for khewat {khewat}"
                    )
                    self.progress.mark_failed(
                        khewat, f"Small response: {len(response.text)} bytes"
                    )

            # After viewing Nakal, we're on a different page - need to re-setup form
            self.form_initialized = False
            return True

        except requests.Timeout:
            print(f"    Timeout for khewat {khewat}")
            self.progress.mark_failed(khewat, "Timeout")
            return True
        except Exception as e:
            print(f"    Error: {e}")
            self.progress.mark_failed(khewat, str(e))
            return True

    def run(self):
        """Main scraping loop."""
        self.progress.set_config(self.config)

        # Initialize form
        if not self.initialize_form():
            print("\nFailed to initialize. Please check your session cookie.")
            return

        # Setup form selections
        if not self.setup_form_selections():
            print("\nFailed to setup form. Session may have expired.")
            return

        # Get pending khewat numbers
        pending = self.progress.get_pending(
            self.config["khewat_start"], self.config["khewat_end"]
        )

        print(f"\nProcessing {len(pending)} khewat numbers...")
        print(f"Progress: {self.progress.get_summary()}")
        print()

        for i, khewat in enumerate(pending):
            # Check if we need to re-setup the form (after errors)
            if not self.form_initialized:
                print("  Re-initializing form...")
                if not self.initialize_form():
                    print("\nSession expired during re-init. Please get new cookie.")
                    break
                if not self.setup_form_selections():
                    print("\nFailed to re-setup form. Session may have expired.")
                    break

            success = self.download_nakal(khewat)

            if not success:
                print("\nSession expired. Please get a new cookie and restart.")
                break

            # Rate limiting
            if i < len(pending) - 1:  # Don't wait after last one
                delay = random.uniform(
                    self.config["min_delay"], self.config["max_delay"]
                )
                print(f"    Waiting {delay:.1f}s...")
                time.sleep(delay)

        # Summary
        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Final status: {self.progress.get_summary()}")

        if self.progress.data["failed"]:
            print("\nFailed khewat numbers:")
            for k, error in list(self.progress.data["failed"].items())[:10]:
                print(f"  - Khewat {k}: {error}")
            if len(self.progress.data["failed"]) > 10:
                print(f"  ... and {len(self.progress.data['failed']) - 10} more")


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
    tag = f"[W{worker_id}]"
    print(f"{tag} Starting with {len(batch)} khewats: {batch[0]}-{batch[-1]}")

    # Create an independent scraper with its own session
    scraper = JamabandiHTTPScraper(session_cookie, config, progress)

    for i, khewat in enumerate(batch):
        # Skip if already completed (another worker or previous run)
        with progress._lock:
            if khewat in progress.data["completed"]:
                continue

        # Initialize form if needed
        if not scraper.form_initialized:
            print(f"{tag} Initializing form...")
            if not scraper.initialize_form():
                print(f"{tag} Session expired during init. Stopping worker.")
                return
            if not scraper.setup_form_selections():
                print(f"{tag} Form setup failed. Stopping worker.")
                return

        success = scraper.download_nakal(khewat)

        if not success:
            print(f"{tag} Session expired. Stopping worker.")
            return

        # Rate limiting
        if i < len(batch) - 1:
            delay = random.uniform(config["min_delay"], config["max_delay"])
            time.sleep(delay)

    print(f"{tag} Finished batch.")


def run_concurrent(session_cookie: str, config: dict, num_workers: int):
    """
    Run the scraper with multiple concurrent workers.
    Splits pending khewats into batches and assigns each to a worker thread.
    """
    progress = ProgressTracker(config["progress_file"])
    progress.set_config(config)

    pending = progress.get_pending(config["khewat_start"], config["khewat_end"])
    if not pending:
        print("\nAll khewat numbers already processed!")
        return

    # Cap workers to number of pending items
    actual_workers = min(num_workers, len(pending))

    print(
        f"\nConcurrent mode: {actual_workers} workers for {len(pending)} pending khewats"
    )
    print(f"Progress: {progress.get_summary()}")

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

    # Print batch assignments
    print("\nBatch assignments:")
    for idx, batch in enumerate(batches):
        if batch:
            print(f"  Worker {idx}: khewat {batch[0]}-{batch[-1]} ({len(batch)} items)")
    print()

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
                print(f"[W{wid}] Worker crashed: {e}")

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("CONCURRENT SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"Final status: {progress.get_summary()}")

    if progress.data["failed"]:
        print("\nFailed khewat numbers:")
        for k, error in list(progress.data["failed"].items())[:10]:
            print(f"  - Khewat {k}: {error}")
        if len(progress.data["failed"]) > 10:
            print(f"  ... and {len(progress.data['failed']) - 10} more")


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
            initargs=(shared_counter, shared_total),
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
