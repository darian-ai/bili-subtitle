import { resolveVideoContext, type VideoPodSnapshot } from "../src/video-context";

function videoPodSnapshot(): VideoPodSnapshot | undefined {
  const items = [...document.querySelectorAll<HTMLElement>(".video-pod__item")];
  if (!items.length) return undefined;
  const selectedIndex = items.findIndex((item) =>
    item.matches(".active, .simple-base-item.active")
    || item.querySelector(".active, .simple-base-item.active") !== null);
  if (selectedIndex < 0) return {};
  const selected = items[selectedIndex]!;
  const distinctBvidCount = new Set(items.map((item) => item.dataset.key)
    .filter((value): value is string => /^BV[A-Za-z0-9]{10}$/.test(value ?? ""))).size;
  const playerItems = [...document.querySelectorAll<HTMLElement>(".bpx-state-multi-list li, .bpx-state-multi-item")];
  let playerIndex = playerItems.findIndex((item) => item.classList.contains("bpx-state-multi-active-item"));
  if (playerIndex < 0) {
    const activePlayer = document.querySelector<HTMLElement>(".bpx-state-multi-active-item");
    if (activePlayer?.parentElement) {
      playerIndex = [...activePlayer.parentElement.children].indexOf(activePlayer);
    }
  }
  return {
    ...(selected.dataset.key ? { selectedBvid: selected.dataset.key } : {}),
    selectedIndex, total: items.length, distinctBvidCount,
    ...(playerIndex < 0 ? {} : { playerIndex }),
  };
}

function context() {
  return resolveVideoContext(
    location.href,
    document.querySelector<HTMLVideoElement>("video")?.currentTime ?? 0,
    videoPodSnapshot(),
  );
}

export default defineContentScript({
  matches: ["https://www.bilibili.com/video/*"],
  main() {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (message?.type === "video-context") {
        sendResponse(context());
      }
      if (message?.type === "seek" && typeof message.timestampMs === "number") {
        const video = document.querySelector<HTMLVideoElement>("video");
        if (video) {
          video.currentTime = Math.max(0, message.timestampMs / 1000);
          sendResponse({ ok: true, currentTimeMs: Math.round(video.currentTime * 1000) });
        } else {
          sendResponse({ ok: false });
        }
      }
      return true;
    });

    let previous = "";
    let scheduled: number | undefined;
    const notifyNavigation = () => {
      if (scheduled !== undefined) return;
      scheduled = window.setTimeout(() => {
        scheduled = undefined;
        const next = context();
        const fingerprint = JSON.stringify({
          supported: next.supported, bvid: next.bvid, page: next.page,
          identity_state: next.identity_state, identity_evidence: next.identity_evidence,
          collection_index: next.collection_index, collection_total: next.collection_total,
        });
        if (previous === fingerprint) return;
        previous = fingerprint;
        chrome.runtime.sendMessage({ type: "content-video-navigation", context: next }).catch(() => undefined);
      }, 100);
    };
    window.addEventListener("popstate", notifyNavigation);
    const observer = new MutationObserver(notifyNavigation);
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true,
      attributeFilter: ["class", "data-key"] });
    notifyNavigation();
  }
});
