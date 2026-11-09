const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
    constructor(tag) {
        this.tagName = tag;
        this.children = [];
        this.attributes = {};
        this.dataset = {};
        this.textContent = "";
    }

    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, callback) { this[name] = callback; }
    querySelector(selector) { return selector === ".module-name" ? this.name : null; }
    get childElementCount() { return this.children.length; }
}

function dashboard(fetch) {
    const buttons = ["module-1", "module-2"].map((id, index) => {
        const button = new Element("button");
        button.dataset.module = id;
        button.name = new Element("span");
        button.name.textContent = `Module ${index + 1}`;
        return button;
    });
    const results = new Element("div");
    const selected = new Element("p");
    const document = {
        addEventListener: (_, callback) => callback(),
        querySelectorAll: () => buttons,
        getElementById: id => id === "tutor-results" ? results : selected,
        createElement: tag => new Element(tag)
    };
    const code = fs.readFileSync(path.join(__dirname, "..", "frontend_shared", "static", "dashboard.js"), "utf8");
    vm.runInNewContext(code, { document, fetch, console: { error() {} } });
    return { buttons, results, selected };
}

test("renders tutor cards and preference pills", async () => {
    const ui = dashboard(async url => {
        assert.equal(url, "/api/dashboard/get_tutors?module_id=module-1");
        return { ok: true, json: async () => ({ tutors: [{
            username: "<Tutor>",
            preferences: { visual: 8, reading_writing: 5 }
        }] }) };
    });
    await ui.buttons[0].click();
    assert.equal(ui.buttons[0].attributes["aria-pressed"], "true");
    assert.equal(ui.selected.textContent, "Module 1");
    const card = ui.results.children[0].children[0];
    assert.equal(card.children[0].children[1].children[1].textContent, "<Tutor>");
    assert.deepEqual(card.children[1].children[1].children.map(chip => chip.textContent), [
        "Visual \u00b7 8/10", "Reading & writing \u00b7 5/10"
    ]);
    assert.equal(card.children[2].disabled, true);
    assert.equal(ui.results.attributes["aria-busy"], "false");
});

test("renders empty and failure states", async () => {
    const ui = dashboard(async url => url.endsWith("module-1")
        ? { ok: true, json: async () => ({ tutors: [] }) }
        : { ok: false, status: 502 });
    await ui.buttons[0].click();
    assert.equal(ui.results.children[0].children[0].textContent, "No tutors found");
    await ui.buttons[1].click();
    assert.equal(ui.results.children[0].children[0].textContent, "Couldn't load tutors");
    assert.equal(ui.buttons[0].attributes["aria-pressed"], "false");
    assert.equal(ui.results.attributes["aria-busy"], "false");
});

test("ignores an older response after selecting another module", async () => {
    let finishFirst;
    const ui = dashboard(url => url.endsWith("module-1")
        ? new Promise(resolve => { finishFirst = resolve; })
        : Promise.resolve({ ok: true, json: async () => ({ tutors: [] }) }));
    const first = ui.buttons[0].click();
    await ui.buttons[1].click();
    finishFirst({ ok: true, json: async () => ({ tutors: [{ username: "Outdated" }] }) });
    await first;
    assert.equal(ui.selected.textContent, "Module 2");
    assert.equal(ui.results.children[0].children[0].textContent, "No tutors found");
});
