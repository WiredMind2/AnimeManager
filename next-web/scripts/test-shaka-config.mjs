import assert from "node:assert/strict";

function buildShakaConfig(resume) {
  return {
    streaming: {
      segmentPrefetchLimit: resume ? 0 : 2,
    },
  };
}

function loadStartTimeFromPayload(payload) {
  const start = Number(payload.playback_start_seconds ?? 0);
  return Number.isFinite(start) && start > 0 ? start : undefined;
}

function testResumeConfig() {
  const cfg = buildShakaConfig(true);
  assert.equal(cfg.streaming.segmentPrefetchLimit, 0, "resume must disable segment prefetch");
}

function testFreshStartConfig() {
  const cfg = buildShakaConfig(false);
  assert.equal(cfg.streaming.segmentPrefetchLimit, 2, "fresh start may prefetch");
}

function testLoadStartTime() {
  assert.equal(loadStartTimeFromPayload({ playback_start_seconds: 1420 }), 1420);
  assert.equal(loadStartTimeFromPayload({ playback_start_seconds: 0 }), undefined);
  assert.equal(loadStartTimeFromPayload({}), undefined);
}

testResumeConfig();
testFreshStartConfig();
testLoadStartTime();
console.log("shaka-config: ok");
