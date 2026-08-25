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

test("a multi-BV video pod exposes one stable active BVID and collection index", async ({ page }) => {
  await page.setContent(`<section class="video-pod__list">
    <div class="video-pod__item" data-key="BV1xx411c7mD"><button class="simple-base-item">一</button></div>
    <div class="video-pod__item" data-key="BV1yy411c7mD"><button class="simple-base-item active">二</button></div>
    <div class="video-pod__item" data-key="BV1zz411c7mD"><button class="simple-base-item">三</button></div>
  </section><ol><li></li><li class="bpx-state-multi-active-item"></li><li></li></ol>`);
  const identity = await page.evaluate(() => {
    const items = [...document.querySelectorAll<HTMLElement>(".video-pod__item")];
    const index = items.findIndex((item) => item.querySelector(".simple-base-item.active"));
    return { bvid: items[index]?.dataset.key, index: index + 1, total: items.length };
  });
  expect(identity).toEqual({ bvid: "BV1yy411c7mD", index: 2, total: 3 });
});
