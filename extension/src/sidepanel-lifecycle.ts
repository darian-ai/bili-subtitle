import { isSupportedVideoUrl } from "./video-context";

export interface SidePanelConfiguration {
  enabled: boolean;
  path?: string;
}

export function sidePanelPath(tabId: number): string {
  return `sidepanel.html?tabId=${tabId}`;
}

export function sidePanelConfiguration(
  tabId: number,
  url: string | undefined,
): SidePanelConfiguration {
  return isSupportedVideoUrl(url)
    ? { enabled: true, path: sidePanelPath(tabId) }
    : { enabled: false };
}
