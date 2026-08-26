import { afterEach, describe, expect, it } from "vitest";
import { readVideoDomSnapshot } from "../src/bilibili-dom";

afterEach(() => {
  document.head.innerHTML = "";
  document.body.innerHTML = "";
});

function metadata(bvid: string, page: number): void {
  document.head.innerHTML = `
    <meta property="og:video" content="https://player.bilibili.com/player.html?bvid=${bvid}&page=${page}">
    <link rel="canonical" href="https://www.bilibili.com/video/${bvid}?p=${page}">
    <meta property="og:url" content="https://www.bilibili.com/video/${bvid}?p=${page}">
  `;
}

describe("Bilibili DOM snapshot", () => {
  it.each([
    { bvid: "BV1Y6Ju6vEeN", page: 41, total: 92, cidBase: 39124863600 },
    { bvid: "BV1DfrdByE2H", page: 4, total: 43, cidBase: 35394160500 },
  ])("reads numeric-CID P$page of a $total-page list", ({ bvid, page, total, cidBase }) => {
    metadata(bvid, page);
    const podItems = Array.from({ length: total }, (_, index) =>
      `<div class="video-pod__item${index === page - 1 ? " active" : ""}" data-key="${cidBase + index}"></div>`).join("");
    const playerItems = Array.from({ length: total }, (_, index) =>
      `<li class="bpx-player-ctrl-eplist-multi-menu-item${index === page - 1 ? " bpx-state-multi-active-item" : ""}" data-cid="${cidBase + index}"></li>`).join("");
    document.body.innerHTML = `<section class="video-pod"><div class="video-pod__list">${podItems}</div></section>
      <div class="bpx-state-multi-active-item">标题</div><ul>${playerItems}</ul>`;

    expect(readVideoDomSnapshot(document)).toEqual({
      metadata: { bvid, page },
      pod: { kind: "pages", selectedPage: page, selectedCid: String(cidBase + page - 1),
        playerPage: page, playerCid: String(cidBase + page - 1) },
    });
  });

  it("reads global collection position separately from the selected BV page", () => {
    metadata("BV1yANy6mEWe", 6);
    const pages = Array.from({ length: 7 }, (_, index) =>
      `<div class="page-item${index === 5 ? " active" : ""}"></div>`).join("");
    const playerItems = Array.from({ length: 7 }, (_, index) =>
      `<li class="bpx-player-ctrl-eplist-multi-menu-item${index === 5 ? " bpx-state-multi-active-item" : ""}" data-cid="${40000 + index}"></li>`).join("");
    document.body.innerHTML = `<section class="video-pod">
      <header class="video-pod__header"><span class="amt">（30/64）</span></header>
      <div class="video-pod__item" data-key="BV1yANy6mEWe"><div class="head active"></div>${pages}</div>
      <div class="video-pod__item" data-key="BV1qdbo6AEVQ"><div class="head"></div></div>
    </section><ul>${playerItems}</ul>`;

    expect(readVideoDomSnapshot(document)).toEqual({
      metadata: { bvid: "BV1yANy6mEWe", page: 6 },
      pod: { kind: "collection", selectedBvid: "BV1yANy6mEWe", selectedPage: 6,
        multiplePages: true, playerPage: 6, collectionIndex: 30, collectionTotal: 64 },
    });
  });

  it("reads a simple collection item whose nested base item is active", () => {
    metadata("BV1Y9u76aEdy", 1);
    document.body.innerHTML = `<section class="video-pod">
      <div class="video-pod__item simple" data-key="BV1other0000">
        <div class="single-p"><div class="simple-base-item normal"></div></div>
      </div>
      <div class="video-pod__item simple" data-key="BV1Y9u76aEdy">
        <div class="single-p"><div class="simple-base-item active normal"></div></div>
      </div>
    </section>`;

    expect(readVideoDomSnapshot(document)).toEqual({
      metadata: { bvid: "BV1Y9u76aEdy", page: 1 },
      pod: {
        kind: "collection", selectedBvid: "BV1Y9u76aEdy", selectedPage: 1,
        multiplePages: false,
      },
    });
  });

  it("uses primary og:video metadata despite stale secondary tags", () => {
    document.head.innerHTML = `
      <meta property="og:video" content="https://player.bilibili.com/player.html?bvid=BV1xx411c7mD&page=2">
      <link rel="canonical" href="https://www.bilibili.com/video/BV1xx411c7mD?p=1">`;
    expect(readVideoDomSnapshot(document)).toEqual({
      metadata: { bvid: "BV1xx411c7mD", page: 2 },
    });
  });

  it("reads a stable pod even when the player menu is absent", () => {
    metadata("BV1xx411c7mD", 2);
    document.body.innerHTML = `<section class="video-pod">
      <div class="video-pod__item" data-key="100"></div>
      <div class="video-pod__item active" data-key="200"></div>
    </section>`;
    expect(readVideoDomSnapshot(document)).toEqual({
      metadata: { bvid: "BV1xx411c7mD", page: 2 },
      pod: { kind: "pages", selectedPage: 2, selectedCid: "200" },
    });
  });
});
