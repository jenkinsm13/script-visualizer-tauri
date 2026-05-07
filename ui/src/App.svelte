<script lang="ts">
  import { onMount } from "svelte";

  type Health = { ok: boolean; project: string };

  let health = $state<Health | null>(null);
  let healthError = $state<string | null>(null);

  const SERVER = "http://127.0.0.1:8767";

  async function ping() {
    try {
      const r = await fetch(`${SERVER}/healthz`);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      health = (await r.json()) as Health;
      healthError = null;
    } catch (e) {
      healthError = e instanceof Error ? e.message : String(e);
      health = null;
    }
  }

  onMount(() => {
    ping();
    const t = setInterval(ping, 4000);
    return () => clearInterval(t);
  });
</script>

<main>
  <header>
    <h1>Script Visualizer</h1>
    <p class="tagline">Screenplay → storyboard images</p>
  </header>

  <section class="status">
    {#if health}
      <span class="ok">●</span>
      <span>server: <code>{health.project}</code></span>
    {:else if healthError}
      <span class="err">●</span>
      <span class="err-text">server unreachable: <code>{healthError}</code></span>
    {:else}
      <span class="dim">●</span>
      <span class="dim">connecting…</span>
    {/if}
  </section>

  <section class="empty">
    <h2>Empty scaffold.</h2>
    <p>This is a fresh Tauri+Svelte shell that auto-spawns the FastAPI sidecar at <code>:8767</code>.</p>
    <p>Next steps to wire up:</p>
    <ol>
      <li>Drop a screenplay PDF / fountain file into the UI (file picker via <code>@tauri-apps/plugin-fs</code>)</li>
      <li>Server parses it via <code>src/core/parser.py</code> → list of scenes</li>
      <li>For each scene, build an image-gen prompt via <code>src/core/prompt_structure.py</code></li>
      <li>Send prompts to SD/Flux/Imagen via <code>src/ai/sd_connector.py</code></li>
      <li>UI shows a storyboard grid as images stream back</li>
    </ol>
    <p class="dim">Rebuild from the original <code>script_visualizer/gui</code> (PySide6) — the data flow is already in <code>src/core/</code>.</p>
  </section>
</main>

<style>
  :global(body) {
    margin: 0;
    background: #15171d;
    color: #e8eaed;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  }
  main {
    max-width: 760px;
    margin: 0 auto;
    padding: 48px 32px;
  }
  header h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .tagline {
    margin: 4px 0 0;
    color: #8b919c;
    font-size: 14px;
  }
  .status {
    margin: 20px 0 32px;
    padding: 8px 12px;
    background: #1c1f27;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .status code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  .ok { color: #5fcf80; }
  .err { color: #ff6b6b; }
  .err-text { color: #ff6b6b; }
  .dim { color: #6b7280; }
  .empty {
    background: #1c1f27;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
    padding: 22px 26px;
  }
  .empty h2 {
    margin: 0 0 10px;
    font-size: 17px;
    font-weight: 600;
  }
  .empty p { line-height: 1.55; }
  .empty ol { padding-left: 22px; line-height: 1.7; }
  .empty code {
    background: #2a2f3a;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
  }
</style>
