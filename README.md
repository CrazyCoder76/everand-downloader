# scribd(everand)-multi thread downloader
Download your books from Everand in PDF format for personal and offline use.

### Please note:
Only everand **eBooks** are supported for now (no PDF Documents/Ebooks etc.)

## Installation

Install the required Python libraries:

  >$ pip install -r requirements.txt

## Preparation
Save book urls to your local mongodb database.

To scrape everand books url, you can use another project on my github repo ["everand-book-url-downloader"](https://github.com/CrazyCoder76/everand-book-url-scraper).

## Run
1) Run the script:

>$ python3 main.py

2) A multiple browser instance will open. Proceed with the login on Scribd and make sure to solve the captcha (if any). This step is required only for the first run. If you later want to login with another account, delete the session.json file and re-run the script.

3) The script will start downloading the book:
