from setuptools import find_packages, setup

setup(
    name="refly",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Refly: A tool to fetch research papers from BibTeX entries",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/refly",
    packages=find_packages(),
    install_requires=[
        "arxiv",
        "bibtexparser",
        "scidownl",
        "tqdm",
    ],
    entry_points={
        "console_scripts": [
            "refly=refly:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
