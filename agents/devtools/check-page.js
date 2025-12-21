const { chromium } = require('playwright');

(async () => {
  console.log('Connecting to Chrome DevTools at localhost:9222...');

  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const contexts = browser.contexts();
  const context = contexts[0];

  // Get or create a page
  let page;
  const pages = context.pages();
  if (pages.length > 0) {
    page = pages[0];
  } else {
    page = await context.newPage();
  }

  // Listen for console messages
  page.on('console', msg => {
    console.log(`[CONSOLE ${msg.type()}]:`, msg.text());
  });

  // Listen for page errors
  page.on('pageerror', error => {
    console.error('[PAGE ERROR]:', error.message);
  });

  // Navigate to the page
  console.log('\nNavigating to the page...');
  await page.goto('http://localhost:8000/claude-code/ai-productivity-patterns.html', {
    waitUntil: 'networkidle'
  });

  // Wait a bit for animations to start
  await page.waitForTimeout(2000);

  // Take a screenshot
  console.log('\nTaking screenshot...');
  await page.screenshot({
    path: '/home/vscode/code/datastories/anthropic-work/claude-code/screenshot.png',
    fullPage: true
  });
  console.log('Screenshot saved to screenshot.png');

  // Check for D3 and basic structure
  const pageInfo = await page.evaluate(() => {
    return {
      title: document.title,
      d3Loaded: typeof d3 !== 'undefined',
      chartsCount: document.querySelectorAll('.chart').length,
      chartContainersCount: document.querySelectorAll('.chart-container').length,
      errors: []
    };
  });

  console.log('\n=== Page Info ===');
  console.log('Title:', pageInfo.title);
  console.log('D3 Loaded:', pageInfo.d3Loaded);
  console.log('Charts:', pageInfo.chartsCount);
  console.log('Chart Containers:', pageInfo.chartContainersCount);

  // Check each chart for SVG content
  const chartStatus = await page.evaluate(() => {
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
  });

  console.log('\n=== Chart Status ===');
  chartStatus.forEach(chart => {
    console.log(`Chart ${chart.index} (${chart.id}):`,
      chart.hasSvg ? `✓ SVG with ${chart.svgChildCount} children` : '✗ No SVG');
  });

  console.log('\n=== Done ===');
  await browser.close();
})();
