#!/usr/bin/env python
"""
Refly

Refly is a command-line tool that extracts research paper information from BibTeX entries and
downloads the corresponding PDFs from arXiv or Sci-Hub. It saves each paper using a standardized
filename derived from the first author's last name, publication year, and title, while avoiding
duplicate downloads.

Usage:
    python refly.py -b <bibtex_file> -o <output_directory>
    python refly.py -f <folder_with_bibtex_files> -o <output_directory>

Dependencies:
    pip install arxiv bibtexparser scidownl tqdm
"""

import argparse
import logging
import os
import re
import sys
from typing import Dict, List

import arxiv
import bibtexparser
import scidownl
from tqdm import tqdm

# Configure logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def parse_bibtex(bibtex_file: str) -> List[Dict]:
    """
    Parse a BibTeX file and return its entries.

    Parameters:
        bibtex_file (str): Path to the BibTeX file.

    Returns:
        List[Dict]: A list of BibTeX entries.
    """
    with open(bibtex_file, "r", encoding="utf-8") as f:
        bib_database = bibtexparser.load(f)
    return bib_database.entries


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a string for safe filename usage.

    Replaces spaces with underscores and removes non-alphanumeric characters except underscores,
    hyphens, and periods.

    Parameters:
        filename (str): The raw filename.

    Returns:
        str: A sanitized filename.
    """
    filename = filename.replace(" ", "_")
    filename = re.sub(r"[^\w\-_\.]", "", filename)
    return filename


def generate_filename(entry: Dict) -> str:
    """
    Generate a standardized filename based on the first author's last name, publication year, and title.

    Parameters:
        entry (Dict): A BibTeX entry expected to contain 'author', 'year', and 'title'.

    Returns:
        str: A sanitized filename in the format 'LastName_Year_Title.pdf'.
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
    """
    Check if a paper with the given filename already exists in the output directory.

    Parameters:
        filename (str): The standardized filename.
        output_dir (str): Directory where papers are stored.

    Returns:
        bool: True if the file exists, False otherwise.
    """
    return os.path.exists(os.path.join(output_dir, filename))


def arxiv_download(entry: Dict, output_dir: str, filename: str) -> None:
    """
    Download a paper from arXiv based on the DOI in the entry and save it with a custom filename.

    Parameters:
        entry (Dict): A BibTeX entry containing the 'url' field with the arXiv DOI.
        output_dir (str): Directory where the PDF will be saved.
        filename (str): The standardized filename for the paper.
    """
    doi = entry["url"]
    logging.info(f"Processing arXiv paper with DOI: {doi}")
    try:
        arxiv_id = doi.split("/")[-1]
        logging.info(f"Downloading paper with arXiv ID: {arxiv_id}")
        paper = next(arxiv.Client().results(arxiv.Search(id_list=[arxiv_id])))
        try:
            paper.download_pdf(dirpath=output_dir, filename=filename)
        except TypeError:
            paper.download_pdf(dirpath=output_dir)
            default_path = os.path.join(output_dir, f"{arxiv_id}.pdf")
            new_path = os.path.join(output_dir, filename)
            if os.path.exists(default_path):
                os.rename(default_path, new_path)
        logging.info(f"Downloaded and saved as: {filename}")
    except Exception as e:
        logging.error(f"Error downloading arXiv paper: {e}")


def scidownl_download(entry: Dict, output_dir: str, filename: str) -> None:
    """
    Download a paper from Sci-Hub using its DOI and save it with a custom filename.

    Parameters:
        entry (Dict): A BibTeX entry containing the 'url' field with the paper DOI.
        output_dir (str): Directory where the PDF will be saved.
        filename (str): The standardized filename for the paper.
    """
    doi = entry["url"]
    logging.info(f"Processing Sci-Hub paper with DOI: {doi}")
    out_path = os.path.join(output_dir, filename)
    try:
        scidownl.scihub_download(doi, paper_type="doi", out=out_path)
        logging.info(f"Downloaded and saved as: {filename}")
    except Exception as e:
        logging.error(f"Error downloading Sci-Hub paper: {e}")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    if len(sys.argv) == 1:
        sys.argv.append("-h")
    parser = argparse.ArgumentParser(
        description="Refly: Fetch research papers from BibTeX entries"
    )
    parser.add_argument("-b", "--bibtex", help="Path to a BibTeX file")
    parser.add_argument(
        "-f", "--folder", help="Path to a folder containing BibTeX files"
    )
    parser.add_argument("-o", "--output", help="Output directory for downloaded papers")
    return parser.parse_args()


def process_entries(entries: List[Dict], output_dir: str) -> None:
    """
    Process BibTeX entries and download papers if they don't already exist.

    Parameters:
        entries (List[Dict]): List of BibTeX entries.
        output_dir (str): Directory where the papers will be stored.
    """
    for entry in tqdm(entries, desc="Downloading papers", unit="paper"):
        filename = generate_filename(entry)
        if paper_exists(filename, output_dir):
            logging.info(f"Paper '{filename}' already exists. Skipping.")
            continue

        doi = entry.get("url", "")
        if re.search("arxiv", doi, re.IGNORECASE):
            arxiv_download(entry, output_dir, filename)
        else:
            scidownl_download(entry, output_dir, filename)


def main() -> int:
    """
    Main function to extract and download papers based on BibTeX entries.

    Returns:
        int: Exit status code (0 for success, 1 for error).
    """
    logging.info("Welcome to Refly!")
    args = parse_args()
    output_dir = args.output if args.output else "papers"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logging.info(f"Created output directory: {output_dir}")

    if args.folder:
        folder = args.folder
        bib_files = [f for f in os.listdir(folder) if f.endswith(".bib")]
        if not bib_files:
            logging.error("No BibTeX files found in the specified folder.")
            return 1
        for file in bib_files:
            bib_path = os.path.join(folder, file)
            logging.info(f"Processing BibTeX file: {bib_path}")
            try:
                entries = parse_bibtex(bib_path)
                process_entries(entries, output_dir)
            except Exception as e:
                logging.error(f"Error processing file '{bib_path}': {e}")
        return 0

    if args.bibtex:
        bib_file = args.bibtex
        logging.info(f"Processing BibTeX file: {bib_file}")
        try:
            entries = parse_bibtex(bib_file)
            process_entries(entries, output_dir)
        except Exception as e:
            logging.error(f"Error processing file '{bib_file}': {e}")
            return 1
        return 0

    logging.error(
        "Error: Please specify a BibTeX file or a folder containing BibTeX files."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
