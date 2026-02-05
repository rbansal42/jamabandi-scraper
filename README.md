# Jamabandi Land Records Scraper

Download Jamabandi (land records) from **jamabandi.nic.in** as PDF files.

This tool logs into the Jamabandi website using your session cookie, downloads all
Nakal records for a village as HTML, and converts them to landscape PDF files
automatically.

---

## Quick Start

### Step 1 - Install

1. Make sure **Python 3.10+** is installed on your computer
   - **Mac:** comes pre-installed, or run `brew install python`
   - **Windows:** download from https://www.python.org/downloads/

2. Double-click the installer for your system:
   - **Mac:** `Install Dependencies.command`
   - **Windows:** `Install Dependencies.cmd`

   This creates a virtual environment and installs all required packages.

### Step 2 - Get Your Session Cookie

The Jamabandi website requires login. The scraper needs your session cookie to
download records on your behalf.

1. Open **https://jamabandi.nic.in** in your browser and **log in**
2. Open Developer Tools (press `F12` or `Cmd+Option+I` on Mac)
3. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
4. Under **Cookies**, click on `https://jamabandi.nic.in`
5. Find the cookie named `ASP.NET_SessionId` (or similar session cookie)
6. Copy its **Value** (e.g. `c1l3rgujedy2qgc5gycc5ehx`)

### Step 3 - Run

1. Double-click the launcher:
   - **Mac:** `Jamabandi Scraper.command`
   - **Windows:** `Jamabandi Scraper.cmd`

2. The GUI window will open. Fill in:
   - **District Code** (e.g. `17` for Sirsa)
   - **Tehsil Code** (e.g. `102`)
   - **Village Code** (e.g. `05464`)
   - **Period** (e.g. `2024-2025`)
   - **Khewat Start / End** (range of khewat numbers to download)
   - **Session Cookie** (paste the value from Step 2)

3. Click **Start Scraping**

4. The tool will:
   - Download each khewat record as HTML
   - Show real-time progress in the progress bar
   - Automatically convert all HTML files to PDF when done
   - Delete the HTML files after successful conversion

5. Your PDF files will be in the `downloads_<village_code>/` folder.

---

## GUI Overview

| Section | What it does |
|---------|-------------|
| **Main Settings** | District, tehsil, village, period, khewat range, cookie |
| **Downloads Path** | Where PDFs are saved. Leave blank to auto-create `downloads_<village>` |
| **Concurrent Downloads** | Enable to use 3-8 parallel workers (faster but more load on server) |
| **Advanced Settings** | Click `+` to expand, then `Unlock` (password: `admin123`) to adjust delays, retries, timeouts |
| **PDF Conversion** | Input/output dirs and worker count for manual conversion |
| **Start Scraping** | Begin downloading records |
| **Convert HTML to PDF** | Manually convert HTML files if auto-convert was off |
| **Stop** | Stop the running process |
| **Progress Bar** | Shows download/conversion progress with counts |
| **Log Output** | Live output from the scraper |

---

## Tips

- **Session cookies expire.** If you get errors about expired sessions, log in
  again on the website and paste the new cookie value.

- **Resume support.** If the scraper is interrupted, just run it again with the
  same settings. It automatically skips already-downloaded khewats using a
  progress file stored in the downloads folder.

- **Concurrent mode** is faster but uses more connections. Start with the default
  (sequential) if you are unsure.

- **PDFs are landscape A4** to fit the 12-column Jamabandi table without clipping.

---

## Reliability Features

### Automatic Retry
Failed downloads are automatically retried at the end of a scraping session. The retry manager:
- Classifies failures as transient (worth retrying) or permanent (no record exists)
- Uses exponential backoff between retry attempts
- Respects configurable max retries (default: 3)

### Adaptive Rate Limiting
The scraper automatically adjusts request delays based on server response:
- Backs off on 429 (Too Many Requests) errors
- Increases delay on server errors (5xx)
- Decreases delay when server is responsive

### Progress Persistence
Progress is saved atomically every few downloads to prevent data loss:
- Uses temp file + rename for atomic writes
- Configurable save interval
- Tracks statistics (download count, time, etc.)

### Download Validation
Each download is validated before saving:
- HTML checked for error patterns (no record, session expired, etc.)
- PDF validated for correct header and minimum size

### Session Management
The scraper automatically handles session expiry during long-running scrapes:
- Monitors HTTP responses for login redirects and expiry messages
- Pauses all workers when session expires
- GUI prompts for new cookie without losing progress
- Resumes from where it left off after re-authentication

### Real-Time Statistics
Track download progress with live statistics in the GUI:
- Downloads per minute (speed)
- Estimated time remaining (ETA)
- Success rate percentage
- Total bytes downloaded

### Cookie Capture
Two methods for obtaining the session cookie:
- **Manual:** Copy from browser DevTools (always available)
- **Webview:** Built-in browser window for automatic capture (requires pywebview)

---

## Configuration

The scraper can be configured via `config.yaml` in the project root. If the file doesn't exist, defaults are used.

### Example config.yaml

```yaml
delays:
  min_delay: 2.0    # Increase delay between requests
  max_delay: 5.0

http:
  timeout: 60       # Longer timeout for slow connections

logging:
  level: DEBUG      # More verbose logging
```

### Available Settings

- `urls.base_url` - Base URL for the website
- `http.timeout` - Request timeout in seconds
- `http.verify_ssl` - Whether to verify SSL certificates
- `delays.min_delay`, `delays.max_delay` - Random delay range between requests
- `retry.max_retries` - Number of retry attempts
- `concurrency.max_workers` - Maximum concurrent workers
- `logging.level` - Log level (DEBUG, INFO, WARNING, ERROR)

### PDF Conversion Backend

The scraper supports two PDF conversion backends:
- **wkhtmltopdf** (default) - Easier to install, bundled in standalone builds
- **WeasyPrint** - Better CSS support, requires GTK libraries

Configure in `config.yaml`:
```yaml
pdf:
  backend: "auto"  # or "weasyprint" / "wkhtmltopdf"
```

---

## Project Structure

```
jamabandi-scraper/
├── run.py                          # Entry point (launches the GUI)
├── requirements.txt                # Python dependencies
├── Install Dependencies.command    # Mac installer (double-click)
├── Install Dependencies.cmd        # Windows installer (double-click)
├── Jamabandi Scraper.command       # Mac launcher (double-click)
├── Jamabandi Scraper.cmd           # Windows launcher (double-click)
└── scraper/
    ├── gui.py                      # GUI application
    ├── http_scraper.py             # HTTP-based scraper
    ├── pdf_converter.py            # HTML to PDF converter
    └── selenium_scraper.py         # Selenium-based scraper (legacy)
```

---

## Running from Terminal (Advanced)

If you prefer the command line over the GUI:

```bash
# Activate the virtual environment
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# Launch the GUI
python run.py

# Or run the scraper directly
python scraper/http_scraper.py --cookie YOUR_COOKIE --start 1 --end 100

# Convert HTML to PDF manually
python scraper/pdf_converter.py --input downloads_05464 --workers 4 --delete-html
```

---

## Requirements

- Python 3.10 or newer
- tkinter (usually included with Python; on Mac: `brew install python-tk`)
- Internet connection to access jamabandi.nic.in
- A valid login session on the Jamabandi website

## Installation Options

### Option 1: Standalone Installer (Recommended)

Download the latest release for your platform:
- **Windows:** `JamabandiScraper.exe` - Double-click to run
- **macOS:** `JamabandiScraper.dmg` - Open and drag to Applications

No Python installation required!

### Option 2: Run from Source

If you prefer to run from source code:
1. Install Python 3.10+
2. Clone the repository
3. Run the installer script (see Quick Start)
