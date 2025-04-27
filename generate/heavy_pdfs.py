# Generates a vector-heavy PDF with lots rectangles which is hard for PyMuPDF to read.
# Saves it as heavy.pdf.
# Generates a Lua script for wrk to upload the PDF file.
# Sample usage: wrk -s heavy.lua -d 10 http://localhost:8000/pdf

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pymupdf",
#     "tqdm",
# ]
# ///

import fitz
import os
from tqdm import tqdm


# Generates a vector-heavy PDF with lots rectangles which is hard for PyMuPDF to read.
if not os.path.exists("heavy.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4-ish
    for i in tqdm(range(7000)):
        x = (i * 7) % 595
        y = ((i * 7) // 595 * 5) % 842
        rect = fitz.Rect(x, y, x + 3, y + 3)
        page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
    with open(os.path.join("heavy.pdf"), "wb") as f:
        f.write(doc.tobytes())


# Generate a Lua script for wrk to upload the PDF file.
if not os.path.exists("heavy.lua"):
    # Configuration
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"  # any random boundary string
    mode_value = ""

    # Read the file to upload
    with open("heavy.pdf", "rb") as f:
        file_bytes = f.read()

    # Multipart body
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="heavy.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8")
        + file_bytes
        + (
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="mode"\r\n\r\n'
            f"page\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
    )

    # Escape Lua string
    def escape_lua_string(b):
        return (
            b.decode("latin1")
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    chunk_size = 4000  # Lua strings should not be too large
    chunks = []
    for i in range(0, len(body), chunk_size):
        chunk = body[i : i + chunk_size]
        chunks.append(f'"{escape_lua_string(chunk)}"')

    lua_script = f"""\
wrk.method = "POST"
wrk.body = table.concat({{
{",\n".join(chunks)}
}})
wrk.headers["Content-Type"] = "multipart/form-data; boundary={boundary}"
wrk.headers["Sec-Fetch-Mode"] = "cors"
wrk.headers["Cache-Control"] = "no-cache"
"""

    # Write to file
    with open("heavy.lua", "w", encoding="utf-8") as f:
        f.write(lua_script)
