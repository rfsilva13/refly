# Refly

Refly is a lightweight command-line tool that extracts research paper details from BibTeX entries and downloads the corresponding PDFs from arXiv or Sci-Hub. Each paper is saved using a standardized filename based on the first author's last name, publication year, and title. Duplicate downloads are automatically avoided.

## Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/yourusername/refly.git
cd refly
pip install -r requirements.txt
```

Alternatively, install the dependencies manually:

```bash
pip install arxiv bibtexparser scidownl tqdm
```

## Usage

Run Refly from the command line. For example, to process a single BibTeX file:

```bash
python refly.py -b path/to/your.bib -o papers
```

Or to process all BibTeX files in a folder:

```bash
python refly.py -f path/to/bibtex_folder -o papers
```

## Dependencies

- Python 3.6+
- [arxiv](https://pypi.org/project/arxiv/)
- [bibtexparser](https://pypi.org/project/bibtexparser/)
- [scidownl](https://pypi.org/project/scidownl/)
- [tqdm](https://pypi.org/project/tqdm/)

## License

This project is licensed under the MIT License.
