# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "beautifulsoup4",
# ]
# ///
import sys
import re
from bs4 import BeautifulSoup

def main():
    content = sys.stdin.read()

    # 1. Strip Markdown Images: ![alt](url) -> alt
    # We allow empty alt text with * instead of +
    content = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', content)

    # 2. Strip Markdown Links: [text](url) -> text
    # Now that images are stripped, we don't need the negative lookbehind
    content = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', content)

    # 3. Initialize BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')

    # 4. Strip HTML Images: <img src="..." alt="text"> -> text
    # We replace the tag entirely with the content of its 'alt' attribute
    for img in soup.find_all('img'):
        # use .get() to return empty string if alt attribute is missing
        soup_text  = img.get('alt', '')
        soup_text = "" if soup_text is None or not isinstance(soup_text, str) else soup_text
        img.replace_with(soup_text)

    # 5. Strip HTML Links: <a href="...">text</a> -> text
    # unwrap() removes the tag but keeps inner text/formatting
    for a in soup.find_all('a'):
        a.unwrap()

    print(soup.decode(formatter=None))

if __name__ == "__main__":
    main()
