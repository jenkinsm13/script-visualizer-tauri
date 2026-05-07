<script lang="ts">
  import { onMount } from "svelte";
  import {
    getHealth,
    getStyles,
    parseScript,
    type Health,
    type Scene,
    type StylePreset,
  } from "./lib/api";
  import SceneCard from "./lib/SceneCard.svelte";

  let health = $state<Health | null>(null);
  let healthError = $state<string | null>(null);

  let scriptText = $state("");
  let scenes = $state<Scene[]>([]);
  let parsing = $state(false);
  let parseError = $state<string | null>(null);

  let styles = $state<StylePreset[]>([]);
  let selectedStyle = $state("cinematic");

  async function ping() {
    try {
      health = await getHealth();
      healthError = null;
    } catch (e) {
      healthError = e instanceof Error ? e.message : String(e);
      health = null;
    }
  }

  async function loadStyles() {
    try {
      styles = await getStyles();
    } catch {
      // server probably not up yet — ping loop will retry
    }
  }

  async function openFile() {
    // Tauri 2 dialog plugin (lazy-imported so the page works without Tauri).
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const path = await open({
        multiple: false,
        filters: [
          { name: "Screenplay", extensions: ["txt", "fountain", "fdx", "md"] },
          { name: "Any", extensions: ["*"] },
        ],
      });
      if (typeof path !== "string") return;
      const { readTextFile } = await import("@tauri-apps/plugin-fs");
      scriptText = await readTextFile(path);
      // auto-parse on load
      parse();
    } catch (e) {
      parseError = `file open: ${e instanceof Error ? e.message : String(e)}`;
    }
  }

  async function parse() {
    if (!scriptText.trim() || parsing) return;
    parsing = true;
    parseError = null;
    try {
      scenes = await parseScript(scriptText);
    } catch (e) {
      parseError = e instanceof Error ? e.message : String(e);
    } finally {
      parsing = false;
    }
  }

  onMount(() => {
    ping();
    loadStyles();
    const t = setInterval(() => {
      ping();
      if (styles.length === 0) loadStyles();
    }, 5000);
    return () => clearInterval(t);
  });
</script>

<main>
  <header class="topbar">
    <div class="title">
      <h1>Script Visualizer</h1>
      <span class="dim">screenplay → storyboard</span>
    </div>
    <div class="status">
      {#if health}
        <span class="ok">●</span>
        <span class="dim">server up</span>
      {:else if healthError}
        <span class="err">●</span>
        <span class="err-text" title={healthError}>server unreachable</span>
      {:else}
        <span class="dim">●</span>
        <span class="dim">connecting…</span>
      {/if}
    </div>
  </header>

  <section class="input-row">
    <textarea
      bind:value={scriptText}
      placeholder="Paste screenplay here, or click 'Open file' below…"
      rows="6"
      disabled={parsing}
    ></textarea>
    <div class="controls">
      <button class="primary" onclick={parse} disabled={parsing || !scriptText.trim()}>
        {parsing ? "parsing…" : "Parse"}
      </button>
      <button onclick={openFile} disabled={parsing}>Open file…</button>
      <div class="spacer"></div>
      <label class="style-pick">
        <span class="dim">style</span>
        <select bind:value={selectedStyle}>
          {#each styles as s (s.id)}
            <option value={s.id}>{s.name}</option>
          {/each}
        </select>
      </label>
    </div>
    {#if parseError}
      <div class="err-box">{parseError}</div>
    {/if}
  </section>

  {#if scenes.length === 0 && !parseError}
    <section class="empty">
      <h2>Empty.</h2>
      <p>Drop a screenplay (.txt / .fountain / .md) or paste raw screenplay text and hit <strong>Parse</strong>.</p>
      <p class="dim">Each scene becomes a card. Click <strong>render</strong> on any card to generate a storyboard image.</p>
      <p class="dim small">
        Image generation backends (in priority order):
        <code>SD_URL=http://localhost:7860</code> (AUTOMATIC1111),
        <code>REPLICATE_API_TOKEN=…</code> (Flux Schnell). Without either, you get a
        text placeholder so the pipeline still works end-to-end.
      </p>
    </section>
  {:else if scenes.length > 0}
    <section class="grid">
      {#each scenes as scene (scene.number)}
        <SceneCard {scene} styleId={selectedStyle} {styles} />
      {/each}
    </section>
  {/if}
</main>

<style>
  :global(html, body) {
    margin: 0;
    height: 100%;
    background: #15171d;
    color: #e8eaed;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    font-size: 14px;
  }
  main { padding: 18px 22px 36px; max-width: 1400px; margin: 0 auto; }

  .topbar {
    display: flex;
    align-items: baseline;
    gap: 18px;
    margin-bottom: 18px;
  }
  .title h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.01em;
    display: inline;
  }
  .title .dim { margin-left: 10px; font-size: 12px; }
  .status { margin-left: auto; font-size: 12px; }
  .ok { color: #5fcf80; }
  .err { color: #ff6b6b; }
  .err-text { color: #ff6b6b; cursor: help; }
  .dim { color: #6b7280; }

  .input-row {
    background: #1c1f27;
    border: 1px solid #2a2f3a;
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 18px;
  }
  textarea {
    width: 100%;
    box-sizing: border-box;
    background: #15171d;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
    color: #e8eaed;
    padding: 10px 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    line-height: 1.5;
    resize: vertical;
  }
  .controls {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-top: 10px;
  }
  .controls button {
    background: #2a2f3a;
    color: #e8eaed;
    border: 1px solid #3a3f4a;
    padding: 6px 14px;
    border-radius: 5px;
    font-size: 12px;
    cursor: pointer;
  }
  .controls button:hover:not(:disabled) { background: #3a3f4a; }
  .controls button:disabled { opacity: 0.5; cursor: not-allowed; }
  .controls button.primary {
    background: #4ec3ff;
    color: #15171d;
    font-weight: 600;
    border-color: #4ec3ff;
  }
  .controls button.primary:hover:not(:disabled) { background: #7fd5ff; }
  .controls .spacer { flex: 1; }
  .style-pick {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
  }
  .style-pick select {
    background: #15171d;
    color: #e8eaed;
    border: 1px solid #3a3f4a;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
  }

  .err-box {
    margin-top: 10px;
    padding: 8px 12px;
    background: rgba(255,107,107,0.1);
    border: 1px solid #ff6b6b;
    border-radius: 5px;
    color: #ff6b6b;
    font-size: 12px;
  }

  .empty {
    background: #1c1f27;
    border: 1px solid #2a2f3a;
    border-radius: 10px;
    padding: 28px;
    text-align: center;
  }
  .empty h2 { margin: 0 0 8px; font-size: 17px; font-weight: 600; }
  .empty p { line-height: 1.55; }
  .empty .small { font-size: 11px; max-width: 700px; margin-left: auto; margin-right: auto; }
  .empty code {
    background: #2a2f3a;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    margin: 0 1px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
    gap: 14px;
  }
</style>
