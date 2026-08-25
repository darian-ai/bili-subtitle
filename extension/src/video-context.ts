export interface VideoContext {
  supported: boolean;
  bvid?: string;
  page?: number;
  identity_state?: "resolved" | "transitioning" | "ambiguous";
  identity_evidence?: "url_page" | "video_pod_item" | "single_video";
  collection_index?: number;
  collection_total?: number;
  currentTimeMs: number;
}

export interface VideoPodSnapshot {
  selectedBvid?: string;
  selectedIndex?: number;
  total?: number;
  playerIndex?: number;
}

export function isSupportedVideoUrl(url: string | undefined): boolean {
  if (!url) return false;
  try {
    return parseVideoContext(url).supported;
  } catch {
    return false;
  }
}

export function parseVideoContext(url: string, currentTimeSeconds = 0): VideoContext {
  return resolveVideoContext(url, currentTimeSeconds);
}

export function resolveVideoContext(
  url: string,
  currentTimeSeconds = 0,
  pod?: VideoPodSnapshot,
): VideoContext {
  const parsed = new URL(url);
  const match = /^\/video\/(BV[A-Za-z0-9]{10})(?:\/|$)/.exec(parsed.pathname);
  const currentTimeMs = Math.max(0, Math.round(currentTimeSeconds * 1000));
  if (parsed.hostname !== "www.bilibili.com" || !match?.[1]) {
    return { supported: false, currentTimeMs };
  }
  const pageValue = parsed.searchParams.get("p");
  const rawPage = pageValue === null ? 1 : Number.parseInt(pageValue, 10);
  if (!Number.isSafeInteger(rawPage) || rawPage < 1) {
    return { supported: true, identity_state: "ambiguous", currentTimeMs };
  }
  if (pod !== undefined && !pod.selectedBvid) {
    return { supported: true, identity_state: "transitioning", currentTimeMs };
  }
  if (pod?.selectedBvid) {
    const validPodBvid = /^BV[A-Za-z0-9]{10}$/.test(pod.selectedBvid);
    const indexConflict = pod.selectedIndex !== undefined && pod.playerIndex !== undefined
      && pod.selectedIndex !== pod.playerIndex;
    if (!validPodBvid) return { supported: true, identity_state: "ambiguous", currentTimeMs };
    if (match[1] !== pod.selectedBvid || indexConflict) {
      return {
        supported: true, identity_state: "transitioning", currentTimeMs,
        ...(pod.selectedIndex === undefined ? {} : { collection_index: pod.selectedIndex + 1 }),
        ...(pod.total === undefined ? {} : { collection_total: pod.total }),
      };
    }
    return {
      supported: true, bvid: pod.selectedBvid, page: rawPage,
      identity_state: "resolved", identity_evidence: "video_pod_item",
      ...(pod.selectedIndex === undefined ? {} : { collection_index: pod.selectedIndex + 1 }),
      ...(pod.total === undefined ? {} : { collection_total: pod.total }), currentTimeMs,
    };
  }
  return {
    supported: true,
    bvid: match[1],
    page: rawPage,
    identity_state: "resolved",
    identity_evidence: pageValue === null ? "single_video" : "url_page",
    currentTimeMs,
  };
}

export function activeChapter<T extends { start_ms: number; end_ms: number }>(
  chapters: T[],
  currentTimeMs: number
): T | undefined {
  return chapters.find((chapter) => currentTimeMs >= chapter.start_ms && currentTimeMs <= chapter.end_ms);
}

export function activeCue<T extends { start_ms: number; end_ms: number }>(
  cues: T[], currentTimeMs: number,
): T | undefined {
  return cues.filter((cue) =>
    currentTimeMs >= cue.start_ms && currentTimeMs < cue.end_ms).at(-1);
}
