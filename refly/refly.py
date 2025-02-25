#!/usr/bin/env python3
"""
Refly

Refly extracts research paper details from BibTeX entries and downloads the corresponding PDFs.
It attempts downloads in the following order:
  1. Unpaywall (using unpywall; requires an email address)
  2. arXiv (querying by title and first author with fuzzy matching)
  3. Sci-Hub

If none succeed, the paper's DOI and title are logged to 'failed_downloads.log'.

Usage:
    python refly.py -b <bibtex_file> -o <output_directory> [--unpaywall-email your.email@example.com]
    python refly.py -f <folder_with_bibtex_files> -o <output_directory> [--unpaywall-email your.email@example.com]
"""

import argparse
import logging
import os
import re
import sys
from typing import Dict, List

import arxiv
import bibtexparser
import requests
import scidownl
from rapidfuzz import fuzz
from tqdm import tqdm

# Configure logging for clear terminal output.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def parse_bibtex(bibtex_file: str) -> List[Dict]:
    """Parse a BibTeX file and return its entries."""
    with open(bibtex_file, "r", encoding="utf-8") as f:
        bib_database = bibtexparser.load(f)
    return bib_database.entries


def sanitize_filename(filename: str) -> str:
    """Sanitize a string for safe filename usage."""
    filename = filename.replace(" ", "_")
    filename = re.sub(r"[^\w\-_\.]", "", filename)
    return filename


def generate_filename(entry: Dict) -> str:
    """
    Generate a standardized filename based on the first author's last name, year, and title.
    """
    author_field = entry.get("author", "Unknown")
    first_author = author_field.split(" and ")[0].strip()
    if "," in first_author:
        first_author = first_author.split(",")[0].strip()
    else:
        first_author = first_author.split()[-1].strip()
    year = entry.get("year", "Unknown")
    title = entry.get("title", "Untitled")
    filename = f"{first_author}_{year}_{title}.pdf"
    return sanitize_filename(filename)


def paper_exists(filename: str, output_dir: str) -> bool:
    """Check if the paper already exists in the output directory."""
    return os.path.exists(os.path.join(output_dir, filename))


def extract_arxiv_id(url: str) -> str:
    """Extract arXiv ID from a URL if possible."""
    if not url:
        return ""

    # Match new style IDs (YYMM.number)
    pattern1 = r"arxiv\.org/abs/(\d{4}\.\d+(?:v\d+)?)"
    match = re.search(pattern1, url)
    if match:
        return match.group(1)

    # Match old style IDs (category/YYMMNNN)
    pattern2 = r"arxiv\.org/abs/([a-zA-Z\-]+/\d{7}(?:v\d+)?)"
    match = re.search(pattern2, url)
    if match:
        return match.group(1)

    return ""


def extract_doi(entry: Dict) -> str:
    """
    Extract DOI from a BibTeX entry. Check both 'doi' and 'url' fields.
    """
    # First, check if 'doi' field exists
    doi = entry.get("doi", "").strip()
    if doi:
        # If DOI is already in the format 10.xxxx/xxxx, return it
        if re.match(r"10\.\d{4,}/.+", doi):
            return doi

        # If DOI is a URL, extract the DOI part
        doi_match = re.search(r"(?:doi\.org/|doi:)(.+)", doi)
        if doi_match:
            return doi_match.group(1)

    # If 'doi' field doesn't exist or couldn't extract DOI, check 'url' field
    url = entry.get("url", "").strip()
    if url:
        # Check if URL contains a DOI
        doi_match = re.search(r"(?:doi\.org/|doi:)(.+)", url)
        if doi_match:
            return doi_match.group(1)

    # If no DOI found, return empty string
    return ""


def unpaywall_download(entry: Dict, output_dir: str, filename: str) -> bool:
    """
    Try to download a PDF using Unpaywall via unpywall.
    Returns True if successful, False otherwise.
    """
    doi = extract_doi(entry)
    if not doi:
        logging.info("No DOI found for Unpaywall download")
        return False

    try:
        from unpywall import Unpywall
    except ImportError:
        logging.error(
            "Unpywall client not installed. Install it via: pip install unpywall"
        )
        return False

    try:
        pdf_url = Unpywall.get_pdf_link(doi=doi)
        if pdf_url:
            logging.info(f"Attempting Unpaywall download for DOI {doi} from {pdf_url}")
            headers = {
                "User-Agent": "Refly/1.0 (+https://github.com/yourusername/refly)"
            }
            pdf_response = requests.get(
                pdf_url, stream=True, timeout=20, headers=headers
            )
            if pdf_response.status_code == 200:
                with open(os.path.join(output_dir, filename), "wb") as f:
                    for chunk in pdf_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logging.info(f"Downloaded via Unpaywall: {doi}")
                return True
            else:
                logging.error(
                    f"Failed to download PDF from {pdf_url}, status code {pdf_response.status_code}"
                )
        else:
            logging.info(f"No PDF URL found via Unpywall for DOI {doi}")
        return False
    except Exception as e:
        logging.error(f"Unpaywall download error for DOI {doi}: {e}")
        return False


def arxiv_download(entry: Dict, output_dir: str, filename: str) -> bool:
    """
    Try to download the paper from arXiv. First attempt to use arXiv ID if the URL contains it,
    otherwise query using title and first author with fuzzy matching.

    Returns True if successful, False otherwise.
    """
    try:
        # First, check if the URL contains an arXiv ID
        url = entry.get("url", "")
        arxiv_id = extract_arxiv_id(url)

        if arxiv_id:
            logging.info(f"Found arXiv ID in URL: {arxiv_id}")
            try:
                # Try to query arXiv using the ID
                search = arxiv.Search(id_list=[arxiv_id])
                results = list(search.results())
                if results:
                    candidate = results[0]
                    logging.info(
                        f"Found paper on arXiv with ID {arxiv_id}: {candidate.title}"
                    )
                    try:
                        candidate.download_pdf(dirpath=output_dir, filename=filename)
                    except TypeError:
                        candidate.download_pdf(dirpath=output_dir)
                        default_path = os.path.join(
                            output_dir, f"{candidate.get_short_id()}.pdf"
                        )
                        new_path = os.path.join(output_dir, filename)
                        if os.path.exists(default_path):
                            os.rename(default_path, new_path)
                    logging.info(f"Downloaded via arXiv ID: {arxiv_id}")
                    return True
                else:
                    logging.info(f"No arXiv paper found with ID {arxiv_id}")
            except Exception as e:
                logging.error(f"Error when querying arXiv with ID {arxiv_id}: {e}")
        else:
            logging.info("No arXiv ID found in URL")

        # If no arXiv ID found in URL or download failed, continue with title and author search
        title = entry.get("title", "").strip()
        author_field = entry.get("author", "Unknown").strip()
        first_author = author_field.split(" and ")[0].strip()

        # Use a more forgiving query on arXiv - use 'all' instead of 'ti'
        query = f'all:"{title}" OR au:"{first_author}"'
        logging.info(f"Querying arXiv with: {query}")

        try:
            search = arxiv.Search(query=query, max_results=10)
            results = list(search.results())

            logging.info(f"Found {len(results)} results from arXiv search")

            if not results:
                logging.info(
                    f"No arXiv results found for title '{title}' or author '{first_author}'"
                )
                return False

            # Print details about each result for debugging
            for i, result in enumerate(results):
                logging.debug(f"Result {i+1}:")
                logging.debug(f"  Title: {result.title}")
                logging.debug(
                    f"  Authors: {', '.join(str(author) for author in result.authors)}"
                )
                logging.debug(f"  Published: {result.published}")
                logging.debug(f"  ID: {result.get_short_id()}")

            best_candidate = None
            best_score = 0
            # Evaluate candidates using fuzzy matching on title and first author.
            for candidate in results:
                candidate_title = candidate.title.strip() if candidate.title else ""
                candidate_first_author = (
                    str(candidate.authors[0]).strip()
                    if candidate.authors and len(candidate.authors) > 0
                    else ""
                )
                title_score = fuzz.ratio(title.lower(), candidate_title.lower())
                author_score = (
                    fuzz.ratio(first_author.lower(), candidate_first_author.lower())
                    if candidate_first_author
                    else 0
                )
                score = (title_score + author_score) / 2
                logging.info(
                    f"Candidate: '{candidate_title}' by '{candidate_first_author}', title_score: {title_score}, author_score: {author_score}, combined: {score}"
                )
                if score > best_score:
                    best_score = score
                    best_candidate = candidate

            if best_candidate is None:
                logging.info("No suitable candidate found on arXiv")
                return False

            # Define a threshold below which we do not consider a candidate a match.
            threshold = 60
            if best_score < threshold:
                logging.info(
                    f"Best candidate score {best_score} is below threshold {threshold}"
                )
                return False

            logging.info(
                f"Best candidate: '{best_candidate.title}' with score {best_score}"
            )
            try:
                best_candidate.download_pdf(dirpath=output_dir, filename=filename)
            except TypeError as te:
                logging.error(f"TypeError when downloading PDF: {te}")
                try:
                    logging.info("Trying alternative download method...")
                    best_candidate.download_pdf(dirpath=output_dir)
                    default_path = os.path.join(
                        output_dir, f"{best_candidate.get_short_id()}.pdf"
                    )
                    new_path = os.path.join(output_dir, filename)
                    if os.path.exists(default_path):
                        os.rename(default_path, new_path)
                        logging.info(f"Successfully renamed file to {filename}")
                except Exception as e2:
                    logging.error(f"Alternative download method also failed: {e2}")
                    return False
            logging.info(f"Downloaded via arXiv: '{best_candidate.title}'")
            return True
        except Exception as e:
            logging.error(f"Error during arXiv search or download: {e}")
            return False

    except Exception as e:
        logging.error(f"arXiv download error: {e}")
        return False


def scidownl_download(entry: Dict, output_dir: str, filename: str) -> bool:
    """
    Try to download the paper from Sci-Hub.
    Returns True if successful, False otherwise.
    """
    doi = extract_doi(entry)
    if not doi:
        logging.info("No DOI found for Sci-Hub download")
        return False

    try:
        out_path = os.path.join(output_dir, filename)
        logging.info(f"Attempting Sci-Hub download for DOI {doi}")
        scidownl.scihub_download(doi, paper_type="doi", out=out_path)
        logging.info(f"Downloaded via Sci-Hub: {doi}")
        return True
    except SystemExit as e:
        logging.error(f"Sci-Hub download caused SystemExit for DOI {doi}: {e}")
        return False
    except Exception as e:
        logging.error(f"Sci-Hub download error for DOI {doi}: {e}")
        return False


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    if len(sys.argv) == 1:
        sys.argv.append("-h")
    parser = argparse.ArgumentParser(
        description="Refly: Fetch research papers from BibTeX entries"
    )
    parser.add_argument("-b", "--bibtex", help="Path to a BibTeX file")
    parser.add_argument(
        "-f", "--folder", help="Path to a folder containing BibTeX files"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory for downloaded papers",
        default="papers",
    )
    parser.add_argument(
        "--unpaywall-email",
        help="Email address for Unpaywall API (or set UNPAYWALL_EMAIL env var)",
        default="",
    )
    return parser.parse_args()


def process_entries(entries: List[Dict], output_dir: str, unpaywall_email: str) -> None:
    """
    Process each BibTeX entry:
      1. Try Unpaywall.
      2. Try arXiv (using ID if available, otherwise fuzzy matching on title and first author).
      3. Try Sci-Hub.

    Log any failures to 'failed_downloads.log'.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logging.info(f"Created output directory: {output_dir}")

    failed_log_path = os.path.join(output_dir, "failed_downloads.log")
    for entry in tqdm(entries, desc="Downloading papers", unit="paper"):
        filename = generate_filename(entry)
        if paper_exists(filename, output_dir):
            logging.info(f"Paper '{filename}' already exists. Skipping.")
            continue

        doi = extract_doi(entry)
        success = False

        # Set UNPAYWALL_EMAIL if provided.
        if unpaywall_email:
            os.environ["UNPAYWALL_EMAIL"] = unpaywall_email

        # 1. Try Unpaywall.
        success = unpaywall_download(entry, output_dir, filename)

        # 2. If Unpaywall fails, try arXiv (using ID if available).
        if not success:
            success = arxiv_download(entry, output_dir, filename)

        # 3. If still unsuccessful, try Sci-Hub.
        if not success:
            success = scidownl_download(entry, output_dir, filename)

        # 4. Log failures.
        if not success:
            failure_info = f"{doi or 'No DOI'} - {entry.get('title', 'No Title')}"
            logging.error(f"Failed to download paper: {failure_info}")
            with open(failed_log_path, "a") as log_file:
                log_file.write(f"{failure_info}\n")


def main() -> int:
    """Main function to process BibTeX entries and download papers."""
    logging.info("Welcome to Refly!")
    args = parse_args()

    # Prompt for Unpaywall email if not provided.
    if not args.unpaywall_email:
        email = input(
            "Enter your Unpaywall email (required for API access, or leave blank to skip Unpaywall): "
        ).strip()
        args.unpaywall_email = email

    # Process folder containing multiple BibTeX files.
    if args.folder:
        for file in os.listdir(args.folder):
            if file.endswith(".bib"):
                bib_path = os.path.join(args.folder, file)
                logging.info(f"Processing BibTeX file: {bib_path}")
                try:
                    entries = parse_bibtex(bib_path)
                    process_entries(entries, args.output, args.unpaywall_email)
                except Exception as e:
                    logging.error(f"Error processing file '{bib_path}': {e}")
        return 0

    # Process a single BibTeX file.
    if args.bibtex:
        logging.info(f"Processing BibTeX file: {args.bibtex}")
        try:
            entries = parse_bibtex(args.bibtex)
            process_entries(entries, args.output, args.unpaywall_email)
        except Exception as e:
            logging.error(f"Error processing file '{args.bibtex}': {e}")
            return 1
        return 0

    logging.error(
        "Error: Please specify a BibTeX file or a folder containing BibTeX files."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
