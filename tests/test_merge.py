import gc
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import DecodedStreamObject, DictionaryObject, NameObject

import merge


def make_page(path, number):
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    page = writer.pages[0]
    # Vary object numbering so a stale cloning map also mixes fonts and streams.
    for _ in range(number % 7):
        writer._add_object(DictionaryObject())
    font = writer._add_object(DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    }))
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 12 Tf 20 300 Td (Source page {number:03d}) Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    with path.open('wb') as output:
        writer.write(output)


class MergeTests(unittest.TestCase):
    def test_many_independent_inputs_preserve_content_fonts_and_order(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = []
            for number in range(120):
                path = root / f'{number}.pdf'
                make_page(path, number)
                files.append(str(path))

            def read_with_collection(source):
                gc.collect()
                return PdfReader(source)

            output = root / 'merged.pdf'
            with patch.object(merge, 'PdfReader', side_effect=read_with_collection):
                merge.merge_pdfs(files, str(output), log=lambda _: None)
            reader = PdfReader(output)
            self.assertEqual(len(reader.pages), 120)
            for number, page in enumerate(reader.pages):
                self.assertEqual(page.extract_text(), f'Source page {number:03d}')
                self.assertEqual(page['/Resources']['/Font']['/F1']['/Type'], '/Font')





if __name__ == '__main__':
    unittest.main()
