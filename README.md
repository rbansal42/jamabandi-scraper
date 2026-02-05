# Jamabandi Land Records Scraper

Download Jamabandi (land records) from **jamabandi.nic.in** as PDF files.

## Download

Get the latest release for your platform:

| Platform | Download | 
|----------|----------|
| **Windows** | [JamabandiScraper.exe](https://github.com/rbansal42/jamabandi-scraper/releases/latest) |
| **macOS** | [JamabandiScraper.dmg](https://github.com/rbansal42/jamabandi-scraper/releases/latest) |

No Python installation required - just download and run!

---

## Quick Start Guide

### Step 1: Get Your Session Cookie

The Jamabandi website requires login with captcha. You need to copy your session cookie from the browser.

1. Open **Chrome** or **Edge** browser
2. Go to **https://jamabandi.nic.in/PublicNakal**
3. Complete the login/captcha process
4. Press **F12** to open Developer Tools
5. Click the **Application** tab (Chrome) or **Storage** tab (Firefox)
6. In the left sidebar, expand **Cookies** and click on `https://jamabandi.nic.in`
7. Find the cookie named **`jamabandiID`** (or `ASP.NET_SessionId`)
8. Double-click the **Value** column and copy it (e.g., `abc123xyz...`)

![Cookie Location](https://i.imgur.com/cookie-example.png)

### Step 2: Run the Application

1. **Windows:** Double-click `JamabandiScraper.exe`
2. **macOS:** Open `JamabandiScraper.dmg` and drag to Applications, then run

### Step 3: Configure and Start

1. Paste your **Session Cookie** in the cookie field
2. Enter the location details:
   - **District Code** (e.g., `17` for Sirsa)
   - **Tehsil Code** (e.g., `102`)
   - **Village Code** (e.g., `05464`)
   - **Period** (e.g., `2024-2025`)
   - **Khewat Range** (start and end numbers)
3. Click **Start Scraping**

The tool will download each record as HTML and automatically convert to PDF.

---

## Features

- **GUI Application** - Easy to use graphical interface
- **Automatic PDF Conversion** - HTML records converted to landscape A4 PDFs
- **Resume Support** - Interrupted downloads resume from where they left off
- **Session Expiry Detection** - Prompts for new cookie when session expires
- **Concurrent Downloads** - Optional parallel downloading (3-8 workers)
- **Automatic Retry** - Failed downloads are retried automatically
- **Adaptive Rate Limiting** - Adjusts speed based on server response
- **Real-Time Statistics** - Download speed, ETA, success rate
- **Update Checker** - Notifies when new version is available

---

## GUI Overview

| Section | Description |
|---------|-------------|
| **Main Settings** | District, tehsil, village, period, khewat range, session cookie |
| **Downloads Path** | Where PDFs are saved (auto-creates `downloads_<village>` if blank) |
| **Concurrent Downloads** | Enable for faster downloads with multiple workers |
| **Advanced Settings** | Click `+` then `Unlock` (password: `admin123`) for delays, retries |
| **Progress Bar** | Shows download progress with counts |
| **Log Output** | Live output from the scraper |

---

## Troubleshooting

### "Session Expired" Error

Your session cookie has expired. This happens after ~30 minutes of inactivity.

**Solution:**
1. Go back to jamabandi.nic.in in your browser
2. Refresh the page and complete captcha if needed
3. Copy the new cookie value (it changes each session)
4. Paste in the app and click Start again

The app will resume from where it left off.

### "No Record Found" for Some Khewats

This is normal - not every khewat number has a record. The scraper will:
- Log these as "no record" (not errors)
- Continue to the next khewat
- Not retry these (they're permanent, not transient failures)

### PDF Conversion Fails

The app includes WeasyPrint for PDF conversion. If you see conversion errors:

**Windows:** Install wkhtmltopdf for better compatibility:
1. Download from https://wkhtmltopdf.org/downloads.html
2. Install to default location
3. Restart the app

**macOS:** Usually works out of the box. If issues persist, install via Homebrew:
```bash
brew install wkhtmltopdf
```

### App Won't Start (macOS)

macOS may block unsigned apps. To allow:
1. Right-click the app and select "Open"
2. Click "Open" in the security dialog
3. Or: System Preferences > Security & Privacy > "Open Anyway"

### App Won't Start (Windows)

Windows Defender may block the app. To allow:
1. Click "More info" on the SmartScreen warning
2. Click "Run anyway"

---

## Tips

- **Cookie expires quickly** - Get a fresh cookie right before starting a large download
- **Use concurrent mode** for faster downloads (enable checkbox, 3-8 workers)
- **Check the log** for detailed progress and any errors
- **Resume anytime** - Progress is saved, just restart with same settings

---

## Running from Source (Advanced)

If you prefer to run from source code instead of the standalone app:

### Requirements
- Python 3.10 or newer
- tkinter (usually included with Python)

### Installation

```bash
# Clone the repository
git clone https://github.com/rbansal42/jamabandi-scraper.git
cd jamabandi-scraper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run the GUI
python run.py
```

### Command Line Usage

```bash
# Run scraper directly
python -m scraper.http_scraper --cookie YOUR_COOKIE --start 1 --end 100

# Convert HTML to PDF manually
python -m scraper.pdf_converter --input downloads_05464 --workers 4
```

---

## Configuration

Create `config.yaml` in the app directory to customize settings:

```yaml
delays:
  min_delay: 2.0      # Minimum delay between requests (seconds)
  max_delay: 5.0      # Maximum delay between requests

http:
  timeout: 60         # Request timeout (seconds)

retry:
  max_retries: 3      # Number of retry attempts

concurrency:
  max_workers: 5      # Maximum concurrent download workers

logging:
  level: INFO         # Log level: DEBUG, INFO, WARNING, ERROR
```

---

## Project Structure

```
jamabandi-scraper/
├── run.py                    # Entry point
├── requirements.txt          # Python dependencies
├── config.yaml              # Configuration (optional)
├── scraper/
│   ├── gui.py               # GUI application
│   ├── http_scraper.py      # HTTP-based scraper
│   ├── pdf_converter.py     # HTML to PDF converter
│   ├── pdf_backend.py       # PDF conversion backends
│   ├── session_manager.py   # Session expiry handling
│   ├── statistics.py        # Download statistics
│   ├── rate_limiter.py      # Adaptive rate limiting
│   ├── retry_manager.py     # Failed download retry
│   ├── validator.py         # Download validation
│   ├── update_checker.py    # Version update checker
│   ├── cookie_capture.py    # Cookie capture helpers
│   ├── config.py            # Configuration loader
│   └── logger.py            # Logging setup
└── tests/                   # Unit tests
```

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

## Support

- **Issues:** [GitHub Issues](https://github.com/rbansal42/jamabandi-scraper/issues)
- **Releases:** [GitHub Releases](https://github.com/rbansal42/jamabandi-scraper/releases)
