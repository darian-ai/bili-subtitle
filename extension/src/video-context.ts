export interface VideoContext {
  supported: boolean;
  bvid?: string;
  page?: number;
  currentTimeMs: number;
}

export function parseVideoContext(url: string, currentTimeSeconds = 0): VideoContext {
  const parsed = new URL(url);
  const match = /^\/video\/(BV[A-Za-z0-9]{10})(?:\/|$)/.exec(parsed.pathname);
  if (parsed.hostname !== "www.bilibili.com" || !match?.[1]) {
    return { supported: false, currentTimeMs: Math.max(0, Math.round(currentTimeSeconds * 1000)) };
  }
  const rawPage = Number.parseInt(parsed.searchParams.get("p") ?? "1", 10);
  return {
    supported: true,
    bvid: match[1],
    page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1,
    currentTimeMs: Math.max(0, Math.round(currentTimeSeconds * 1000))
  };
}

export function activeChapter<T extends { start_ms: number; end_ms: number }>(
  chapters: T[],
  currentTimeMs: number
): T | undefined {
  return chapters.find((chapter) => currentTimeMs >= chapter.start_ms && currentTimeMs <= chapter.end_ms);
}
