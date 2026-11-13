const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function screen({ onboarding = true, admin = false, failure = null, kind = null } = {}) {
  const redirects = [];
  const calls = [];
  const status = { focus() {} };
  const button = { disabled: false };
  const values = {};
  const form = {
    dataset: { onboarding: String(onboarding), ...(kind && { kind }) }, events: {},
    elements: Object.fromEntries(["visual", "auditory", "reading_writing", "kinesthetic"]
      .map((key, index) => {
        values[`value-${key}`] = { textContent: String(index ? 10 : 0) };
        return [key, { value: String(index ? 10 : 0), events: {},
          addEventListener(event, callback) { this.events[event] = callback; } }];
      })),
    querySelector() { return button; }, reportValidity() { return true; },
    setAttribute() {}, removeAttribute() {},
    addEventListener(event, callback) { this.events[event] = callback; },
  };
  const context = vm.createContext({
    document: { body: { dataset: { page: "preferences" } },
      getElementById(id) { return id === "form-status" ? status : id === "preferences-form" ? form : values[id]; } },
    window: { location: { assign(url) { redirects.push(url); }, replace(url) { redirects.push(url); } } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const csrf = url.endsWith("/auth/csrf");
      return { ok: csrf || !failure, status: failure,
        json: async () => csrf ? { csrf_token: "token" } : failure ? { error: "Save failed" } :
          { user: { roles: [admin ? "college_admin" : "student"], college_id: null } } };
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend_shared/static/auth.js"), "utf8"), context);
  return { redirects, calls, status, button, values, form,
    submit: () => form.events.submit({ preventDefault() {} }) };
}

test("Moving a slider updates its displayed value and submitted rating", async () => {
  const ui = screen();
  ui.form.elements.visual.value = "7";
  ui.form.elements.visual.events.input();
  assert.equal(ui.values["value-visual"].textContent, "7");
  await ui.submit();
  assert.equal(JSON.parse(ui.calls[1].options.body).preferences.visual, 7);
});

test("Onboarding saves all four numeric ratings with CSRF and continues to dashboard", async () => {
  const ui = screen();
  await ui.submit();
  const save = ui.calls[1];
  assert.equal(save.url, "/api/users/users/me/preferences");
  assert.equal(save.options.headers["X-CSRFToken"], "token");
  assert.deepEqual(JSON.parse(save.options.body).preferences,
    { visual: 0, auditory: 10, reading_writing: 10, kinesthetic: 10 });
  assert.deepEqual(ui.redirects, ["/dashboard"]);
});

test("Administrators continue to college setup after preferences", async () => {
  const ui = screen({ admin: true });
  await ui.submit();
  assert.deepEqual(ui.redirects, ["/register-college"]);
});

test("Later edits stay on the page and confirm the save", async () => {
  const ui = screen({ onboarding: false });
  await ui.submit();
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.status.textContent, "Your learning preferences have been saved.");
});

test("Teaching preferences post to the teaching endpoint and confirm the save", async () => {
  const ui = screen({ onboarding: false, kind: "teaching" });
  await ui.submit();
  assert.equal(ui.calls[1].url, "/api/users/users/me/teaching_preferences");
  assert.deepEqual(JSON.parse(ui.calls[1].options.body).preferences,
    { visual: 0, auditory: 10, reading_writing: 10, kinesthetic: 10 });
  assert.equal(ui.status.textContent, "Your teaching preferences have been saved.");
});

test("Unknown preference kinds fall back to learning preferences", async () => {
  const ui = screen({ onboarding: false, kind: "other" });
  await ui.submit();
  assert.equal(ui.calls[1].url, "/api/users/users/me/preferences");
});

test("Failed save keeps setup open and allows retry", async () => {
  const ui = screen({ failure: 503 });
  await ui.submit();
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.status.textContent, "Save failed");
  assert.equal(ui.button.disabled, false);
});

test("Expired sessions return to login", async () => {
  const ui = screen({ failure: 401 });
  await ui.submit();
  assert.deepEqual(ui.redirects, ["/login"]);
});
