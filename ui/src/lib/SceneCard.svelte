<script lang="ts">
  import type { Scene, StylePreset } from "./api";
  import { generatePromptForScene, renderScene, renderImageUrl } from "./api";

  type Props = {
    scene: Scene;
    styleId: string;
    styles: StylePreset[];
    width?: number;
    height?: number;
    glossary?: string;
  };
  let {
    scene,
    styleId,
    width = 1024,
    height = 512,
    glossary = "",
  }: Props = $props();

  let renderState = $state<"idle" | "loading" | "ready" | "error">("idle");
  let imageUrl = $state<string | null>(null);
  let renderBackend = $state<string>("");
  let renderDetail = $state<string>("");
  let renderError = $state<string | null>(null);

  // LLM-generated image prompt. When present, overrides scene.base_prompt
  // for the next render. Editable so the user can tweak before rendering.
  let generatedPrompt = $state<string | null>(null);
  let promptModel = $state<string>("");
  let promptElapsed = $state<number>(0);
  let promptState = $state<"idle" | "loading" | "ready" | "error">("idle");
  let promptError = $state<string | null>(null);

  // Reference images for Flux.2 multi-image conditioning (character/style/
  // composition consistency across shots). Stored as { dataUrl, base64 }
  // — dataUrl for <img> preview, base64 for the /render payload.
  type Ref = { dataUrl: string; base64: string; name: string };
  let refs = $state<Ref[]>([]);
  let refError = $state<string | null>(null);

  function _fileToRef(file: File): Promise<Ref> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result as string;
        // strip "data:image/png;base64," prefix
        const comma = dataUrl.indexOf(",");
        const base64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
        resolve({ dataUrl, base64, name: file.name });
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function addReferences(files: FileList | File[] | null) {
    if (!files) return;
    refError = null;
    const wanted = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (!wanted.length) {
      refError = "no image files in drop";
      return;
    }
    try {
      const newRefs = await Promise.all(wanted.map(_fileToRef));
      refs = [...refs, ...newRefs].slice(0, 4); // cap at 4
    } catch (e) {
      refError = e instanceof Error ? e.message : String(e);
    }
  }

  function removeRef(i: number) {
    refs = refs.filter((_, idx) => idx !== i);
  }

  let dragOver = $state(false);
  function onDrop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    addReferences(e.dataTransfer?.files ?? null);
  }
  function onDragOver(e: DragEvent) {
    e.preventDefault();
    dragOver = true;
  }
  function onDragLeave() {
    dragOver = false;
  }
  function onPickFiles(e: Event) {
    const input = e.target as HTMLInputElement;
    addReferences(input.files);
    input.value = ""; // allow re-picking same file
  }

  // What gets sent to /render: generated prompt if available, else the
  // rule-based base_prompt the parser produced.
  const effectivePrompt = $derived(
    (generatedPrompt && generatedPrompt.trim()) || scene.base_prompt,
  );

  // The shot description the LLM should translate. For shot-list cards
  // there's exactly one action_descriptions entry per shot; for screenplay
  // scenes, join the lot.
  const shotDescription = $derived(
    scene.action_descriptions.length > 0
      ? scene.action_descriptions.join(" ")
      : scene.heading,
  );

  async function generatePrompt() {
    promptState = "loading";
    promptError = null;
    try {
      const r = await generatePromptForScene({
        heading: scene.heading,
        setting: `${scene.location.setting_type} ${scene.location.name}`,
        time_of_day: scene.location.time_of_day,
        characters: scene.characters.map((c) => c.name),
        description: shotDescription,
        glossary: glossary && glossary.trim() ? glossary : undefined,
      });
      generatedPrompt = r.text;
      promptModel = r.model;
      promptElapsed = r.elapsed_seconds;
      promptState = "ready";
    } catch (e) {
      promptError = e instanceof Error ? e.message : String(e);
      promptState = "error";
    }
  }

  async function render() {
    renderState = "loading";
    renderError = null;
    try {
      const r = await renderScene({
        scene_idx: scene.number - 1,
        prompt: effectivePrompt,
        style_id: styleId,
        width,
        height,
        reference_images: refs.map((r) => r.base64),
      });
      imageUrl = renderImageUrl(r.image_url);
      renderBackend = r.backend;
      renderDetail = r.detail;
      renderState = "ready";
    } catch (e) {
      renderError = e instanceof Error ? e.message : String(e);
      renderState = "error";
    }
  }
</script>

<div class="card">
  <header>
    <span class="badge">{scene.location.setting_type}</span>
    <h3>{scene.heading}</h3>
    <span class="meta">
      {scene.location.time_of_day} · tone: {scene.visual_style.tone}
      {#if scene.visual_style.atmosphere_keywords.length}
        · {scene.visual_style.atmosphere_keywords.join(", ")}
      {/if}
    </span>
  </header>

  <div class="body">
    <div class="image-slot" class:loading={renderState === "loading"}>
      {#if renderState === "ready" && imageUrl}
        <img src={imageUrl} alt="scene {scene.number} storyboard" />
        {#if renderBackend === "stub"}
          <div class="stub-tag" title={renderDetail}>placeholder</div>
        {:else}
          <div class="backend-tag">{renderBackend}</div>
        {/if}
      {:else if renderState === "loading"}
        <div class="placeholder">rendering…</div>
      {:else if renderState === "error"}
        <div class="placeholder err">render failed: {renderError}</div>
      {:else}
        <div class="placeholder dim">no image yet</div>
      {/if}
    </div>

    <div class="details">
      {#if scene.characters.length}
        <p class="line"><span class="label">cast</span> {scene.characters.map((c) => c.name).join(", ")}</p>
      {/if}
      {#if scene.action_descriptions.length}
        <p class="line action">{scene.action_descriptions.slice(0, 2).join(" ")}{scene.action_descriptions.length > 2 ? "…" : ""}</p>
      {/if}
      {#if scene.dialogue.length}
        <details class="dialogue">
          <summary>{scene.dialogue.length} dialogue line{scene.dialogue.length === 1 ? "" : "s"}</summary>
          {#each scene.dialogue as [who, what]}
            <div class="dline"><span class="who">{who}</span> {what}</div>
          {/each}
        </details>
      {/if}
      <details class="prompt" open={generatedPrompt !== null}>
        <summary>
          {#if generatedPrompt !== null}
            prompt <span class="model-tag">{promptModel} · {promptElapsed.toFixed(1)}s</span>
          {:else}
            prompt <span class="dim">(rule-based — click "generate prompt" to enhance)</span>
          {/if}
        </summary>
        {#if generatedPrompt !== null}
          <textarea
            class="prompt-edit"
            bind:value={generatedPrompt}
            rows="3"
            placeholder="image-gen prompt"
          ></textarea>
        {:else}
          <pre>{scene.base_prompt}</pre>
        {/if}
        {#if promptError}
          <div class="prompt-err">prompt-gen failed: {promptError}</div>
        {/if}
      </details>

      <!-- Reference images: drop or click to add. Used by the render call
           as Flux.2 multi-image inputs. -->
      <div
        class="refs"
        class:dragover={dragOver}
        ondrop={onDrop}
        ondragover={onDragOver}
        ondragleave={onDragLeave}
        role="region"
        aria-label="Reference images"
      >
        {#if refs.length === 0}
          <label class="refs-empty">
            <input type="file" accept="image/*" multiple onchange={onPickFiles} />
            <span class="dim">drop reference image(s) here, or click to pick</span>
          </label>
        {:else}
          <div class="refs-row">
            {#each refs as r, i (i)}
              <figure class="ref-thumb" title={r.name}>
                <img src={r.dataUrl} alt={r.name} />
                <button
                  type="button"
                  class="ref-remove"
                  onclick={() => removeRef(i)}
                  aria-label="remove reference">×</button>
              </figure>
            {/each}
            {#if refs.length < 4}
              <label class="ref-add">
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  onchange={onPickFiles}
                />
                <span>+</span>
              </label>
            {/if}
          </div>
        {/if}
        {#if refError}
          <div class="prompt-err">{refError}</div>
        {/if}
      </div>
    </div>
  </div>

  <footer>
    <button
      class="ghost"
      onclick={generatePrompt}
      disabled={promptState === "loading"}
      title="Use the local LLM to translate this shot into a still-frame image-gen prompt"
    >
      {#if promptState === "loading"}
        thinking…
      {:else if generatedPrompt !== null}
        regenerate prompt
      {:else}
        generate prompt
      {/if}
    </button>
    <button onclick={render} disabled={renderState === "loading"}>
      {renderState === "ready" ? "re-render" : "render"}
    </button>
  </footer>
</div>

<style>
  .card {
    background: #1c1f27;
    border: 1px solid #2a2f3a;
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    border-bottom: 1px solid #2a2f3a;
  }
  .badge {
    background: #4ec3ff;
    color: #15171d;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
    letter-spacing: 0.5px;
  }
  header h3 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .meta { color: #8b919c; font-size: 11px; }
  .body { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; flex: 1; }
  .image-slot {
    aspect-ratio: 16 / 9;
    background: #15171d;
    border-radius: 6px;
    overflow: hidden;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .image-slot img { width: 100%; height: 100%; display: block; object-fit: cover; }
  .image-slot.loading { animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.65; } }
  .placeholder { color: #6b7280; font-size: 12px; padding: 30px; text-align: center; }
  .placeholder.err { color: #ff6b6b; }
  .placeholder.dim { color: #4a5160; }
  .stub-tag, .backend-tag {
    position: absolute;
    top: 6px;
    right: 6px;
    background: rgba(0,0,0,0.6);
    color: #fff;
    font-size: 9px;
    padding: 2px 6px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }
  .stub-tag { background: rgba(255,200,90,0.85); color: #15171d; cursor: help; }
  .details { font-size: 12px; line-height: 1.5; }
  .line { margin: 0 0 4px; color: #c5c8cf; }
  .line.action { color: #a5acb8; font-style: italic; }
  .label { color: #6b7280; font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px; margin-right: 4px; }
  .dialogue { font-size: 11px; color: #a5acb8; }
  .dialogue summary { cursor: pointer; color: #6b7280; }
  .dline { margin-top: 4px; padding-left: 10px; }
  .who { font-weight: 600; color: #4ec3ff; margin-right: 6px; }
  .prompt summary { cursor: pointer; color: #6b7280; font-size: 11px; }
  .prompt pre {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 10px;
    margin: 6px 0 0;
    padding: 8px;
    background: #15171d;
    border-radius: 4px;
    white-space: pre-wrap;
    word-break: break-word;
    color: #8b919c;
  }
  footer {
    padding: 10px 14px;
    border-top: 1px solid #2a2f3a;
    display: flex;
    gap: 8px;
  }
  footer button {
    flex: 1;
    background: #4ec3ff;
    color: #15171d;
    border: 1px solid #4ec3ff;
    padding: 6px 10px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  footer button:hover:not(:disabled) { background: #7fd5ff; }
  footer button:disabled { opacity: 0.5; cursor: not-allowed; }
  footer button.ghost {
    background: #2a2f3a;
    color: #e8eaed;
    border-color: #3a3f4a;
    font-weight: 500;
  }
  footer button.ghost:hover:not(:disabled) { background: #3a3f4a; }
  .model-tag {
    color: #5fcf80;
    font-size: 10px;
    margin-left: 6px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .prompt-edit {
    width: 100%;
    box-sizing: border-box;
    margin-top: 6px;
    background: #15171d;
    border: 1px solid #2a2f3a;
    color: #e8eaed;
    border-radius: 4px;
    padding: 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    line-height: 1.5;
    resize: vertical;
  }
  .prompt-err {
    margin-top: 6px;
    color: #ff6b6b;
    font-size: 11px;
  }

  /* Reference-image drop zone */
  .refs {
    margin-top: 8px;
    border: 1px dashed #3a3f4a;
    border-radius: 6px;
    padding: 8px;
    transition: border-color 0.12s, background 0.12s;
  }
  .refs.dragover {
    border-color: #4ec3ff;
    background: rgba(78, 195, 255, 0.06);
  }
  .refs-empty {
    display: block;
    text-align: center;
    padding: 14px 8px;
    cursor: pointer;
    font-size: 11px;
  }
  .refs-empty input[type="file"] {
    display: none;
  }
  .refs-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
  }
  .ref-thumb {
    margin: 0;
    position: relative;
    width: 60px;
    height: 60px;
    border-radius: 4px;
    overflow: hidden;
    background: #15171d;
    border: 1px solid #2a2f3a;
  }
  .ref-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .ref-remove {
    position: absolute;
    top: 2px;
    right: 2px;
    width: 18px;
    height: 18px;
    background: rgba(0, 0, 0, 0.7);
    color: #fff;
    border: none;
    border-radius: 50%;
    font-size: 14px;
    line-height: 14px;
    padding: 0;
    cursor: pointer;
  }
  .ref-add {
    width: 60px;
    height: 60px;
    border: 1px dashed #3a3f4a;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    font-size: 22px;
    cursor: pointer;
  }
  .ref-add:hover { color: #c5c8cf; border-color: #4a5160; }
  .ref-add input[type="file"] { display: none; }
</style>
