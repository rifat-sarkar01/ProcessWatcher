import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { expect, test } from "@playwright/test";

import { TINY_WEBM } from "./fixtures/media";

/**
 * G5 extra: byte-range seeking in real Chromium/Edge.
 *
 * The fixture API (`mock-api.ts`) answers every media request with a full 200, so Range
 * is never exercised there. This spec serves the same tiny H.264 clip from a local
 * loopback server that implements single-range requests, then checks both the protocol
 * (206 + Content-Range) and that the browser can seek a real `<video>` element.
 */

interface LogEntry {
  status: number;
  range: string | undefined;
}

let server: Server;
let baseURL: string;
let logs: LogEntry[] = [];

test.beforeAll(async () => {
  server = createServer((request, response) => {
    response.setHeader("Accept-Ranges", "bytes");
    response.setHeader("Access-Control-Allow-Origin", "*");
    response.setHeader("Access-Control-Allow-Headers", "Range");
    response.setHeader("Access-Control-Expose-Headers", "Content-Range");

    if (request.url === "/" || request.url === "/index.html") {
      response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      response.end(
        '<!doctype html><html><body><video id="clip" src="/clip.webm" ' +
          'preload="auto" muted></video></body></html>',
      );
      return;
    }

    response.setHeader("Content-Type", "video/webm");

    const range = request.headers.range;
    if (!range) {
      logs.push({ status: 200, range });
      response.writeHead(200, { "Content-Length": TINY_WEBM.length });
      response.end(TINY_WEBM);
      return;
    }

    const match = /^bytes=(\d*)-(\d*)$/.exec(range);
    if (!match) {
      logs.push({ status: 416, range });
      response.writeHead(416, { "Content-Range": `bytes */${TINY_WEBM.length}` });
      response.end();
      return;
    }
    const start = match[1] ? Number(match[1]) : 0;
    const requestedEnd = match[2] ? Number(match[2]) : TINY_WEBM.length - 1;
    const end = Math.min(requestedEnd, TINY_WEBM.length - 1);
    if (start >= TINY_WEBM.length || start > end) {
      logs.push({ status: 416, range });
      response.writeHead(416, { "Content-Range": `bytes */${TINY_WEBM.length}` });
      response.end();
      return;
    }

    logs.push({ status: 206, range });
    response.writeHead(206, {
      "Content-Range": `bytes ${start}-${end}/${TINY_WEBM.length}`,
      "Content-Length": end - start + 1,
    });
    response.end(TINY_WEBM.subarray(start, end + 1));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  baseURL = `http://127.0.0.1:${address.port}`;
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test("serves byte ranges with 206 and Content-Range", async ({ request }) => {
  const response = await request.get(`${baseURL}/clip.webm`, {
    headers: { Range: "bytes=0-9" },
  });

  expect(response.status()).toBe(206);
  expect(response.headers()["content-range"]).toBe(`bytes 0-9/${TINY_WEBM.length}`);
  expect(response.headers()["accept-ranges"]).toBe("bytes");
  expect((await response.body()).length).toBe(10);
});

test("the browser seeks a real video over a range request", async ({ page }) => {
  logs = [];
  await page.goto(`${baseURL}/`);

  const result = await page.evaluate(async () => {
    const video = document.querySelector("video");
    if (!video) throw new Error("video element missing");
    video.load();

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("video metadata timed out")), 10_000);
      video.onloadedmetadata = () => {
        clearTimeout(timer);
        resolve();
      };
      video.onerror = () => {
        clearTimeout(timer);
        reject(new Error("video failed to load"));
      };
    });
    video.pause();
    const target = Math.min(0.5, video.duration / 2);
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("seek timed out")), 10_000);
      video.onseeked = () => {
        clearTimeout(timer);
        resolve();
      };
      video.currentTime = target;
    });
    return { duration: video.duration, currentTime: video.currentTime };
  });

  expect(result.duration).toBeGreaterThan(0);
  expect(result.currentTime).toBeGreaterThan(0);
  expect(logs.some((entry) => entry.status === 206 && entry.range)).toBe(true);
});
