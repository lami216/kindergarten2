"""Render real synthetic receipt PDFs using an explicit CI-only dependency."""
from pathlib import Path
import pypdfium2 as pdfium


def main():
    documents=sorted(Path('visual-evidence/receipt-contract').glob('*.pdf'))
    if not documents:
        raise RuntimeError('No synthetic receipt PDFs were produced by acceptance tests')
    for path in documents:
        with pdfium.PdfDocument(path) as document:
            if not len(document):
                raise RuntimeError(f'Empty receipt PDF: {path.name}')
            page=document[0]
            bitmap=page.render(scale=110/72)
            bitmap.to_pil().save(path.with_suffix('.png'))
            bitmap.close()
            page.close()
    print(f'Rendered {len(documents)} actual synthetic receipt PDFs')


if __name__=='__main__':
    main()
