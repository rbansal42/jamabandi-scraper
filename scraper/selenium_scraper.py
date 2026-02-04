#!/usr/bin/env python3
"""
Jamabandi Land Records Scraper
==============================
Scrapes PDF land records (Nakal) from jamabandi.nic.in

Features:
- Selenium-based OTP authentication
- Chrome's built-in PDF printing for clean PDFs
- Progress tracking with resume capability
- Rate limiting to avoid detection
- Automatic session expiry handling

Usage:
    pip install -r requirements.txt
    python main.py
"""

import base64
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "district_code": "17",  # Sirsa
    "tehsil_code": "102",
    "village_code": "02566",
    "period": "2024-2025",
    "khewat_start": 1,
    "khewat_end": 923,
    "min_delay": 2,  # seconds between requests
    "max_delay": 5,  # seconds between requests
    "max_retries": 3,  # retry attempts per khewat
    "page_load_timeout": 30,  # seconds to wait for page load
    "downloads_dir": "downloads",
    "progress_file": "progress.json",
}

# URLs
BASE_URL = "https://jamabandi.nic.in"
LOGIN_URL = f"{BASE_URL}/PublicNakal/login.aspx"
FORM_URL = f"{BASE_URL}/PublicNakal/CreateNewRequest"


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


class ProgressTracker:
    """Track downloaded khewat numbers for resume capability."""

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.data = {"config": {}, "completed": [], "failed": {}, "last_updated": None}
        self.load()

    def load(self):
        """Load progress from file if exists."""
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
        """Save progress to file."""
        self.data["last_updated"] = datetime.now().isoformat()
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def set_config(self, config: dict):
        """Store configuration for reference."""
        self.data["config"] = {
            "district": config["district_code"],
            "tehsil": config["tehsil_code"],
            "village": config["village_code"],
            "period": config["period"],
        }
        self.save()

    def mark_complete(self, khewat: int):
        """Mark a khewat as successfully downloaded."""
        if khewat not in self.data["completed"]:
            self.data["completed"].append(khewat)
            self.data["completed"].sort()
        # Remove from failed if it was there
        self.data["failed"].pop(str(khewat), None)
        self.save()

    def mark_failed(self, khewat: int, error: str):
        """Mark a khewat as failed with error message."""
        self.data["failed"][str(khewat)] = error
        self.save()

    def get_pending(self, start: int, end: int) -> list:
        """Get list of khewat numbers not yet completed."""
        completed_set = set(self.data["completed"])
        return [k for k in range(start, end + 1) if k not in completed_set]

    def get_summary(self) -> str:
        """Get a summary of progress."""
        return (
            f"Completed: {len(self.data['completed'])}, "
            f"Failed: {len(self.data['failed'])}, "
            f"Pending: {CONFIG['khewat_end'] - CONFIG['khewat_start'] + 1 - len(self.data['completed'])}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# JAMABANDI SCRAPER
# ═══════════════════════════════════════════════════════════════════════════════


class JamabandiScraper:
    """
    Selenium-based scraper for Jamabandi land records.

    Uses Chrome with PDF printing capability to save rendered Nakal pages.
    """

    def __init__(self, config: dict, progress: ProgressTracker):
        self.config = config
        self.progress = progress
        self.driver = None
        self.downloads_dir = Path(config["downloads_dir"])
        self.downloads_dir.mkdir(exist_ok=True)

    def _create_driver(self) -> webdriver.Chrome:
        """Create Chrome driver with PDF printing capability and anti-detection."""
        chrome_options = Options()

        # Anti-detection measures
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # Configure for PDF printing
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        # Set a realistic user agent
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # PDF printing settings
        app_state = {
            "recentDestinations": [
                {"id": "Save as PDF", "origin": "local", "account": ""}
            ],
            "selectedDestinationId": "Save as PDF",
            "version": 2,
        }

        prefs = {
            "printing.print_preview_sticky_settings.appState": json.dumps(app_state),
            "savefile.default_directory": str(self.downloads_dir.absolute()),
            "download.default_directory": str(self.downloads_dir.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": False,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_argument("--kiosk-printing")

        # Install and create driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(self.config["page_load_timeout"])

        # Additional anti-detection: modify navigator.webdriver
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            },
        )

        return driver

    def start(self):
        """Start the browser and initialize."""
        print("Starting Chrome browser...")
        self.driver = self._create_driver()
        print("Browser started successfully.")

    def stop(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            print("Browser closed.")

    def _dismiss_alert_if_present(self):
        """Dismiss any alert that might be present."""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            alert.accept()
            return alert_text
        except:
            return None

    def _safe_get_current_url(self):
        """Get current URL, handling any alerts that might appear."""
        try:
            self._dismiss_alert_if_present()
            return self.driver.current_url
        except:
            return ""

    def authenticate(self) -> bool:
        """
        Navigate to login page and wait for user to complete OTP authentication.
        Returns True if authentication successful.
        """
        print(f"\nNavigating to login page: {LOGIN_URL}")
        self.driver.get(LOGIN_URL)

        print("\n" + "=" * 60)
        print("MANUAL ACTION REQUIRED")
        print("=" * 60)
        print("1. Enter your mobile number in the browser")
        print("2. Click 'Send OTP'")
        print("3. Enter the OTP you receive")
        print("4. Complete the login process")
        print("=" * 60)
        print("\nWaiting for authentication (timeout: 5 minutes)...")

        start_time = time.time()
        timeout = 300  # 5 minutes

        while time.time() - start_time < timeout:
            try:
                # Dismiss any alerts (like "Invalid OTP")
                alert_text = self._dismiss_alert_if_present()
                if alert_text:
                    print(f"  Alert dismissed: {alert_text}")

                # Check current URL
                current_url = self._safe_get_current_url()

                if "CreateNewRequest" in current_url:
                    print("Authentication successful!")
                    return True

                if "default.aspx" in current_url.lower():
                    print("Logged in. Navigating to Nakal form...")
                    self.driver.get(FORM_URL)
                    time.sleep(2)
                    if "CreateNewRequest" in self._safe_get_current_url():
                        print("Authentication successful!")
                        return True

                time.sleep(1)  # Check every second

            except Exception as e:
                # Ignore errors during polling, just continue
                time.sleep(1)

        print("Authentication timeout. Please try again.")
        return False

    def _wait_for_element(self, by: By, value: str, timeout: int = 10):
        """Wait for an element to be present and return it."""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    def _wait_for_clickable(self, by: By, value: str, timeout: int = 10):
        """Wait for an element to be clickable and return it."""
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )

    def _wait_for_dropdown_options(self, element_id: str, timeout: int = 15):
        """Wait until dropdown has more than one option (data loaded)."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: len(Select(d.find_element(By.ID, element_id)).options) > 1
            )
            return True
        except:
            return False

    def _select_dropdown(self, element_id: str, value: str, wait_after: float = 2.0):
        """Select a value from dropdown and wait for postback."""
        try:
            # First dismiss any alerts
            self._dismiss_alert_if_present()

            # Check if we're still logged in
            if "login" in self.driver.current_url.lower():
                print(f"    Session lost before selecting {element_id}")
                return False

            # Wait for dropdown to be present
            dropdown = self._wait_for_element(By.ID, element_id, timeout=10)

            # Wait for options to load
            self._wait_for_dropdown_options(element_id, timeout=10)

            # Select using JavaScript for more reliable behavior
            self.driver.execute_script(
                f"document.getElementById('{element_id}').value = '{value}';"
            )

            # Trigger the change event to activate postback
            self.driver.execute_script(
                f"document.getElementById('{element_id}').dispatchEvent(new Event('change'));"
            )

            time.sleep(wait_after)  # Wait for AJAX/postback

            # Check if still logged in after postback
            self._dismiss_alert_if_present()
            if "login" in self.driver.current_url.lower():
                print(f"    Session lost after selecting {element_id}")
                return False

            return True
        except Exception as e:
            print(f"Error selecting {element_id}={value}: {e}")
            return False

    def _select_radio(self, element_id: str, wait_after: float = 2.0):
        """Click a radio button and wait for postback."""
        try:
            # First dismiss any alerts
            self._dismiss_alert_if_present()

            # Check if we're still logged in
            if "login" in self.driver.current_url.lower():
                print(f"    Session lost before selecting radio {element_id}")
                return False

            # Use JavaScript click for reliability
            self.driver.execute_script(
                f"document.getElementById('{element_id}').click();"
            )
            time.sleep(wait_after)  # Wait for AJAX/postback

            # Check if still logged in
            self._dismiss_alert_if_present()
            if "login" in self.driver.current_url.lower():
                print(f"    Session lost after selecting radio {element_id}")
                return False

            return True
        except Exception as e:
            print(f"Error selecting radio {element_id}: {e}")
            return False

    def setup_form(self) -> bool:
        """
        Set up the form with district, tehsil, village, period selections.
        This needs to be done once per session.
        """
        print("\nSetting up form selections...")

        try:
            # Make sure we're on the form page
            current_url = self._safe_get_current_url()
            if "CreateNewRequest" not in current_url:
                if "login" in current_url.lower():
                    print("  Not logged in!")
                    return False
                self.driver.get(FORM_URL)
                time.sleep(3)

            # Check for login redirect
            if "login" in self._safe_get_current_url().lower():
                print("  Session expired - redirected to login")
                return False

            # Select "By Khewat" radio button
            print("  Selecting search type: By Khewat")
            if not self._select_radio("RdobtnKhewat", wait_after=3):
                return False

            # Select District - wait a bit longer for the first dropdown
            print(f"  Selecting district: {self.config['district_code']}")
            time.sleep(1)
            if not self._select_dropdown(
                "ddldname", self.config["district_code"], wait_after=3
            ):
                return False

            # Select Tehsil
            print(f"  Selecting tehsil: {self.config['tehsil_code']}")
            if not self._select_dropdown(
                "ddltname", self.config["tehsil_code"], wait_after=3
            ):
                return False

            # Select Village
            print(f"  Selecting village: {self.config['village_code']}")
            if not self._select_dropdown(
                "ddlvname", self.config["village_code"], wait_after=3
            ):
                return False

            # Select Period
            print(f"  Selecting period: {self.config['period']}")
            if not self._select_dropdown(
                "ddlPeriod", self.config["period"], wait_after=3
            ):
                return False

            print("Form setup complete!")
            return True

        except Exception as e:
            print(f"Error setting up form: {e}")
            return False

    def _check_session_valid(self) -> bool:
        """Check if we're still logged in."""
        current_url = self.driver.current_url
        if "login" in current_url.lower() or "NotFound" in current_url:
            return False
        return True

    def _save_page_as_pdf(self, khewat: int) -> bool:
        """Save current page as PDF using Chrome DevTools Protocol."""
        try:
            filename = f"nakal_khewat_{khewat:04d}.pdf"
            filepath = self.downloads_dir / filename

            # Use Chrome DevTools Protocol to print to PDF
            pdf_data = self.driver.execute_cdp_cmd(
                "Page.printToPDF",
                {
                    "printBackground": True,
                    "preferCSSPageSize": True,
                    "paperWidth": 8.27,  # A4 width in inches
                    "paperHeight": 11.69,  # A4 height in inches
                    "marginTop": 0.4,
                    "marginBottom": 0.4,
                    "marginLeft": 0.4,
                    "marginRight": 0.4,
                },
            )

            # Decode and save PDF
            pdf_bytes = base64.b64decode(pdf_data["data"])
            with open(filepath, "wb") as f:
                f.write(pdf_bytes)

            print(f"    Saved: {filename} ({len(pdf_bytes)} bytes)")
            return True

        except Exception as e:
            print(f"    Error saving PDF: {e}")
            return False

    def download_nakal(self, khewat: int) -> bool:
        """
        Download Nakal for a specific khewat number.
        Returns True if successful.
        """
        print(f"  Processing khewat {khewat}...")

        try:
            # Check session
            if not self._check_session_valid():
                print("    Session expired!")
                return False

            # Select khewat from dropdown
            if not self._select_dropdown("ddlkhewat", str(khewat), wait_after=1):
                print(f"    Khewat {khewat} not found in dropdown")
                self.progress.mark_failed(khewat, "Not found in dropdown")
                return True  # Continue to next, this is not a session error

            # Remember original window
            original_window = self.driver.current_window_handle
            original_windows = set(self.driver.window_handles)

            # Click Nakal button
            try:
                nakal_btn = self._wait_for_clickable(By.NAME, "Cmdnakal", timeout=5)
                nakal_btn.click()
            except:
                # Try alternative selectors
                try:
                    nakal_btn = self._wait_for_clickable(By.ID, "Cmdnakal", timeout=5)
                    nakal_btn.click()
                except:
                    # Try by value
                    nakal_btn = self.driver.find_element(
                        By.XPATH, "//input[@value='Nakal']"
                    )
                    nakal_btn.click()

            # Wait for new window/tab to open or page to load
            time.sleep(3)

            # Check if a new window opened
            new_windows = set(self.driver.window_handles) - original_windows
            if new_windows:
                # Switch to the new window
                new_window = new_windows.pop()
                self.driver.switch_to.window(new_window)
                print(f"    Switched to new window for Nakal content")
                time.sleep(2)  # Wait for content to load

            # Wait for actual content to load - look for specific elements
            # that indicate the Nakal content is ready
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda d: len(d.page_source) > 5000
                    or "no record" in d.page_source.lower()
                    or "nakal" in d.page_source.lower()
                )
            except:
                pass  # Continue anyway

            # Additional wait for content rendering
            time.sleep(2)

            # Check if we got a result or error
            page_source = self.driver.page_source.lower()

            if "no record found" in page_source or "record not found" in page_source:
                print(f"    No record found for khewat {khewat}")
                self.progress.mark_failed(khewat, "No record found")
                # Close new window if opened, switch back to original
                if new_windows:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                else:
                    self.driver.get(FORM_URL)
                    time.sleep(2)
                    self.setup_form()
                return True  # Continue to next

            if "login" in self.driver.current_url.lower():
                print("    Session expired during request!")
                return False

            # Save the page as PDF
            if self._save_page_as_pdf(khewat):
                self.progress.mark_complete(khewat)
                # Close new window if opened, switch back to original
                if new_windows:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                    time.sleep(1)
                else:
                    # Navigate back to form for next khewat
                    self.driver.get(FORM_URL)
                    time.sleep(2)
                    self.setup_form()
                return True
            else:
                self.progress.mark_failed(khewat, "Failed to save PDF")
                if new_windows:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                return True  # Continue to next

        except TimeoutException:
            print(f"    Timeout processing khewat {khewat}")
            self.progress.mark_failed(khewat, "Timeout")
            return True  # Continue to next
        except Exception as e:
            print(f"    Error processing khewat {khewat}: {e}")
            # Check if it's a session error
            if not self._check_session_valid():
                return False
            self.progress.mark_failed(khewat, str(e))
            return True  # Continue to next

    def run(self):
        """Main scraping loop."""
        self.progress.set_config(self.config)

        while True:
            # Get pending khewat numbers
            pending = self.progress.get_pending(
                self.config["khewat_start"], self.config["khewat_end"]
            )

            if not pending:
                print("\nAll khewat numbers have been processed!")
                break

            print(f"\nPending: {len(pending)} khewat numbers")
            print(f"Progress: {self.progress.get_summary()}")

            # Start browser if not running
            if not self.driver:
                self.start()

            # Authenticate
            if not self.authenticate():
                print("Authentication failed. Retrying...")
                continue

            # Setup form
            if not self.setup_form():
                print("Form setup failed. Retrying...")
                self.driver.get(FORM_URL)
                time.sleep(2)
                continue

            # Process each pending khewat
            for khewat in pending:
                success = self.download_nakal(khewat)

                if not success:
                    # Session expired, need to re-authenticate
                    print("\nSession expired. Re-authenticating...")
                    break

                # Rate limiting
                delay = random.uniform(
                    self.config["min_delay"], self.config["max_delay"]
                )
                print(f"    Waiting {delay:.1f}s before next request...")
                time.sleep(delay)

            # Check if we completed all
            remaining = self.progress.get_pending(
                self.config["khewat_start"], self.config["khewat_end"]
            )
            if not remaining:
                break

        # Final summary
        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE")
        print("=" * 60)
        print(f"Final status: {self.progress.get_summary()}")

        if self.progress.data["failed"]:
            print("\nFailed khewat numbers:")
            for k, error in self.progress.data["failed"].items():
                print(f"  - Khewat {k}: {error}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Jamabandi Land Records Scraper")
    parser.add_argument(
        "--no-confirm", action="store_true", help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--start", type=int, default=None, help="Override start khewat number"
    )
    parser.add_argument(
        "--end", type=int, default=None, help="Override end khewat number"
    )
    args = parser.parse_args()

    # Override config if provided
    if args.start:
        CONFIG["khewat_start"] = args.start
    if args.end:
        CONFIG["khewat_end"] = args.end

    print("=" * 60)
    print("JAMABANDI LAND RECORDS SCRAPER")
    print("=" * 60)
    print(
        f"Target: District {CONFIG['district_code']}, "
        f"Tehsil {CONFIG['tehsil_code']}, "
        f"Village {CONFIG['village_code']}"
    )
    print(f"Period: {CONFIG['period']}")
    print(f"Khewat range: {CONFIG['khewat_start']} - {CONFIG['khewat_end']}")
    print(f"Output directory: {CONFIG['downloads_dir']}/")
    print("=" * 60)

    # Initialize progress tracker
    progress = ProgressTracker(CONFIG["progress_file"])

    # Show current progress
    pending = progress.get_pending(CONFIG["khewat_start"], CONFIG["khewat_end"])
    print(f"\nCurrent status: {progress.get_summary()}")

    if not pending:
        print("\nAll khewat numbers already processed!")
        print("To re-download, delete progress.json and run again.")
        return

    print(f"\nWill process {len(pending)} khewat numbers.")

    # Confirm before starting (unless --no-confirm)
    if not args.no_confirm:
        try:
            input("\nPress Enter to start (or Ctrl+C to cancel)...")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return

    # Initialize and run scraper
    scraper = JamabandiScraper(CONFIG, progress)

    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        print(f"Progress saved. {progress.get_summary()}")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        print(f"Progress saved. {progress.get_summary()}")
        raise
    finally:
        scraper.stop()


if __name__ == "__main__":
    main()
