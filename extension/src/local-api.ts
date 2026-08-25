import type { CancelablePromise } from "./api";

export class LocalApiTimeoutError extends Error {
  constructor() {
    super("本地服务请求超时。");
    this.name = "LocalApiTimeoutError";
  }
}

export function localApi<T>(request: CancelablePromise<T>, timeoutMs = 15_000): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      request.cancel();
      reject(new LocalApiTimeoutError());
    }, timeoutMs);
    request.then(resolve, reject).finally(() => window.clearTimeout(timer));
  });
}
