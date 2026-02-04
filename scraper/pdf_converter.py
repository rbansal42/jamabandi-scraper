#!/usr/bin/env python3
"""
Convert Nakal HTML files to PDF using WeasyPrint.

Features:
- Removes print-blocking CSS
- Cleans up HTML for better PDF output
- Processes all HTML files in downloads/ folder
- Shows progress
- Parallel processing with batch splitting across multiple workers

Usage:
    python convert_to_pdf.py
    python convert_to_pdf.py --input downloads/ --output pdfs/
    python convert_to_pdf.py --workers 8 --skip-existing
"""

import argparse
import multiprocessing
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Dict, Any

from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration


# Custom CSS to override print-blocking styles and improve PDF output.
# Landscape A4 gives ~277mm usable width for the 12-column Jamabandi table.
CUSTOM_CSS = """
@page {
    size: A4 landscape;
    margin: 0.6cm;
}

/* Override the print-blocking CSS */
@media print {
    html, body {
        display: block !important;
        visibility: visible !important;
    }
}

/* Force everything to be visible */
html, body {
    display: block !important;
    visibility: visible !important;
    margin: 0;
    padding: 0;
}

/* ── Table rendering ─────────────────────────────────────── */
table {
    width: 100% !important;
    border-collapse: collapse;
    font-size: 7.5pt;
    table-layout: fixed;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

th, td {
    border: 1px solid #333;
    padding: 2px 3px;
    overflow: hidden;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

th {
    font-size: 7pt;
    background-color: #eee;
}

/* Strip any leftover inline widths the source HTML sets on spans */
span[style] {
    width: auto !important;
    max-width: 100% !important;
    position: static !important;
}

/* Hide unnecessary elements */
.btn_login, .header_43, form > div:first-child {
    display: none !important;
}

/* Remove any scripts display */
script {
    display: none !important;
}

/* Hide header/nav/button rows */
#btnLogout, #btnGetVirifiableNakal, #dvlang {
    display: none !important;
}
"""

# Shared counter for cross-process progress tracking
_shared_counter = None
_total_files = None
_delete_html = False


def _init_worker(counter, total, delete_html):
    """Initializer for each worker process to set up shared state."""
    global _shared_counter, _total_files, _delete_html
    _shared_counter = counter
    _total_files = total
    _delete_html = delete_html


def clean_html(html_content: str) -> str:
    """
    Clean HTML content for better PDF conversion.
    - Remove print-blocking CSS
    - Remove JavaScript
    - Strip inline width / position styles that cause clipping
    - Remove external stylesheets (we supply our own)
    """
    # Remove the @media print block that hides content
    html_content = re.sub(
        r"@media\s+print\s*\{[^}]*display\s*:\s*none[^}]*\}",
        "",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove all script tags
    html_content = re.sub(
        r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL
    )

    # Remove external CSS links (we'll use our own styling)
    html_content = re.sub(
        r"<link[^>]*stylesheet[^>]*>", "", html_content, flags=re.IGNORECASE
    )

    # Remove form elements that might cause issues
    html_content = re.sub(
        r'<input[^>]*type=["\']hidden["\'][^>]*>', "", html_content, flags=re.IGNORECASE
    )

    # ── Strip inline widths from <td> and <span> that force fixed pixel sizes ──
    # e.g. style="width: 82px; height: 21px"  ->  style="height: 21px"
    # e.g. style="display:inline-block;width:200px;"  ->  style="display:inline-block;"
    html_content = re.sub(
        r"width\s*:\s*\d+px\s*;?\s*", "", html_content, flags=re.IGNORECASE
    )

    # Strip position: relative/static with left/top offsets that shift content
    html_content = re.sub(
        r"position\s*:\s*(?:relative|static)\s*;?\s*",
        "",
        html_content,
        flags=re.IGNORECASE,
    )
    html_content = re.sub(
        r"(?:left|top)\s*:\s*-?\d+px\s*;?\s*", "", html_content, flags=re.IGNORECASE
    )

    return html_content


def convert_html_to_pdf(html_path: Path, pdf_path: Path) -> bool:
    """
    Convert a single HTML file to PDF.
    Returns True if successful.
    """
    try:
        # Read HTML content
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Clean the HTML
        html_content = clean_html(html_content)

        # Configure fonts
        font_config = FontConfiguration()

        # Create HTML object
        # Use as_posix() so Windows backslashes don't break URL resolution
        html_doc = HTML(string=html_content, base_url=html_path.parent.as_posix())

        # Create custom CSS
        css = CSS(string=CUSTOM_CSS, font_config=font_config)

        # Generate PDF
        html_doc.write_pdf(pdf_path, stylesheets=[css], font_config=font_config)

        return True

    except Exception as e:
        print(f"    Error: {e}")
        return False


def process_batch(
    worker_id: int,
    file_pairs: List[Tuple[str, str]],
) -> Dict[str, Any]:
    """
    Worker function that processes a batch of (html_path, pdf_path) pairs.

    This runs in a separate process. Each worker processes its batch sequentially
    and reports results back.

    Args:
        worker_id: Identifier for this worker.
        file_pairs: List of (html_path_str, pdf_path_str) tuples to process.

    Returns:
        Dict with worker_id, success_count, fail_count, failed_files.
    """
    global _shared_counter, _total_files, _delete_html

    success_count = 0
    fail_count = 0
    failed_files = []

    for html_path_str, pdf_path_str in file_pairs:
        html_path = Path(html_path_str)
        pdf_path = Path(pdf_path_str)

        ok = convert_html_to_pdf(html_path, pdf_path)

        if ok:
            try:
                file_size = pdf_path.stat().st_size
                print(
                    f"  [Worker {worker_id}] Converted {html_path.name} "
                    f"-> {pdf_path.name} ({file_size:,} bytes)"
                )
            except OSError:
                print(
                    f"  [Worker {worker_id}] Converted {html_path.name} "
                    f"-> {pdf_path.name}"
                )
            success_count += 1

            # Delete the source HTML after successful conversion
            if _delete_html:
                try:
                    html_path.unlink()
                except OSError as e:
                    print(
                        f"  [Worker {worker_id}] Warning: could not delete {html_path.name}: {e}"
                    )
        else:
            print(f"  [Worker {worker_id}] FAILED {html_path.name}")
            fail_count += 1
            failed_files.append(html_path_str)

        # Update shared progress counter
        if _shared_counter is not None:
            with _shared_counter.get_lock():
                _shared_counter.value += 1
                completed = _shared_counter.value
            total = _total_files.value if _total_files is not None else 0
            if total > 0:
                pct = (completed / total) * 100
                print(
                    f"  [Progress] {completed}/{total} files completed ({pct:.1f}%)",
                    flush=True,
                )

    return {
        "worker_id": worker_id,
        "success_count": success_count,
        "fail_count": fail_count,
        "failed_files": failed_files,
    }


def split_into_batches(items: list, num_batches: int) -> List[list]:
    """
    Split a list into N roughly-equal batches using chunk-based splitting.

    Args:
        items: The list to split.
        num_batches: Number of batches to create.

    Returns:
        List of sublists (batches). Some may be empty if num_batches > len(items).
    """
    if num_batches <= 0:
        return [items]

    batches = [[] for _ in range(num_batches)]
    for idx, item in enumerate(items):
        batches[idx % num_batches].append(item)

    return batches


def main():
    parser = argparse.ArgumentParser(description="Convert Nakal HTML files to PDF")
    parser.add_argument(
        "--input",
        "-i",
        default="downloads",
        help="Input directory containing HTML files (default: downloads)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output directory for PDFs (default: same as input)",
    )
    parser.add_argument(
        "--file", "-f", default=None, help="Convert a single file instead of all files"
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=False,
        help="Skip HTML files that already have a corresponding PDF in the output dir",
    )
    parser.add_argument(
        "--delete-html",
        action="store_true",
        default=False,
        help="Delete each HTML file after it has been successfully converted to PDF",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else input_dir

    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get list of HTML files
    if args.file:
        html_files = sorted([Path(args.file)])
    else:
        html_files = sorted(input_dir.glob("nakal_khewat_*.html"))

    if not html_files:
        print(f"No HTML files found in {input_dir}")
        return

    # Build (html_path, pdf_path) pairs
    file_pairs = []
    skipped_count = 0
    for html_path in html_files:
        pdf_name = html_path.stem + ".pdf"
        pdf_path = output_dir / pdf_name

        if args.skip_existing and pdf_path.exists():
            skipped_count += 1
            continue

        file_pairs.append((str(html_path), str(pdf_path)))

    if skipped_count > 0:
        print(f"Skipped {skipped_count} files with existing PDFs (--skip-existing)")

    if not file_pairs:
        print("No files to convert after filtering.")
        return

    total_files = len(file_pairs)
    num_workers = min(args.workers, total_files)  # No more workers than files

    print(f"Converting {total_files} HTML files to PDF...")
    print(f"Output directory: {output_dir}")
    print(f"Workers: {num_workers}")
    print()

    # Split into batches (one per worker)
    batches = split_into_batches(file_pairs, num_workers)

    # Print batch assignments
    print("Batch assignments:")
    print("-" * 50)
    for batch_idx, batch in enumerate(batches):
        if not batch:
            continue
        file_names = [Path(hp).name for hp, _ in batch]
        print(f"  Worker {batch_idx}: {len(batch)} files")
        for name in file_names:
            print(f"    - {name}")
    print("-" * 50)
    print()

    # Set up shared multiprocessing counter for progress
    shared_counter = multiprocessing.Value("i", 0)
    shared_total = multiprocessing.Value("i", total_files)
    delete_html = args.delete_html

    if delete_html:
        print("HTML files will be DELETED after successful conversion.")
        print()

    start_time = time.time()

    # Launch workers using ProcessPoolExecutor
    results = []
    with ProcessPoolExecutor(
        max_workers=num_workers,
        initializer=_init_worker,
        initargs=(shared_counter, shared_total, delete_html),
    ) as executor:
        futures = {}
        for worker_id, batch in enumerate(batches):
            if not batch:
                continue
            future = executor.submit(process_batch, worker_id, batch)
            futures[future] = worker_id

        # Wait for all futures and collect results
        for future in as_completed(futures):
            worker_id = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"  [Worker {worker_id}] crashed with exception: {e}")
                results.append(
                    {
                        "worker_id": worker_id,
                        "success_count": 0,
                        "fail_count": 0,
                        "failed_files": [],
                    }
                )

    elapsed = time.time() - start_time

    # Sort results by worker_id for consistent reporting
    results.sort(key=lambda r: r["worker_id"])

    # Print final summary
    print()
    print("=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    print(f"Total time: {elapsed:.1f}s")
    print()

    total_success = 0
    total_fail = 0
    all_failed_files = []

    print("Per-worker results:")
    print("-" * 40)
    for r in results:
        wid = r["worker_id"]
        sc = r["success_count"]
        fc = r["fail_count"]
        total_success += sc
        total_fail += fc
        all_failed_files.extend(r["failed_files"])
        status = "OK" if fc == 0 else f"{fc} FAILED"
        print(f"  Worker {wid}: {sc} succeeded, {fc} failed  [{status}]")

    print("-" * 40)
    print(f"Total: {total_success} succeeded, {total_fail} failed out of {total_files}")
    if skipped_count > 0:
        print(f"Skipped (existing): {skipped_count}")
    if delete_html:
        print(f"Deleted {total_success} source HTML files.")
    print(f"PDFs saved to: {output_dir}")

    if all_failed_files:
        print()
        print("Failed files:")
        for fp in all_failed_files:
            print(f"  - {fp}")

    # Exit with error code if any failures
    if total_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
