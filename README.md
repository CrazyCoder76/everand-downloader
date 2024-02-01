# scribd-downloader
Download your books from Everand in PDF format for personal and offline use.

### Please note:
Only everand **eBooks** are supported for now (no PDF Documents/Ebooks etc.)

## Installation

Install the required Python libraries:

  >$ pip install PyPDF2

Install Playwright for Python:
  
  >$ pip install playwright
  
  >$ playwright install

1) Run the script:

>$ python3 run.py [BOOK URL]

2) A browser instance will open. Proceed with the login on Scribd and make sure to solve the captcha (if any). This step is required only for the first run. If you later want to login with another account, delete the session.json file and re-run the script.

3) The script will start downloading the book:

## TODO:
- [X] Scale/reduce pdf page size
- [ ] Render links in the PDFs
- [ ] Add EPUB conversion feature
- [ ] Add support for Documents
- [ ] Add support for Audiobooks

# DISCLAIMER:
The code is not intended for piracy or unlawful re-sharing purposes. You can only download the books you have purchased for the sole purpose of personal use. I do not take responsibility for illegal use of the software.
