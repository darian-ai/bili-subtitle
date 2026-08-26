import type { VideoDomIdentity, VideoDomSnapshot, VideoPodSnapshot } from "./video-context";

const BVID = /^BV[A-Za-z0-9]{10}$/;
const CID = /^\d+$/;

function positiveInteger(value: string | null): number | undefined {
  if (value === null || !/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function metadataIdentity(value: string | null): VideoDomIdentity | undefined {
  if (!value) return undefined;
  try {
    const parsed = new URL(value, "https://www.bilibili.com");
    const pathBvid = /^\/video\/(BV[A-Za-z0-9]{10})(?:\/|$)/.exec(parsed.pathname)?.[1];
    const queryBvid = parsed.searchParams.get("bvid") ?? undefined;
    const bvid = pathBvid ?? queryBvid;
    if (!bvid || !BVID.test(bvid)) return undefined;
    const pageValue = parsed.searchParams.get("page") ?? parsed.searchParams.get("p");
    const page = pageValue === null ? 1 : positiveInteger(pageValue);
    return page === undefined ? undefined : { bvid, page };
  } catch {
    return undefined;
  }
}

function readMetadata(document: Document): Pick<VideoDomSnapshot, "metadata" | "metadataConflict"> {
  const values = [
    document.querySelector<HTMLMetaElement>('meta[property="og:video"]')?.content ?? null,
    document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href ?? null,
    document.querySelector<HTMLMetaElement>('meta[property="og:url"]')?.content ?? null,
  ];
  const identity = values.map(metadataIdentity).find((value) => value !== undefined);
  return identity === undefined ? {} : { metadata: identity };
}

function playerPage(document: Document): { page?: number; cid?: string } {
  const active = document.querySelector<HTMLElement>(
    ".bpx-player-ctrl-eplist-multi-menu-item.bpx-state-multi-active-item",
  );
  if (!active?.parentElement) return {};
  const siblings = [...active.parentElement.children].filter((item) =>
    item.matches(".bpx-player-ctrl-eplist-multi-menu-item"));
  const index = siblings.indexOf(active);
  const cid = active.dataset.cid;
  return {
    ...(index < 0 ? {} : { page: index + 1 }),
    ...(cid && CID.test(cid) ? { cid } : {}),
  };
}

function collectionAmount(container: HTMLElement): { index?: number; total?: number } {
  const text = container.querySelector<HTMLElement>(".video-pod__header .amt, .amt")?.textContent ?? "";
  const match = /(\d+)\s*\/\s*(\d+)/.exec(text);
  const index = positiveInteger(match?.[1] ?? null);
  const total = positiveInteger(match?.[2] ?? null);
  return index !== undefined && total !== undefined && index <= total ? { index, total } : {};
}

function readPod(document: Document): VideoPodSnapshot | undefined {
  const container = document.querySelector<HTMLElement>(".video-pod");
  if (!container) return undefined;
  const items = [...container.querySelectorAll<HTMLElement>(".video-pod__item")];
  if (!items.length) return { kind: "loading" };
  const player = playerPage(document);
  const collection = items.some((item) => BVID.test(item.dataset.key ?? ""));

  if (collection) {
    const selected = items.find((item) =>
      item.matches(".active")
      || item.querySelector(".head.active, .simple-base-item.active") !== null);
    if (!selected) return { kind: "collection" };
    const pages = [...selected.querySelectorAll<HTMLElement>(".page-item")];
    const selectedPageIndex = pages.findIndex((item) => item.classList.contains("active"));
    const selectedPage = pages.length === 0 ? 1
      : selectedPageIndex < 0 ? undefined : selectedPageIndex + 1;
    const amount = collectionAmount(container);
    const selectedBvid = selected.dataset.key;
    return {
      kind: "collection",
      ...(selectedBvid && BVID.test(selectedBvid) ? { selectedBvid } : {}),
      ...(selectedPage === undefined ? {} : { selectedPage }),
      multiplePages: pages.length > 1,
      ...(player.page === undefined ? {} : { playerPage: player.page }),
      ...(amount.index === undefined ? {} : { collectionIndex: amount.index }),
      ...(amount.total === undefined ? {} : { collectionTotal: amount.total }),
    };
  }

  const selectedIndex = items.findIndex((item) => item.classList.contains("active"));
  if (selectedIndex < 0) return { kind: "pages" };
  const selectedCid = items[selectedIndex]!.dataset.key;
  return {
    kind: "pages",
    selectedPage: selectedIndex + 1,
    ...(selectedCid && CID.test(selectedCid) ? { selectedCid } : {}),
    ...(player.page === undefined ? {} : { playerPage: player.page }),
    ...(player.cid === undefined ? {} : { playerCid: player.cid }),
  };
}

export function readVideoDomSnapshot(document: Document): VideoDomSnapshot {
  const metadata = readMetadata(document);
  const pod = readPod(document);
  return { ...metadata, ...(pod === undefined ? {} : { pod }) };
}
