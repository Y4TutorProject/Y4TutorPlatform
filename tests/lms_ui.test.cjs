const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function screen(connection = null) {
  const redirects = [];
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
      value: "", textContent: "", hidden: false, disabled: false, events: {},
      addEventListener(event, callback) { this.events[event] = callback; },
    });
    return nodes.get(id);
  }
  const form = node("lms-form");
  form.elements = {
    provider: node("lms-provider"), api_key: node("lms-key"),
    base_url: node("lms-url"), enabled: node("lms-enabled"),
  };
  form.querySelector = () => node("save-button");
  form.reportValidity = () => true;
  const context = vm.createContext({
    document: { body: { dataset: {} }, getElementById: node },
    window: { location: { replace(url) { redirects.push(url); } } },
    fetch: async (url) => ({ ok: true, json: async () =>
      url.endsWith("/auth/csrf") ? { csrf_token: "token" } : { connection } }),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend_shared/static/auth.js"), "utf8"), context);
  return { node, context, redirects };
}

test("Moodle fields require an explicit selection and disappear for other systems", async () => {
  const { node, context } = screen();
  await context.setupLMSImport("college-id");
  assert.equal(node("moodle-settings").hidden, true);
  assert.equal(node("moodle-settings").disabled, true);
  node("lms-provider").value = "moodle";
  node("lms-provider").events.change();
  assert.equal(node("moodle-settings").hidden, false);
  assert.equal(node("moodle-settings").disabled, false);
  node("lms-key").value = "secret";
  node("lms-provider").value = "blackboard";
  node("lms-provider").events.change();
  assert.equal(node("moodle-settings").hidden, true);
  assert.equal(node("moodle-settings").disabled, true);
  assert.equal(node("lms-provider-help").hidden, false);
  assert.equal(node("lms-key").value, "");
  node("lms-provider").value = "";
  node("lms-provider").events.change();
  assert.equal(node("lms-provider-help").hidden, true);
});

for (const stage of ["load", "save", "sync"]) {
  test(`Expired session during ${stage} returns to sign in and disables Moodle actions`, async () => {
    const { node, context, redirects } = screen({
      provider: "moodle", base_url: "https://college.edu", enabled: true,
      next_sync_at: "2026-11-03T02:00:00Z", timezone: "Europe/Dublin",
    });
    const rejectSession = () => {
      context.fetch = async (url) => ({
        ok: url.endsWith("/auth/csrf"), status: url.endsWith("/auth/csrf") ? 200 : 401,
        json: async () => url.endsWith("/auth/csrf")
          ? { csrf_token: "anonymous-session-token" } : { error: "Authentication required." },
      });
    };
    if (stage === "load") rejectSession();
    await context.setupLMSImport("college-id");
    if (stage !== "load") {
      rejectSession();
      node("lms-key").value = "private-key";
      if (stage === "save") await node("lms-form").events.submit({ preventDefault() {} });
      else await node("lms-sync-button").events.click();
    }
    assert.deepEqual(redirects, ["/login"]);
    assert.equal(node("lms-key").value, "");
    assert.equal(node("save-button").disabled, true);
    assert.equal(node("lms-sync-button").disabled, true);
    assert.match(node("lms-status").textContent, /session has expired/);
  });
}

test("A previously saved Moodle selection restores its fields without the API key", async () => {
  const { node, context } = screen({
    provider: "moodle", base_url: "https://college.edu", enabled: true,
    next_sync_at: "2026-11-03T02:00:00Z", timezone: "Europe/Dublin",
  });
  await context.setupLMSImport("college-id");
  assert.equal(node("lms-provider").value, "moodle");
  assert.equal(node("moodle-settings").hidden, false);
  assert.equal(node("lms-url").value, "https://college.edu");
  assert.equal(node("lms-key").value, "");
  assert.equal(node("lms-sync-button").disabled, false);
});
