<script lang="ts">
  import { onMount } from "svelte";
  import {
    getHealth,
    getStyles,
    parseScript,
    parseShotList,
    type Health,
    type Scene,
    type StylePreset,
  } from "./lib/api";
  import SceneCard from "./lib/SceneCard.svelte";

  let health = $state<Health | null>(null);
  let healthError = $state<string | null>(null);

  type Mode = "screenplay" | "shotlist";
  let mode = $state<Mode>("screenplay");

  let scriptText = $state("");
  let scenes = $state<Scene[]>([]);
  let parsing = $state(false);
  let parseError = $state<string | null>(null);
  let loadedFileName = $state<string | null>(null);

  let styles = $state<StylePreset[]>([]);
  let selectedStyle = $state("cinematic");

  // Project-wide subject glossary. The LLM that builds image prompts (per
  // SceneCard) gets this as context so character/vehicle/prop identity
  // stays consistent across shots — e.g. "BRONCO = 6th-gen Ford Bronco
  // SUV, red, 4-door, soft top". Persisted to localStorage so it survives
  // app restarts.
  const GLOSSARY_KEY = "sv:glossary";
  let glossary = $state(
    typeof localStorage !== "undefined"
      ? localStorage.getItem(GLOSSARY_KEY) ?? ""
      : "",
  );
  let glossaryOpen = $state(false);
  $effect(() => {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(GLOSSARY_KEY, glossary);
    }
  });

  // 2:1 aspect (Univisium / cinematic storyboard). Dims are multiples of 64
  // to match Flux's tile constraints — DrawThings rounds non-multiples down
  // silently. Times are Flux.2 [dev] (32B) on M5 Max @ 30 steps.
  const RES_PRESETS = [
    { id: "low",    label: "Low 512×256 (~20-40s)",     w: 512,  h: 256 },
    { id: "high",   label: "High 1024×512 (~60-90s)",   w: 1024, h: 512 },
    { id: "ultra",  label: "Ultra 1280×640 (~2min)",    w: 1280, h: 640 },
    { id: "hero",   label: "Hero 1920×960 (~5-7min)",   w: 1920, h: 960 },
    { id: "final",  label: "Final 2048×1024 (~7-10min)", w: 2048, h: 1024 },
  ];
  let selectedRes = $state("high");
  const currentRes = $derived(
    RES_PRESETS.find((r) => r.id === selectedRes) ?? RES_PRESETS[1],
  );

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

  function _u8ToBase64(bytes: Uint8Array): string {
    let bin = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      bin += String.fromCharCode.apply(
        null,
        bytes.subarray(i, i + chunk) as unknown as number[],
      );
    }
    return btoa(bin);
  }

  async function openFile() {
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const filters =
        mode === "shotlist"
          ? [
              { name: "Shot list", extensions: ["pdf", "txt", "md"] },
              { name: "Any", extensions: ["*"] },
            ]
          : [
              {
                name: "Screenplay",
                extensions: ["txt", "fountain", "fdx", "md"],
              },
              { name: "Any", extensions: ["*"] },
            ];
      const path = await open({ multiple: false, filters });
      if (typeof path !== "string") return;
      loadedFileName = path.split("/").pop() ?? path;
      const fs = await import("@tauri-apps/plugin-fs");

      if (mode === "shotlist" && path.toLowerCase().endsWith(".pdf")) {
        // PDF → read as bytes, base64-encode, send to /parse-shotlist
        const bytes = await fs.readFile(path);
        const b64 = _u8ToBase64(bytes);
        scriptText = `[PDF loaded: ${loadedFileName} — ${(bytes.length / 1024).toFixed(1)} KB]`;
        parsing = true;
        parseError = null;
        try {
          scenes = await parseShotList({ pdf_base64: b64 });
        } catch (e) {
          parseError = e instanceof Error ? e.message : String(e);
        } finally {
          parsing = false;
        }
        return;
      }

      // Plain text path (screenplay or text shot list)
      scriptText = await fs.readTextFile(path);
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
      if (mode === "shotlist") {
        scenes = await parseShotList({ text: scriptText });
      } else {
        scenes = await parseScript(scriptText);
      }
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
      <span class="dim">{mode === "shotlist" ? "shot list" : "screenplay"} → storyboard</span>
    </div>
    <div class="mode-toggle" role="tablist">
      <button
        role="tab"
        aria-selected={mode === "screenplay"}
        class:active={mode === "screenplay"}
        onclick={() => (mode = "screenplay")}
        disabled={parsing}>Screenplay</button>
      <button
        role="tab"
        aria-selected={mode === "shotlist"}
        class:active={mode === "shotlist"}
        onclick={() => (mode = "shotlist")}
        disabled={parsing}>Shot list</button>
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
      placeholder={mode === "shotlist"
        ? "Paste shot list here, or click 'Open file' to load a PDF…"
        : "Paste screenplay here, or click 'Open file' below…"}
      rows="6"
      disabled={parsing}
    ></textarea>
    {#if loadedFileName}
      <div class="loaded">📄 {loadedFileName}</div>
    {/if}
    <div class="controls">
      <button class="primary" onclick={parse} disabled={parsing || !scriptText.trim()}>
        {parsing ? "parsing…" : "Parse"}
      </button>
      <button onclick={openFile} disabled={parsing}>Open file…</button>
      <div class="spacer"></div>
      <label class="style-pick">
        <span class="dim">size</span>
        <select bind:value={selectedRes}>
          {#each RES_PRESETS as r (r.id)}
            <option value={r.id}>{r.label}</option>
          {/each}
        </select>
      </label>
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

    <!-- Project subject glossary. One per app (persisted to localStorage).
         Fed into every per-shot prompt-gen call so vehicles/characters/
         props stay consistent. -->
    <details class="glossary" bind:open={glossaryOpen}>
      <summary>
        Subject glossary
        {#if glossary.trim()}
          <span class="dim glossary-count">
            ({glossary.split("\n").filter((l) => l.trim()).length} entries)
          </span>
        {:else}
          <span class="dim">— pin character / vehicle / prop identities so prompts stay consistent across shots</span>
        {/if}
      </summary>
      <textarea
        bind:value={glossary}
        rows="4"
        placeholder={`one per line, NAME = description\nBRONCO = 6th-gen Ford Bronco SUV, red, 4-door, soft top, 2023 model\nELIZA = woman 30s, brown hair, blue denim jacket\nSTEPH = girl 6 years old, blonde pigtails, pink dress`}
      ></textarea>
    </details>
  </section>

  {#if scenes.length === 0 && !parseError}
    <section class="empty">
      <h2>Empty.</h2>
      {#if mode === "shotlist"}
        <p>Open a shot-list PDF or paste shot-list text. Format expected: <code>INT./EXT. LOCATION - TIME</code> headers followed by numbered shots <code>1) DESCRIPTION</code>.</p>
        <p class="dim">Each shot becomes its own card with its own image. Hit <strong>render</strong> per card.</p>
      {:else}
        <p>Drop a screenplay (.txt / .fountain / .md) or paste raw screenplay text and hit <strong>Parse</strong>.</p>
        <p class="dim">Each scene becomes a card. Click <strong>render</strong> on any card to generate a storyboard image.</p>
      {/if}
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
        <SceneCard
          {scene}
          styleId={selectedStyle}
          {styles}
          width={currentRes.w}
          height={currentRes.h}
          {glossary}
        />
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
  .mode-toggle {
    display: flex;
    background: #1c1f27;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
    overflow: hidden;
    margin-left: 14px;
  }
  .mode-toggle button {
    background: transparent;
    color: #8b919c;
    border: none;
    padding: 6px 14px;
    font-size: 12px;
    cursor: pointer;
    font-weight: 500;
  }
  .mode-toggle button.active {
    background: #2a2f3a;
    color: #e8eaed;
  }
  .mode-toggle button:hover:not(.active):not(:disabled) {
    background: #1f232c;
    color: #c5c8cf;
  }
  .mode-toggle button:disabled { opacity: 0.5; cursor: not-allowed; }
  .loaded {
    margin-top: 8px;
    font-size: 11px;
    color: #5fcf80;
  }
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
  .glossary {
    margin-top: 10px;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
    background: #15171d;
  }
  .glossary > summary {
    cursor: pointer;
    padding: 8px 12px;
    font-size: 12px;
    list-style: none;
    user-select: none;
  }
  .glossary > summary::-webkit-details-marker { display: none; }
  .glossary > summary::before {
    content: "▸";
    color: #6b7280;
    margin-right: 6px;
    font-size: 10px;
  }
  .glossary[open] > summary::before { content: "▾"; }
  .glossary-count { color: #5fcf80; font-weight: 600; }
  .glossary textarea {
    display: block;
    width: 100%;
    box-sizing: border-box;
    border: none;
    border-top: 1px solid #2a2f3a;
    border-radius: 0;
    background: #15171d;
    color: #e8eaed;
    padding: 10px 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    line-height: 1.55;
    resize: vertical;
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
