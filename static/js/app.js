// Shared UI behaviour: theme toggle, loading overlay, ticker chips, copy buttons.
(function () {
    const root = document.documentElement;

    function isDark() {
        if (root.dataset.theme) return root.dataset.theme === "dark";
        return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    document.getElementById("themeToggle")?.addEventListener("click", () => {
        const next = isDark() ? "light" : "dark";
        root.dataset.theme = next;
        try { localStorage.setItem("theme", next); } catch (e) {}
        document.dispatchEvent(new CustomEvent("themechange"));
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        document.dispatchEvent(new CustomEvent("themechange"));
    });

    // Training takes a few seconds: show an overlay while the request runs.
    const loading = document.getElementById("loading");
    document.querySelectorAll("form[data-loading]").forEach((form) => {
        form.addEventListener("submit", () => {
            const input = form.querySelector('input[name="symbol"]');
            if (input) input.value = input.value.trim().toUpperCase();
            if (loading) loading.hidden = false;
        });
    });
    // Hide it again if the user navigates back to a cached page.
    window.addEventListener("pageshow", () => { if (loading) loading.hidden = true; });

    document.querySelectorAll(".chip[data-ticker]").forEach((chip) => {
        chip.addEventListener("click", () => {
            const form = chip.closest("form");
            form.querySelector('input[name="symbol"]').value = chip.dataset.ticker;
            form.requestSubmit();
        });
    });

    document.querySelectorAll("[data-copy]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(btn.dataset.copy);
                btn.textContent = "Copied";
                setTimeout(() => (btn.textContent = "Copy"), 1500);
            } catch (e) {}
        });
    });
})();
