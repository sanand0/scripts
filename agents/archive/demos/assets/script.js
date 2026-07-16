import { asyncLLM } from "asyncllm";
import { bootstrapAlert } from "bootstrap-alert";
import { openaiConfig } from "bootstrap-llm-provider";
import hljs from "highlight.js";
import { html, render } from "lit-html";
import { unsafeHTML } from "lit-html/directives/unsafe-html.js";
import { Marked } from "marked";
import { parse } from "partial-json";
import saveform from "saveform";

// Helpers
const $ = (selector, el = document) => el.querySelector(selector);
const loading = html`<div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div>`;

// Set up settings form persistence
const settingsForm = saveform("#settings-form");
$("#settings-form [type=reset]").addEventListener("click", () => settingsForm.clear());

// Set up Markdown rendering
const marked = new Marked();
marked.use({
  renderer: {
    code(code, lang) {
      const language = hljs.getLanguage(lang) ? lang : "plaintext";
      return /* html */ `<pre class="hljs language-${language}"><code>${
        hljs.highlight(code, { language }).value.trim()
      }</code></pre>`;
    },
  },
});

// Configure LLM on demand
$("#configure-llm").addEventListener("click", async () => await openaiConfig({ show: true }));

// Render demo cards
render(html`<div class="my-5 text-center">${loading}</div>`, $("#demo-cards"));
const config = await fetch("config.json").then((res) => res.json());
render(
  config.demos.map(({ icon, title, body }, index) =>
    html`
      <div class="col-md-4 col-lg-3">
        <div class="card demo-card h-100 text-center">
          <div class="card-body d-flex flex-column">
            <div class="mb-3"><i class="display-3 text-primary ${icon}"></i></div>
            <h6 class="card-title h5 mb-2">${title}</h6>
            <p class="card-text">${body}</p>
            <button class="mt-auto btn btn-primary" data-run-demo=${index}>Run</button>
          </div>
        </div>
      </div>`
  ),
  $("#demo-cards"),
);

// Handle demo runs
$("#demo-cards").addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-run-demo]");
  if (!button) return;

  const demo = config.demos[button.getAttribute("data-run-demo")];
  if (!demo) return;

  render(html`<div class="my-5 text-center">${loading}</div>`, $("#output"));

  const { baseUrl, apiKey } = await openaiConfig({ defaultBaseUrls: [
    // Use relevant LLM provider endpoints
    // OpenAI endpoints, for chat completions / Responses API
    "https://api.openai.com/v1",
    "https://aipipe.org/openai/v1",
    "https://llmfoundry.straivedemo.com/openai/v1",
    "https://llmfoundry.straive.com/openai/v1",
    // OpenRouter endpoints, which have a slightly different API
    "https://openrouter.ai/api/v1",
    "https://aipipe.org/openrouter/v1",
    "https://llmfoundry.straivedemo.com/openrouter/v1",
    "https://llmfoundry.straive.com/openrouter/v1",
  ]});
  const body = {
    model: $("#model").value || config.defaults.model,
    reasoning_effort: "minimal",
    messages: [{ role: "user", content: demo.prompt }],
    response_format: { type: "json_schema", json_schema: { name: "output_schema", schema: demo.schema } },
    stream: true,
  };

  try {
    for await (
      const { content, error } of asyncLLM(`${baseUrl}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify(body),
      })
    ) {
      if (error) throw error;
      if (!content) continue;
      const response = parse(content);
      if (!response?.snippets?.length) continue;
      render(response.snippets.map(renderSnippet), $("#output"));
    }
  } catch (e) {
    bootstrapAlert({ color: "danger", title: "LLM error", body: e });
  }
});

function renderSnippet({ code, explanation }) {
  const code_html = unsafeHTML(hljs.highlight(code ?? "", { language: "python" }).value);
  return html`
    <div class="card mb-4">
      <pre class="card-body hljs language-plaintext"><code>${code_html}</code></pre>
      <div class="card-footer">
        ${unsafeHTML(marked.parse(explanation ?? ""))}
      </div>
    </div>`;
}
