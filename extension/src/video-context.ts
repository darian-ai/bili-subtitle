export interface VideoContext {
  supported: boolean;
  bvid?: string;
  page?: number;
  identity_state?: "resolved" | "transitioning" | "ambiguous";
  identity_evidence?: "url_page" | "video_pod_page" | "video_pod_item" | "single_video";
  collection_index?: number;
  collection_total?: number;
  currentTimeMs: number;
}

export interface VideoDomIdentity { bvid: string; page: number }

export type VideoPodSnapshot =
  | { kind: "loading" }
  | {
    kind: "pages";
    selectedPage?: number;
    selectedCid?: string;
    playerPage?: number;
    playerCid?: string;
  }
  | {
    kind: "collection";
    selectedBvid?: string;
    selectedPage?: number;
    multiplePages?: boolean;
    playerPage?: number;
    playerTotal?: number;
    collectionIndex?: number;
    collectionTotal?: number;
  };

export interface VideoDomSnapshot {
  metadata?: VideoDomIdentity;
  metadataConflict?: boolean;
  pod?: VideoPodSnapshot;
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
  dom?: VideoDomSnapshot,
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
  if (dom?.metadataConflict) {
    return { supported: true, identity_state: "transitioning", currentTimeMs };
  }
  const metadataMismatch = dom?.metadata !== undefined
    && (dom.metadata.bvid !== match[1] || dom.metadata.page !== rawPage);
  const pod = dom?.pod;
  if (pod?.kind === "pages") {
    if (pod.selectedPage !== undefined && pod.selectedPage !== rawPage) {
      return { supported: true, identity_state: "transitioning", currentTimeMs };
    }
    if (pod.selectedPage !== undefined) {
      return {
        supported: true, bvid: match[1], page: pod.selectedPage,
        identity_state: "resolved", identity_evidence: "video_pod_page", currentTimeMs,
      };
    }
  }
  if (pod?.kind === "collection") {
    if (pod.selectedBvid !== undefined && pod.selectedPage !== undefined) {
      const conflict = pod.selectedBvid !== match[1] || pod.selectedPage !== rawPage;
      if (conflict) {
        return {
          supported: true, identity_state: "transitioning", currentTimeMs,
          ...(pod.collectionIndex === undefined ? {} : { collection_index: pod.collectionIndex }),
          ...(pod.collectionTotal === undefined ? {} : { collection_total: pod.collectionTotal }),
        };
      }
      return {
        supported: true, bvid: pod.selectedBvid, page: pod.selectedPage,
        identity_state: "resolved", identity_evidence: "video_pod_item",
        ...(pod.collectionIndex === undefined ? {} : { collection_index: pod.collectionIndex }),
        ...(pod.collectionTotal === undefined ? {} : { collection_total: pod.collectionTotal }),
        currentTimeMs,
      };
    }
  }
  if (metadataMismatch) {
    return { supported: true, identity_state: "transitioning", currentTimeMs };
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
