#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["click", "markdownify", "playwright"]
# ///
import asyncio
import click
import markdownify
import os
from playwright.async_api import async_playwright

SITES = {
    'google': (
        "https://www.google.com/search?udm=50",
        "textarea",
        "button[aria-label='Positive feedback']",
        "div[data-container-id='main-col']"
    ),
    "chatgpt": (
        "https://chatgpt.com",
        '#prompt-textarea',
        "[data-testid=good-response-turn-action-button]",
        ".markdown",
    ),
    "claude": (
        "https://claude.ai/new",
        'css=div[contenteditable="true"]:not([aria-hidden="true"])',
        "[aria-label='Give positive feedback']",
        ".standard-markdown",
    ),
    "gemini": (
        "https://gemini.google.com/u/2/app",
        'css=.textarea',
        "button.submit",
        "div.markdown",
    ),
}

async def ask(site, question):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(os.getenv("CDP_URL", "http://127.0.0.1:9222"))
        page = await browser.contexts[0].new_page()
        await page.bring_to_front()
        url, input_sel, complete_sel, resp_sel = SITES[site]
        await page.goto(url, wait_until="domcontentloaded")
        box = page.locator(input_sel).first
        await box.wait_for(state="visible")
        await box.fill(question)
        await box.press("Enter")
        await page.wait_for_selector(complete_sel, timeout=900_000)
        txt = await page.locator(resp_sel).inner_html()
        print("\r" + markdownify.markdownify(txt.strip()))


@click.command()
@click.option("-m", type=click.Choice(list(SITES)), default=list(SITES)[0], show_default=True)
@click.argument("question", nargs=-1, required=True)
def main(m, question):
    asyncio.run(ask(m, " ".join(question)))


if __name__ == "__main__":
    main()
