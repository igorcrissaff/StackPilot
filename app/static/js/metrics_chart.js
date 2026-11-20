(function () {
    var CHARTS = [
        { key: "cpu", canvasId: "metrics-chart-cpu", color: "#0ea5e9" },
        { key: "memory", canvasId: "metrics-chart-memory", color: "#10b981" },
        { key: "disk", canvasId: "metrics-chart-disk", color: "#f59e0b" },
        { key: "swap", canvasId: "metrics-chart-swap", color: "#8b5cf6" }
    ];

    window.metricsCharts = window.metricsCharts || {};

    function parseData() {
        var el = document.getElementById("metrics-chart-data");
        if (!el) {
            return null;
        }
        try {
            return JSON.parse(el.textContent);
        } catch (error) {
            return null;
        }
    }

    function formatLabels(labels) {
        return (labels || []).map(function (timestamp) {
            return new Date(timestamp * 1000).toLocaleTimeString();
        });
    }

    function buildOptions() {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    ticks: { color: "#64748b", maxTicksLimit: 5, font: { size: 9 } },
                    grid: { color: "#1c2538" }
                },
                y: {
                    min: 0,
                    max: 100,
                    ticks: {
                        color: "#64748b",
                        font: { size: 9 },
                        callback: function (value) { return value + "%"; }
                    },
                    grid: { color: "#1c2538" }
                }
            }
        };
    }

    function renderChart(def, data, labels) {
        var canvas = document.getElementById(def.canvasId);
        var values = data[def.key];
        if (!canvas || !Array.isArray(values)) {
            return;
        }
        if (!values.some(function (value) { return value !== null && value !== undefined; })) {
            return;
        }

        var datasets = [{
            data: values,
            borderColor: def.color,
            backgroundColor: def.color + "22",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            spanGaps: false,
            fill: true
        }];

        var existing = window.metricsCharts[def.key];
        if (existing && existing.canvas === canvas) {
            existing.data.labels = labels;
            existing.data.datasets = datasets;
            existing.update("none");
            return;
        }

        if (existing) {
            existing.destroy();
        }

        window.metricsCharts[def.key] = new Chart(canvas, {
            type: "line",
            data: { labels: labels, datasets: datasets },
            options: buildOptions()
        });
    }

    function render() {
        var data = parseData();
        if (!data || typeof Chart === "undefined") {
            return;
        }
        var labels = formatLabels(data.labels);
        CHARTS.forEach(function (def) {
            renderChart(def, data, labels);
        });
    }

    document.addEventListener("DOMContentLoaded", render);
    document.body.addEventListener("htmx:afterSwap", render);
    document.body.addEventListener("htmx:afterSettle", render);
})();
