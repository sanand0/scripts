import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    print("Connecting to Chrome DevTools at localhost:9222...")

    async with async_playwright() as p:
        # Connect to existing browser
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")

        # Get the default context and first page
        contexts = browser.contexts
        if not contexts:
            print("No contexts found, creating new one...")
            context = await browser.new_context()
        else:
            context = contexts[0]

        pages = context.pages
        if not pages:
            print("No pages found, creating new one...")
            page = await context.new_page()
        else:
            page = pages[0]

        # Set up console listener
        def handle_console(msg):
            print(f"[CONSOLE {msg.type}]: {msg.text}")

        page.on("console", handle_console)

        # Set up error listener
        def handle_error(error):
            print(f"[PAGE ERROR]: {error}")

        page.on("pageerror", handle_error)

        # Navigate to the page
        print("\nNavigating to the page...")
        await page.goto("http://localhost:8000/claude-code/ai-productivity-patterns.html", wait_until="networkidle")

        # Wait for animations
        print("Waiting for page to load...")
        await asyncio.sleep(3)

        # Take screenshot
        print("\nTaking screenshot...")
        await page.screenshot(path="/home/vscode/code/datastories/anthropic-work/claude-code/screenshot.png", full_page=True)
        print("Screenshot saved!")

        # Get page info
        page_info = await page.evaluate("""() => {
            return {
                title: document.title,
                d3Loaded: typeof d3 !== 'undefined',
                chartsCount: document.querySelectorAll('.chart').length,
                chartContainersCount: document.querySelectorAll('.chart-container').length
            };
        }""")

        print("\n=== Page Info ===")
        print(f"Title: {page_info['title']}")
        print(f"D3 Loaded: {page_info['d3Loaded']}")
        print(f"Charts: {page_info['chartsCount']}")
        print(f"Chart Containers: {page_info['chartContainersCount']}")

        # Check each chart
        chart_status = await page.evaluate("""() => {
            const charts = document.querySelectorAll('.chart');
            const status = [];
            charts.forEach((chart, i) => {
                const svg = chart.querySelector('svg');
                status.push({
                    index: i,
                    id: chart.id,
                    hasSvg: !!svg,
                    svgChildCount: svg ? svg.children.length : 0
                });
            });
            return status;
        }""")

        print("\n=== Chart Status ===")
        for chart in chart_status:
            status = f"✓ SVG with {chart['svgChildCount']} children" if chart['hasSvg'] else "✗ No SVG"
            print(f"Chart {chart['index']} ({chart['id']}): {status}")

        print("\n=== Done ===")
        await browser.close()

asyncio.run(main())
