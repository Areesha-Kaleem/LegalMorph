import re
from langdetect import detect
from bs4 import BeautifulSoup


def extract_clean_text_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()

    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()

    if detect(text) != 'en':
        raise Exception("Non-English content detected")

    return text
