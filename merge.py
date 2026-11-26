"""Merge individual PDF page files into a single PDF.

Can be used as a library (merge_pdfs) or standalone CLI:

    python merge.py <cache_dir>
"""

import glob
import os
import sys

from PyPDF2 import PdfReader, PdfWriter


def merge_pdfs(pdf_files, out_pdf, log=print):
    """Merge *pdf_files* (list of paths) into *out_pdf*.

    Uses PdfWriter + PdfReader so each file handle is released after reading,
    avoiding 'Too many open files' errors on large books.
    """
    log(f'Merging {len(pdf_files)} PDF pages...')

    writer = PdfWriter()
    for i, path in enumerate(pdf_files, 1):
        with open(path, 'rb') as source:
            reader = PdfReader(source)
            for page in reader.pages:
                writer.add_page(page)
            # PyPDF2 keys its cloning cache by id(reader). Once readers are
            # collected, Python can reuse their IDs for unrelated PDFs, causing
            # fonts and page streams to point at objects from an earlier input.
            writer.reset_translation(reader)
        if i % 10 == 0 or i == len(pdf_files):
            log(f'  processed {i}/{len(pdf_files)}')

    log(f'Writing {out_pdf}...')
    with open(out_pdf, 'wb') as f:
        writer.write(f)

    log(f'Done: {out_pdf}  ({len(pdf_files)} pages)')


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python merge.py <cache_dir>")

    cache_dir = sys.argv[1]
    out_pdf = f"{os.path.basename(cache_dir.rstrip('/'))}.pdf"

    pdf_files = sorted(glob.glob(os.path.join(cache_dir, "*.pdf")))
    if not pdf_files:
        sys.exit(f"No PDF files found in {cache_dir}")

    merge_pdfs(pdf_files, out_pdf)


if __name__ == "__main__":
    main()
