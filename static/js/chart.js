// Renders the price/forecast chart with Plotly, styled from the page's CSS tokens.
(function () {
    const el = document.getElementById("chart");
    const data = JSON.parse(document.getElementById("chartData").textContent);
    let range = "ALL";

    const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

    function xRange(key) {
        if (key === "ALL") return null;
        const end = new Date(data.forecast.x[1]);
        const start = new Date(end);
        start.setMonth(start.getMonth() - { "1M": 1, "3M": 3, "6M": 6 }[key]);
        end.setDate(end.getDate() + 2);
        return [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)];
    }

    function yRange(xr) {
        if (!xr) return null;
        const vals = [];
        data.history.x.forEach((d, i) => { if (d >= xr[0]) vals.push(data.history.y[i]); });
        vals.push(...data.forecast.y);
        const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.08 || 1;
        return [lo - pad, hi + pad];
    }

    function render() {
        const c1 = css("--series-1"), c2 = css("--series-2");
        const text = css("--text-2"), muted = css("--text-3"), grid = css("--grid"), surface = css("--surface");
        const money = "$%{y:,.2f}";

        const traces = [
            {
                name: "Actual close", x: data.history.x, y: data.history.y,
                type: "scatter", mode: "lines", line: { color: c1, width: 2 },
                hovertemplate: money + "<extra>Actual</extra>",
            },
            {
                name: "Model (test period)", x: data.fit.x, y: data.fit.y,
                type: "scatter", mode: "lines", line: { color: c2, width: 2, dash: "dot" },
                hovertemplate: money + "<extra>Model</extra>",
            },
            {
                name: "Forecast", x: data.forecast.x, y: data.forecast.y,
                type: "scatter", mode: "lines+markers",
                line: { color: c2, width: 2, dash: "dash" },
                marker: { size: [0, 12], color: c2, line: { color: surface, width: 2 } },
                hovertemplate: money + "<extra>Forecast</extra>",
            },
        ];

        const xr = xRange(range);
        const layout = {
            margin: { l: 56, r: 16, t: 16, b: 36 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: { family: "Inter, system-ui, sans-serif", size: 12, color: text },
            showlegend: false,
            hovermode: "x unified",
            hoverlabel: { bgcolor: surface, bordercolor: grid, font: { color: css("--text") } },
            xaxis: {
                type: "date", range: xr || undefined, autorange: !xr,
                showgrid: false, linecolor: grid, tickcolor: grid, tickfont: { color: muted },
                showspikes: true, spikemode: "across", spikethickness: 1, spikedash: "solid", spikecolor: muted,
            },
            yaxis: {
                range: yRange(xr) || undefined, autorange: !xr,
                gridcolor: grid, zeroline: false, tickprefix: "$", tickfont: { color: muted },
            },
            annotations: [{
                x: data.forecast.x[1], y: data.forecast.y[1], xanchor: "right", yanchor: "bottom",
                text: "<b>$" + data.forecast.y[1].toFixed(2) + "</b>", showarrow: false,
                xshift: -6, yshift: 14, font: { color: css("--text"), size: 12 },
                bgcolor: surface, bordercolor: grid, borderpad: 4,
            }],
        };

        Plotly.react(el, traces, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
    }

    document.querySelectorAll("#rangePicker button").forEach((btn) => {
        btn.addEventListener("click", () => {
            range = btn.dataset.range;
            document.querySelectorAll("#rangePicker button").forEach((b) => b.classList.toggle("active", b === btn));
            render();
        });
    });
    document.addEventListener("themechange", render);
    render();
})();
