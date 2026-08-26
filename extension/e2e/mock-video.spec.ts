import { expect, test } from "@playwright/test";

test("mock video page changes P by SPA navigation without automatic network or pause", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.route("https://www.bilibili.com/**", (route) => route.fulfill({
    contentType: "text/html",
    body: `<video id="player"></video><button id="navigate">P2</button>
    <script>
      const video = document.querySelector('video');
      let pausedByApp = false;
      video.addEventListener('pause', () => pausedByApp = true);
      document.querySelector('button').onclick = () => history.pushState({}, '', '?p=2');
      window.result = () => ({ p: new URL(location.href).searchParams.get('p'), pausedByApp });
    </script>`
  }));
  await page.goto("https://www.bilibili.com/video/BV1xx411c7mD?p=1");
  const before = requests.length;
  await page.click("#navigate");
  await expect.poll(() => page.evaluate(() => (window as any).result().p)).toBe("2");
  expect(await page.evaluate(() => (window as any).result().pausedByApp)).toBe(false);
  expect(requests.length).toBe(before);
});

test("evidence seek stays within two seconds", async ({ page }) => {
  await page.setContent(`<video id="player"></video><script>
    const video = document.querySelector('video');
    window.seek = (ms) => { video.currentTime = ms / 1000; return video.currentTime * 1000; };
  </script>`);
  const actual = await page.evaluate(() => (window as any).seek(12_345));
  expect(Math.abs(actual - 12_345)).toBeLessThanOrEqual(2_000);
});

test("a collection item exposes its global position and inner P", async ({ page }) => {
  await page.setContent(`<section class="video-pod">
    <header class="video-pod__header"><span class="amt">（30/64）</span></header>
    <div class="video-pod__item" data-key="BV1xx411c7mD"><button class="head">一</button></div>
    <div class="video-pod__item" data-key="BV1yy411c7mD"><button class="head active">二</button>
      <button class="page-item">P1</button><button class="page-item active">P2</button></div>
    <div class="video-pod__item" data-key="BV1zz411c7mD"><button class="head">三</button></div>
  </section><ol><li class="bpx-player-ctrl-eplist-multi-menu-item"></li>
    <li class="bpx-player-ctrl-eplist-multi-menu-item bpx-state-multi-active-item"></li></ol>`);
  const identity = await page.evaluate(() => {
    const items = [...document.querySelectorAll<HTMLElement>(".video-pod__item")];
    const selected = items.find((item) => item.querySelector(".head.active"));
    const pages = [...(selected?.querySelectorAll(".page-item") ?? [])];
    const pageIndex = pages.findIndex((item) => item.classList.contains("active"));
    const amount = document.querySelector(".amt")?.textContent?.match(/(\d+)\/(\d+)/);
    return { bvid: selected?.dataset.key, page: pageIndex + 1,
      collectionIndex: Number(amount?.[1]), collectionTotal: Number(amount?.[2]) };
  });
  expect(identity).toEqual({ bvid: "BV1yy411c7mD", page: 2,
    collectionIndex: 30, collectionTotal: 64 });
});
