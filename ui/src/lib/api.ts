// Thin typed client for the FastAPI sidecar.

export const SERVER = "http://127.0.0.1:8767";

export type Health = { ok: boolean; project: string };

export type Character = {
  name: string;
  description: string;
  emotional_state: string;
};

export type Location = {
  name: string;
  setting_type: string;
  description: string;
  time_of_day: string;
};

export type VisualStyleInfo = {
  tone: string;
  lighting: string;
  atmosphere_keywords: string[];
};

export type Scene = {
  number: number;
  heading: string;
  location: Location;
  characters: Character[];
  action_descriptions: string[];
  dialogue: [string, string][];
  visual_style: VisualStyleInfo;
  transitions: string[];
  base_prompt: string;
};

export type StylePreset = {
  id: string;
  name: string;
  description: string;
  modifiers: string;
};

export type RenderResult = {
  render_id: string;
  status: string;
  image_url: string;
  full_prompt: string;
  backend: string;
  detail: string;
};

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${detail}`);
  }
  return (await resp.json()) as T;
}

export async function getHealth(): Promise<Health> {
  return jsonOrThrow(await fetch(`${SERVER}/healthz`));
}

export async function parseScript(text: string): Promise<Scene[]> {
  const r = await fetch(`${SERVER}/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const data = await jsonOrThrow<{ scenes: Scene[] }>(r);
  return data.scenes;
}

export async function parseShotList(payload: {
  text?: string;
  pdf_base64?: string;
}): Promise<Scene[]> {
  const r = await fetch(`${SERVER}/parse-shotlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await jsonOrThrow<{ scenes: Scene[] }>(r);
  return data.scenes;
}

export async function getStyles(): Promise<StylePreset[]> {
  return jsonOrThrow(await fetch(`${SERVER}/styles`));
}

export type GeneratedPromptResult = {
  text: string;
  model: string;
  elapsed_seconds: number;
};

export async function generatePromptForScene(opts: {
  heading: string;
  setting: string;
  time_of_day?: string;
  characters?: string[];
  description: string;
  model?: string;
}): Promise<GeneratedPromptResult> {
  const r = await fetch(`${SERVER}/generate-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  return jsonOrThrow(r);
}

export async function renderScene(opts: {
  scene_idx: number;
  prompt: string;
  style_id?: string;
  width?: number;
  height?: number;
  negative_prompt?: string;
  reference_images?: string[]; // base64 strings (no data: prefix)
}): Promise<RenderResult> {
  const r = await fetch(`${SERVER}/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  return jsonOrThrow(r);
}

export function renderImageUrl(rel: string): string {
  return `${SERVER}${rel}`;
}
