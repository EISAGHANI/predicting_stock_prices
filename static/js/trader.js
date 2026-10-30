// Day Trader Lab: builds each skill's form from the catalog, runs it, and explains every step.
(function () {
    const CAT = JSON.parse(document.getElementById("catalogData").textContent);
    const SKILLS = CAT.skills;
    const byId = Object.fromEntries(SKILLS.map((s) => [s.id, s]));
    const EXPLAINERS = CAT.explainers.map((e) => ({ ...e, re: new RegExp(e.pattern) }));
    const HIGHLIGHT = new RegExp(CAT.explainers.map((e) => `(?:${e.pattern})`).join("|"), "g");
    const URL_RE = /https?:\/\/[^\s"'<>]+/g;

    const store = {
        get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
    };

    const ui = {
        mode: store.get("traderMode") === "live" ? "live" : "demo",
        skill: byId[location.hash.slice(1)] ? location.hash.slice(1) : "scanner",
        action: {},          // skill id -> chosen action id
        server: null,        // last /api/state answer
        clock: null,
        runs: {},            // "mode:skill" -> the last run's element
        running: false,
        redraw: [],          // charts to re-render on a theme change
    };

    // ---------- helpers ----------
    function h(tag, attrs, ...children) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (v === null || v === undefined || v === false) continue;
            if (k === "class") node.className = v;
            else if (k === "text") node.textContent = v;
            else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
            else node.setAttribute(k, v === true ? "" : v);
        }
        for (const c of children.flat(Infinity)) {
            if (c === null || c === undefined || c === false) continue;
            node.append(c instanceof Node ? c : document.createTextNode(String(c)));
        }
        return node;
    }
    const $ = (sel, root = document) => root.querySelector(sel);
    // replaceChildren that skips empty slots (the DOM's own would print "null").
    const fill = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
    const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const money = (v) => (typeof v === "number" ? "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "–");
    const pct = (v) => (v * 100).toFixed(1) + " %";
    const icon = (path) => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        svg.innerHTML = path;
        return svg;
    };
    const ICONS = {
        check: '<path d="M20 6 9 17l-5-5"/>',
        x: '<path d="M18 6 6 18M6 6l12 12"/>',
        play: '<path d="M6 4l14 8-14 8z"/>',
        stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
        file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
        arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
        info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
        warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    };

    async function api(path, body) {
        const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
        const res = await fetch("/trader/api/" + path, opts);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `The server answered ${res.status}.`);
        return data;
    }

    // New York wall time ("2026-10-30 09:30") -> the same moment in the visitor's own clock.
    function nyToLocal(ny) {
        const now = new Date();
        const offset = now - new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
        const d = new Date(new Date(ny.replace(" ", "T")).getTime() + offset);
        return d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
    }

    // ---------- mode, banner, state ----------
    document.querySelectorAll('input[name="mode"]').forEach((r) => {
        r.checked = r.value === ui.mode;
        r.addEventListener("change", () => {
            if (ui.running) { r.checked = false; document.querySelector(`input[name="mode"][value="${ui.mode}"]`).checked = true; return; }
            ui.mode = r.value;
            store.set("traderMode", ui.mode);
            refresh();
        });
    });

    function renderBanner() {
        const b = $("#modeBanner");
        b.className = "mode-banner mode-" + ui.mode;
        if (ui.mode === "demo") {
            fill(b, icon(ICONS.info), h("p", {},
                h("strong", { text: "Demo replay. " }),
                "Every skill reads real data recorded on Monday Oct 19 2026 and the clock is pinned to that day, so the whole TSLA trade can be walked through any time, with no internet. ",
                "Go through the steps in order: each one reads what the previous one saved."));
            return;
        }
        const c = ui.clock;
        const status = !c ? "" : c.open
            ? `The New York Stock Exchange is open now (${c.now_new_york.slice(11)} in New York). `
            : `The New York Stock Exchange is closed now (${c.reason}). It next opens ${c.next_open} New York time, which is ${nyToLocal(c.next_open)} your time. `;
        fill(b, icon(ICONS.info), h("p", {},
            h("strong", { text: "Live data. " }), status,
            "The skills read free, delayed public data right now. The intraday skills (scanner, entry timer) only find something while the market is open."));
    }

    async function refresh() {
        try { ui.server = await api("state?mode=" + ui.mode); } catch (e) { ui.server = null; }
        renderBanner();
        renderJourney();
        renderSkill();
        renderFiles();
    }

    // ---------- journey ----------
    function renderJourney() {
        const done = ui.server?.done || {};
        const steps = SKILLS.filter((s) => s.step);
        $("#journeySteps").replaceChildren(...steps.map((s) => h("li", {},
            h("button", {
                type: "button", class: "journey-step" + (s.id === ui.skill ? " active" : "") + (done[s.id] ? " done" : ""),
                "aria-current": s.id === ui.skill ? "step" : null, onclick: () => selectSkill(s.id),
            },
                h("span", { class: "journey-num" }, done[s.id] ? icon(ICONS.check) : String(s.step)),
                h("span", { class: "journey-name", text: s.name })))));
        $("#journeySide").replaceChildren(...SKILLS.filter((s) => !s.step).map((s) =>
            h("button", {
                type: "button", class: "side-chip" + (s.id === ui.skill ? " active" : "") + (done[s.id] ? " done" : ""),
                onclick: () => selectSkill(s.id),
            }, done[s.id] ? icon(ICONS.check) : null, s.name)));
    }

    function selectSkill(id, scroll = true) {
        if (ui.running) return;
        ui.skill = id;
        history.replaceState(null, "", "#" + id);
        renderJourney();
        renderSkill();
        if (scroll) $("#skillPanel").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ---------- skill panel ----------
    function availableActions(skill) {
        return skill.actions.filter((a) => a.modes.includes(ui.mode));
    }

    function renderSkill() {
        const skill = byId[ui.skill];
        const actions = availableActions(skill);
        if (!actions.some((a) => a.id === ui.action[skill.id])) ui.action[skill.id] = actions[0]?.id;
        const action = skill.actions.find((a) => a.id === ui.action[skill.id]);

        const tabs = h("div", { class: "action-tabs", role: "tablist", "aria-label": "What to do" },
            skill.actions.map((a) => {
                const ok = a.modes.includes(ui.mode);
                return h("button", {
                    type: "button", role: "tab", class: "action-tab" + (a.id === action?.id ? " active" : ""),
                    "aria-selected": a.id === action?.id ? "true" : "false", disabled: !ok || ui.running,
                    title: ok ? null : `Only in ${a.modes[0]} mode`,
                    onclick: () => { ui.action[skill.id] = a.id; renderSkill(); },
                }, a.label, ok ? null : h("span", { class: "tab-tag", text: a.modes[0] }));
            }));

        fill($("#skillPanel"), 
            h("header", { class: "skill-head" },
                h("span", { class: "skill-badge", text: skill.step ? `Step ${skill.step}` : "Tool" }),
                h("div", {},
                    h("h2", { text: skill.name }),
                    h("p", { class: "muted", text: skill.tagline }))),
            h("div", { class: "plain" }, h("span", { class: "plain-label", text: "In plain words" }), h("p", { text: skill.plain })),
            tabs,
            action ? renderAction(skill, action) : h("p", { class: "muted", text: "Nothing to run in this mode." }),
        );
        // A chart drawn while this panel was hidden may have missed a window resize.
        if (window.Plotly) document.querySelectorAll("#skillPanel .js-plotly-plot").forEach((el) => Plotly.Plots.resize(el));
    }

    function renderField(f) {
        const id = "f-" + f.name;
        const value = ui.mode === "demo" && f.demo_default !== null ? f.demo_default : f.default;
        let input;
        if (f.kind === "select") {
            input = h("select", { id, name: f.name },
                f.choices.map(([v, label]) => h("option", { value: v, selected: String(v) === String(value) }, label)));
        } else if (f.kind === "bool") {
            input = h("input", { id, name: f.name, type: "checkbox", checked: !!value });
            return h("label", { class: "field-check" }, input, h("span", {},
                h("span", { class: "check-label", text: f.label }), f.help ? h("span", { class: "help", text: f.help }) : null));
        } else {
            const type = { number: "number", int: "number", time: "time", date: "date" }[f.kind] || "text";
            input = h("input", {
                id, name: f.name, type, value: value ?? "", placeholder: f.placeholder || null,
                step: f.kind === "int" ? "1" : f.kind === "number" ? "any" : null,
                min: f.min, max: f.max, required: f.required,
                class: f.kind === "ticker" || f.kind === "tickers" ? "mono upper" : null,
                autocomplete: "off", spellcheck: "false",
            });
        }
        return h("label", { class: "field", for: id },
            h("span", { class: "field-label", text: f.label }),
            input, f.help ? h("span", { class: "help", text: f.help }) : null);
    }

    function renderAction(skill, action) {
        const fields = action.fields.filter((f) => f.modes.includes(ui.mode));
        const basic = fields.filter((f) => !f.advanced);
        const advanced = fields.filter((f) => f.advanced);
        const notes = [];
        if (ui.mode === "demo" && action.demo_note) notes.push(["info", action.demo_note]);
        if (ui.mode === "live" && action.slow) notes.push(["warn", action.slow]);
        const secMissing = !ui.server?.sec_ready;
        if (ui.mode === "live" && secMissing && (action.needs_sec || skill.id === "news")) {
            notes.push(["warn", action.needs_sec
                ? "This needs your name and email for the SEC. Add them in Settings first."
                : "SEC filings need your name and email in Settings. Without them you only get the headlines."]);
        }
        if (skill.id === "broker") notes.push(["info", "This app is not connected to any broker. Nothing here can buy or sell: it only keeps your paper log."]);

        const form = h("form", { class: "action-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); run(skill, action, form); } },
            h("p", { class: "action-summary", text: action.summary }),
            basic.length ? h("div", { class: "form-grid" }, basic.map(renderField)) : null,
            advanced.length ? h("details", { class: "advanced" }, h("summary", { text: "More options" }),
                h("div", { class: "form-grid" }, advanced.map(renderField))) : null,
            notes.map(([tone, text]) => h("p", { class: "note note-" + tone }, icon(ICONS[tone]), h("span", { text }))),
            h("div", { class: "form-actions" },
                h("button", { type: "submit", class: "btn btn-primary btn-sm", id: "runBtn", disabled: ui.running }, icon(ICONS.play), `Run: ${action.label}`),
                h("button", { type: "button", class: "btn btn-sm btn-danger", id: "stopBtn", hidden: !ui.running, onclick: stop }, icon(ICONS.stop), "Stop")),
        );

        const sources = ui.mode === "demo" ? ["Recorded data from Oct 19 2026 (no internet)"] : action.sources.length ? action.sources : ["Only files on this computer"];
        const fileChip = (p) => {
            const path = "trader/" + p;
            const exists = ui.server?.files.some((f) => f.path === path);
            return h("button", { type: "button", class: "file-chip" + (exists ? "" : " missing"), disabled: !exists,
                title: exists ? "Open it" : "Not created yet", onclick: () => openFile(path) }, icon(ICONS.file), path);
        };
        const uses = h("div", { class: "uses" },
            h("div", {}, h("span", { class: "uses-label", text: "Data from" }), h("div", { class: "uses-list" }, sources.map((s) => h("span", { class: "tag", text: s })))),
            action.reads.length ? h("div", {}, h("span", { class: "uses-label", text: "Reads" }), h("div", { class: "uses-list" }, action.reads.map(fileChip))) : null,
            action.writes.length ? h("div", {}, h("span", { class: "uses-label", text: "Saves" }), h("div", { class: "uses-list" }, action.writes.map(fileChip))) : null);

        const behind = h("div", { class: "behind" },
            h("h3", { text: "What happens behind the scenes" }),
            h("ol", { class: "behind-steps" }, action.steps.map((s) => h("li", { text: s }))),
            uses);

        const key = `${ui.mode}:${skill.id}`;
        const last = ui.runs[key] || h("div", { class: "run-slot" });
        ui.runs[key] = last;
        return h("div", { class: "action-body" }, h("div", { class: "action-grid" }, form, behind), last);
    }

    // ---------- running ----------
    function timelineStep(n, title) {
        const body = h("div", { class: "tl-body" });
        const li = h("li", { class: "tl-step pending" },
            h("span", { class: "tl-dot", text: String(n) }),
            h("div", { class: "tl-content" }, h("h4", { text: title }), body));
        return { li, body, set(state) { li.className = "tl-step " + state; } };
    }

    function highlight(line) {
        // Links first, then the phrases the explainers know about.
        const frag = document.createDocumentFragment();
        let pos = 0;
        const pushText = (text) => {
            let i = 0;
            for (const m of text.matchAll(HIGHLIGHT)) {
                if (!m[0]) continue;
                frag.append(text.slice(i, m.index));
                const ex = EXPLAINERS.find((e) => e.re.test(m[0]));
                frag.append(h("mark", { class: "hl hl-" + (ex?.tone || "info"), title: ex?.title || null, text: m[0] }));
                i = m.index + m[0].length;
            }
            frag.append(text.slice(i));
        };
        for (const m of line.matchAll(URL_RE)) {
            pushText(line.slice(pos, m.index));
            frag.append(h("a", { href: m[0], target: "_blank", rel: "noopener noreferrer", text: m[0] }));
            pos = m.index + m[0].length;
        }
        pushText(line.slice(pos));
        return frag;
    }

    async function run(skill, action, form) {
        if (ui.running) return;
        const values = {};
        for (const f of action.fields.filter((x) => x.modes.includes(ui.mode))) {
            const el = form.elements[f.name];
            values[f.name] = f.kind === "bool" ? el.checked : el.value;
        }

        const status = h("span", { class: "pill pill-run", text: "Running" });
        const elapsed = h("span", { class: "muted small num", text: "0 s" });
        const s1 = timelineStep(1, "Your choices");
        const s2 = timelineStep(2, "The exact command");
        const s3 = timelineStep(3, "Doing the work");
        const s4 = timelineStep(4, "Files saved");
        const s5 = timelineStep(5, "What this means");
        const log = h("pre", { class: "log", "aria-label": "What the skill printed" });
        const view = h("section", { class: "run", "aria-live": "polite" },
            h("header", { class: "run-head" },
                h("h3", {}, `${skill.name}: ${action.label}`),
                h("div", { class: "run-meta" }, elapsed, status)),
            h("ol", { class: "timeline" }, [s1, s2, s3, s4, s5].map((s) => s.li)));

        const slot = ui.runs[`${ui.mode}:${skill.id}`];
        slot.replaceChildren(view);
        view.scrollIntoView({ behavior: "smooth", block: "start" });
        setRunning(true);
        const t0 = Date.now();
        const timer = setInterval(() => (elapsed.textContent = Math.round((Date.now() - t0) / 1000) + " s"), 500);

        const output = [];
        let end = null, files = [], failure = null;
        try {
            const res = await fetch("/trader/api/run", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode: ui.mode, skill: skill.id, action: action.id, values }),
            });
            if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `The server answered ${res.status}.`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            for (;;) {
                const { value, done } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                let nl;
                while ((nl = buf.indexOf("\n")) >= 0) {
                    const ev = JSON.parse(buf.slice(0, nl));
                    buf = buf.slice(nl + 1);
                    if (ev.t === "start") {
                        fill(s1.body, ev.inputs.length
                            ? h("dl", { class: "inputs" }, ev.inputs.map((i) => [h("dt", { text: i.label }), h("dd", { text: i.value })]))
                            : h("p", { class: "muted", text: "No options: it runs on the saved files." }),
                            ui.mode === "demo" ? h("p", { class: "muted small", text: "Demo mode also adds the recorded data and pins the clock to Oct 19 2026." }) : null);
                        s1.set("done");
                        fill(s2.body, 
                            h("p", { class: "muted small", text: `The page runs this Python script for you, inside ${ev.folder}:` }),
                            h("pre", { class: "code cmd", text: ev.command }));
                        s2.set("done");
                        fill(s3.body, 
                            h("ol", { class: "behind-steps compact" }, action.steps.map((s) => h("li", { text: s }))),
                            h("p", { class: "muted small", text: "What the skill prints, line by line (highlighted words are explained in step 5):" }),
                            log);
                        s3.set("active");
                    } else if (ev.t === "line") {
                        output.push(ev.text);
                        const stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 24;
                        log.append(h("span", { class: ev.s === "err" ? "ln ln-err" : "ln" }, highlight(ev.text)), "\n");
                        if (stick) log.scrollTop = log.scrollHeight;
                    } else if (ev.t === "files") {
                        files = ev.files;
                    } else if (ev.t === "end") {
                        end = ev;
                    } else if (ev.t === "error") {
                        throw new Error(ev.message);
                    }
                }
            }
            if (!end) throw new Error("The connection closed before the skill finished.");
        } catch (e) {
            failure = e.message;
        } finally {
            clearInterval(timer);
            setRunning(false);
        }

        if (failure && !end) {
            // Refused before it started (bad input, busy), or broke off while running.
            const target = s3.li.classList.contains("active") ? s3 : s1;
            target.set("fail");
            target.body.append(h("p", { class: "note note-bad" }, icon(ICONS.x), h("span", { text: failure })));
            status.className = "pill pill-bad";
            status.textContent = "Did not run";
            if (/Settings/.test(failure)) target.body.append(h("button", { type: "button", class: "btn btn-sm btn-quiet", onclick: openSettings, text: "Open Settings" }));
            return;
        }

        if (!output.length) log.append(h("span", { class: "muted", text: "(it printed nothing)" }));
        const ok = end.code === 0;
        s3.set(end.cancelled || end.timed_out ? "fail" : ok ? "done" : "warn");
        status.className = "pill " + (end.cancelled || end.timed_out ? "pill-bad" : ok ? "pill-good" : "pill-warn");
        status.textContent = end.cancelled ? "Stopped" : end.timed_out ? "Timed out" : ok ? "Finished" : "Finished, see notes";
        elapsed.textContent = end.seconds + " s";

        fill(s4.body, files.length
            ? h("ul", { class: "saved" }, files.map((f) => h("li", {},
                h("span", { class: "change change-" + f.change, text: f.change }),
                f.change === "deleted" ? h("span", { class: "mono", text: f.path })
                    : h("button", { type: "button", class: "file-chip", onclick: () => openFile(f.path) }, icon(ICONS.file), f.path),
                h("span", { class: "muted small", text: FILE_ABOUT[f.path] ? " " + FILE_ABOUT[f.path].split(".")[0] + "." : "" }))))
            : h("p", { class: "muted", text: "Nothing was saved this time." }));
        s4.set("done");

        // What this means: the exit code, the phrases it printed, a visual of the main result, the next step.
        const text = output.join("\n");
        const codeText = end.cancelled ? "You stopped it." : end.timed_out ? "It ran too long and was stopped."
            : ok ? "It finished without problems."
            : action.exit_codes[String(end.code)] || (end.code === 2 ? "The skill did not accept one of the options (the reason is in the log)." : "It stopped with a problem. The last lines of the log say why.");
        const lastErr = !ok ? output.filter((l) => l.trim()).slice(-1)[0] : null;
        const seen = new Set();
        const cards = EXPLAINERS.filter((e) => e.re.test(text) && !seen.has(e.title) && seen.add(e.title)).slice(0, 6)
            .map((e) => h("div", { class: "explain explain-" + e.tone }, h("strong", { text: e.title }), h("p", { text: e.text })));
        fill(s5.body, 
            h("p", { class: "outcome outcome-" + (ok ? "good" : "warn") }, icon(ok ? ICONS.check : ICONS.warn), h("span", { text: codeText })),
            lastErr && !end.cancelled ? h("p", { class: "muted small" }, "Last line: ", h("q", { text: lastErr })) : null,
            cards.length ? h("div", { class: "explains" }, cards) : null);
        s5.set(ok ? "done" : "warn");

        const main = files.find((f) => f.change !== "deleted" && VISUALS[f.path]);
        if (main) {
            try {
                const data = await api(`file?mode=${ui.mode}&path=${encodeURIComponent(main.path)}`);
                const vis = data.kind === "json" ? VISUALS[main.path](data.content) : null;
                if (vis) s5.body.append(h("div", { class: "result-visual" }, h("h5", { text: "The saved result, drawn" }), vis));
            } catch (e) { /* the raw file is still one click away */ }
        }
        if (skill.next && ok) {
            const nxt = byId[skill.next];
            s5.body.append(h("button", { type: "button", class: "btn btn-sm btn-primary next-btn", onclick: () => selectSkill(nxt.id) },
                `Next: step ${nxt.step}, ${nxt.name}`, icon(ICONS.arrow)));
        }
        await refreshAfterRun();
    }

    async function refreshAfterRun() {
        try { ui.server = await api("state?mode=" + ui.mode); } catch (e) { return; }
        renderJourney();
        renderFiles();
        // Update the file chips in the panel without wiping the run view.
        document.querySelectorAll("#skillPanel .uses .file-chip").forEach((chip) => {
            const exists = ui.server.files.some((f) => f.path === chip.textContent);
            chip.disabled = !exists;
            chip.classList.toggle("missing", !exists);
        });
    }

    function setRunning(on) {
        ui.running = on;
        const run = $("#runBtn"), stopBtn = $("#stopBtn");
        if (run) run.disabled = on;
        if (stopBtn) stopBtn.hidden = !on;
        document.querySelectorAll(".action-tab, .journey-step, .side-chip, #resetBtn").forEach((b) => (b.disabled = on));
        document.body.classList.toggle("is-running", on);
    }

    async function stop() {
        try { await api("cancel", { mode: ui.mode }); } catch (e) {}
    }

    // ---------- files ----------
    const FILE_ABOUT = {
        "trader/config.json": "Your rules (Settings): budget, max loss, trading hours. Every skill that sizes or checks a trade reads it.",
        "trader/universe.txt": "The list of US stocks the scanner goes through, one per line. Written by the Chart Scanner (\"All US stocks\").",
        "trader/watchlist.json": "The stocks the Chart Scanner found. The News Monitor and the Entry Timer read it.",
        "trader/state/news.json": "Which news items were already shown, so each appears once. Written by the News Monitor.",
        "trader/entry.json": "The entry signal: the stock, the time and price it triggered, and the opening range. Written by the Entry Timer, read by the Exit Planner.",
        "trader/plan.json": "The trade plan: entry, stop, target, risk per share and the time to be out by. Written by the Exit Planner.",
        "trader/timemachine.json": "The 10,000 replays: the odds, the price spread over the day and the real history. Written by the Time Machine.",
        "trader/orders.json": "The proposed order with an exact number of shares. Written by the Budget Manager, checked by the Risk Manager.",
        "trader/state/risk.json": "PASS or BLOCK for each order, with a fingerprint of the exact order. Written by the Risk Manager.",
        "trader/state/broker.json": "Your log: every yes, no, placed order and fill. Written by the Order Executor.",
        "trader/portfolio.json": "Your paper account: cash and shares. Updated when you log a fill.",
        "trader/prices.json": "The latest delayed prices. Written by Price Alerts, read when sizing and checking a trade.",
        "trader/alerts.json": "Your alert rules. Written by Price Alerts.",
        "trader/state/alerts.json": "Which alerts already rang and when, so each rings once.",
        "trader/metrics.json": "One summary row per company. Written by the Earnings Analyst.",
        "trader/state/pelosi.json": "Which Congress trade reports were already shown. Written by the Pelosi Tracker.",
    };

    function renderFiles() {
        const files = ui.server?.files || [];
        $("#filesHint").textContent = `On disk: trader_workspace/${ui.mode}/trader/ in the project folder. Demo and live each have their own.`;
        $("#fileList").replaceChildren(...files.map((f) => {
            const readable = /\.(json|txt)$/.test(f.path);
            return h("button", { type: "button", class: "file-row", disabled: !readable, onclick: () => openFile(f.path) },
                icon(ICONS.file),
                h("span", { class: "mono file-name", text: f.path }),
                h("span", { class: "muted small file-about", text: FILE_ABOUT[f.path] || "" }),
                h("span", { class: "muted small num file-size", text: f.size < 1024 ? f.size + " B" : Math.round(f.size / 1024) + " KB" }));
        }));
        if (!files.length) $("#fileList").append(h("p", { class: "muted", text: "Empty. Run a skill to fill it." }));
    }

    async function openFile(path) {
        const dlg = $("#fileDialog");
        $("#fileTitle").textContent = path;
        $("#fileAbout").textContent = FILE_ABOUT[path] || "";
        $("#fileVisual").replaceChildren();
        $("#fileRaw").textContent = "Loading…";
        dlg.showModal();
        try {
            const data = await api(`file?mode=${ui.mode}&path=${encodeURIComponent(path)}`);
            $("#fileRaw").textContent = data.kind === "json" ? JSON.stringify(data.content, null, 2) : data.content;
            const vis = data.kind === "json" && VISUALS[path] ? VISUALS[path](data.content) : null;
            if (vis) $("#fileVisual").append(vis);
            $("#fileRawWrap").open = !vis;
        } catch (e) {
            $("#fileRaw").textContent = e.message;
            $("#fileRawWrap").open = true;
        }
    }

    // ---------- result visuals ----------
    function kv(rows) {
        return h("dl", { class: "kv" }, rows.filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
    }

    function table(cols, rows) {
        return h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, cols.map(([label, , right]) => h("th", { class: right ? "r" : null, text: label })))),
            h("tbody", {}, rows.map((r) => h("tr", {}, cols.map(([, fn, right]) => h("td", { class: right ? "r num" : null }, fn(r))))))));
    }

    const SETUP_NAMES = { orb: "Opening-range breakout", breakout_20d: "New 20-day high", bull_flag: "Bull flag",
        reclaim_ma20: "Back above the 20-day average", oversold: "Oversold", oversold_bounce: "Oversold bounce" };

    const VISUALS = {
        "trader/plan.json": (p) => {
            const lo = p.stop, hi = p.target, span = hi - lo || 1;
            const at = (v) => `${((hi - v) / span) * 100}%`;
            return h("div", { class: "ladder-wrap" },
                h("div", { class: "ladder" },
                    h("div", { class: "ladder-zone zone-good", style: `top:0;height:${at(p.entry)}` }),
                    h("div", { class: "ladder-zone zone-bad", style: `top:${at(p.entry)};bottom:0` }),
                    [["Target", p.target, "good", `take the profit (+${money(p.target - p.entry)} a share)`],
                        ["Entry", p.entry, "accent", `buy here, ${p.entry_time || ""}`],
                        ["Stop", p.stop, "bad", `get out (-${money(p.risk_per_share)} a share)`]].map(([name, v, tone, note]) =>
                        h("div", { class: "ladder-line line-" + tone, style: `top:${at(v)}` },
                            h("span", { class: "ladder-name", text: name }), h("strong", { class: "num", text: money(v) }), h("span", { class: "muted small", text: note })))),
                kv([["Stock", `${p.symbol} (${p.side}), ${p.date}`], ["Stop rule", p.stop_label], ["Target rule", p.target_label],
                    ["Risk a share (1R)", money(p.risk_per_share)], ["Reward : risk", String(p.reward_risk)], ["Out by", `${p.flat_by} New York time`]]));
        },
        "trader/entry.json": (e) => kv([["Stock", e.symbol], ["Status", e.status], ["Triggered at", e.time ? `${e.time}, ${money(e.price)}` : null],
            ["Line to beat", money(e.level)], ["Opening range", e.opening_range ? `${money(e.opening_range.low)} to ${money(e.opening_range.high)}` : null]]),
        "trader/watchlist.json": (w) => {
            const hits = w.hits || [];
            return h("div", {},
                h("p", { class: "muted small", text: `${hits.length} matches${w.scanned ? ` out of ${w.scanned} charts scanned` : ""}${w.as_of ? `, data as of ${w.as_of}` : ""}.` }),
                hits.length ? table([
                    ["Stock", (r) => h("strong", { class: "mono", text: r.symbol })],
                    ["Pattern", (r) => (r.setups || []).map((s) => SETUP_NAMES[s] || s).join(", ")],
                    ["When", (r) => r.at || r.close_date || ""],
                    ["Price", (r) => money(r.price), true],
                    ["Above range", (r) => (r.pct_over !== undefined ? `+${r.pct_over}%` : r.rsi !== undefined ? `RSI ${r.rsi}` : ""), true],
                ], hits.slice(0, 60)) : null);
        },
        "trader/orders.json": (o) => {
            const orders = Array.isArray(o) ? o : o.orders || [];
            return h("div", { class: "tickets" }, orders.map((r, i) => h("div", { class: "ticket" },
                h("div", { class: "ticket-head" }, h("strong", { text: `Order ${i + 1}: ${String(r.side).toUpperCase()} ${r.qty} ${r.symbol}` }),
                    h("span", { class: "tag", text: `${r.type}, ${r.order_class || "simple"}` })),
                kv([["Stop-loss", r.stop_loss_stop_price ? money(Number(r.stop_loss_stop_price)) : null],
                    ["Take-profit", r.take_profit_limit_price ? money(Number(r.take_profit_limit_price)) : null],
                    ["Max loss at the stop", r.plan?.max_loss !== undefined ? money(r.plan.max_loss) : null], ["Why", r.why]]))));
        },
        "trader/timemachine.json": (t) => {
            const m = t.mc, p = t.plan;
            const seg = (cls, v, label) => h("div", { class: "odds-seg " + cls, style: `flex:${v}`, title: `${label}: ${pct(v)}` }, v > 0.08 ? pct(v) : "");
            const chart = h("div", { class: "chart chart-sm" });
            const draw = () => fanChart(chart, m, p);
            ui.redraw = [draw];
            requestAnimationFrame(draw);
            return h("div", {},
                h("p", { class: "verdict", text: t.verdict }),
                h("div", { class: "odds" }, seg("odds-good", m.p_target, "Target first"), seg("odds-bad", m.p_stop, "Stop first"), seg("odds-mid", m.p_neither, "Neither by the close")),
                h("div", { class: "legend" },
                    h("span", { class: "legend-item" }, h("i", { class: "dot odds-good" }), `Target first ${pct(m.p_target)}`),
                    h("span", { class: "legend-item" }, h("i", { class: "dot odds-bad" }), `Stop first ${pct(m.p_stop)}`),
                    h("span", { class: "legend-item" }, h("i", { class: "dot odds-mid" }), `Still open at ${m.until} ${pct(m.p_neither)}`)),
                h("p", { class: "muted small", text: `${m.replays.toLocaleString()} replays, seed ${m.seed}, built from ${m.pool_sessions} real trading days (${m.pool_from} to ${m.pool_to}). Real history of the same rule: ${t.history.triggered} times, ${t.history.target} hit the target, ${t.history.stop} the stop, ${t.history.close} neither.` }),
                h("h5", { text: "Where the price went in the replays" }),
                chart,
                h("p", { class: "muted small", text: "Dark band: the middle half of the replays. Light band: 90% of them. Line: the middle replay." }));
        },
        "trader/prices.json": (p) => table([["Stock", (r) => h("strong", { class: "mono", text: r[0] })], ["Price", (r) => money(typeof r[1] === "number" ? r[1] : r[1]?.price), true]],
            Object.entries(p.prices || {})),
        "trader/portfolio.json": (p) => h("div", {}, kv([["Cash", money(p.cash)]]),
            (p.positions || []).length ? table([["Stock", (r) => r.symbol || r.ticker], ["Shares", (r) => String(r.qty ?? r.shares), true]], p.positions) : h("p", { class: "muted", text: "No shares held." })),
        "trader/config.json": (c) => kv(CAT.settings.map((f) => [f.label, Array.isArray(c[f.name]) ? c[f.name].join(", ") || "none" : String(c[f.name] ?? "")])),
    };

    function fanChart(el, m, p) {
        if (!window.Plotly) return;
        const x = m.band_times, b = m.bands;
        const col = (i) => b.map((r) => r[i]);
        const accent = css("--series-1"), text = css("--text-2"), grid = css("--grid"), good = css("--good"), bad = css("--bad");
        const band = (lo, hi, alpha, name) => [
            { x, y: col(lo), type: "scatter", mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
            { x, y: col(hi), type: "scatter", mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: hexA(accent, alpha), name, hoverinfo: "skip" },
        ];
        const level = (y, color, label) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y, line: { color, width: 1.5, dash: "dot" }, label: { text: label, textposition: "end", font: { color, size: 11 } } });
        Plotly.react(el, [
            ...band(0, 4, 0.14, "90% of replays"),
            ...band(1, 3, 0.28, "middle half"),
            { x, y: col(2), type: "scatter", mode: "lines", line: { color: accent, width: 2 }, name: "middle replay", hovertemplate: "%{x}: $%{y:.2f}<extra></extra>" },
        ], {
            margin: { l: 48, r: 12, t: 8, b: 32 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", showlegend: false,
            font: { family: "Inter, sans-serif", size: 12, color: text },
            xaxis: { gridcolor: grid, nticks: 8, fixedrange: true }, yaxis: { gridcolor: grid, tickprefix: "$", fixedrange: true },
            shapes: [level(p.target, good, `target ${p.target}`), level(p.entry, text, `entry ${p.entry}`), level(p.stop, bad, `stop ${p.stop}`)],
        }, { displayModeBar: false, responsive: true });
    }

    function hexA(color, alpha) {
        const m = color.match(/^#([0-9a-f]{6})$/i);
        if (!m) return color;
        const n = parseInt(m[1], 16);
        return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
    }

    document.addEventListener("themechange", () => ui.redraw.forEach((f) => f()));

    // ---------- dialogs: settings, glossary, file ----------
    document.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => {
        if (b.dataset.open === "settingsDialog") openSettings();
        else document.getElementById(b.dataset.open).showModal();
    }));
    document.querySelectorAll("dialog").forEach((d) => {
        d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
        d.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => d.close()));
    });

    function openSettings() {
        const s = ui.server?.settings || {};
        $("#settingsMode").textContent = ui.mode === "demo"
            ? "These are the rules for Demo mode. Live mode keeps its own."
            : "These are the rules for Live mode. Demo mode keeps its own.";
        $("#settingsFields").replaceChildren(...CAT.settings.map((f) => {
            const v = s[f.name];
            return renderField({ ...f, default: Array.isArray(v) ? v.join(", ") : v, demo_default: null, required: false });
        }));
        $("#settingsError").hidden = true;
        $("#settingsDialog").showModal();
    }

    $("#settingsForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const values = {};
        CAT.settings.forEach((f) => (values[f.name] = $("#settingsForm").elements[f.name].value));
        try {
            await api("settings", { mode: ui.mode, values });
            $("#settingsDialog").close();
            ui.server = await api("state?mode=" + ui.mode);
            renderSkill();
        } catch (err) {
            $("#settingsError").textContent = err.message;
            $("#settingsError").hidden = false;
        }
    });

    fill($("#glossaryList"), Object.entries(CAT.glossary).map(([term, def]) => [h("dt", { text: term }), h("dd", { text: def })]));

    $("#resetBtn").addEventListener("click", async () => {
        const what = ui.mode === "demo" ? "Demo" : "Live";
        if (!confirm(`Delete everything the skills saved in ${what} mode and put your rules back to the defaults?`)) return;
        try {
            await api("reset", { mode: ui.mode });
            Object.keys(ui.runs).filter((k) => k.startsWith(ui.mode + ":")).forEach((k) => delete ui.runs[k]);
            await refresh();
        } catch (e) { alert(e.message); }
    });

    window.addEventListener("hashchange", () => { if (byId[location.hash.slice(1)] && location.hash.slice(1) !== ui.skill) selectSkill(location.hash.slice(1), false); });

    api("clock").then((c) => { ui.clock = c; renderBanner(); }).catch(() => {});
    refresh();
})();
