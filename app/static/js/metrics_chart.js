(function () {
    var COLORS = {
        cpu: "#0ea5e9",
        memory: "#10b981",
        disk: "#f59e0b",
        swap: "#8b5cf6"
    };
    var LABELS = {
        cpu: "CPU",
        memory: "Memória",
        disk: "Disco",
        swap: "Swap"
    };

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

    function buildDatasets(data) {
        return ["cpu", "memory", "disk", "swap"]
            .filter(function (key) {
                return Array.isArray(data[key]) && data[key].some(function (value) {
                    return value !== null && value !== undefined;
                });
            })
            .map(function (key) {
                return {
                    label: LABELS[key],
                    data: data[key],
                    borderColor: COLORS[key],
                    backgroundColor: COLORS[key] + "22",
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.3,
                    spanGaps: false,
                    fill: false
                };
            });
    }

    function formatLabels(labels) {
        return (labels || []).map(function (timestamp) {
            return new Date(timestamp * 1000).toLocaleTimeString();
        });
    }

    function render() {
        var canvas = document.getElementById("metrics-chart");
        var data = parseData();
        if (!canvas || !data || typeof Chart === "undefined") {
            return;
        }

        var labels = formatLabels(data.labels);
        var datasets = buildDatasets(data);

        if (window.metricsChart && window.metricsChart.canvas === canvas) {
            window.metricsChart.data.labels = labels;
            window.metricsChart.data.datasets = datasets;
            window.metricsChart.update("none");
            return;
        }

        if (window.metricsChart) {
            window.metricsChart.destroy();
        }

        window.metricsChart = new Chart(canvas, {
            type: "line",
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        labels: { color: "#94a3b8", boxWidth: 10, font: { size: 10 } }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: "#64748b", maxTicksLimit: 6, font: { size: 9 } },
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
            }
        });
    }

    document.addEventListener("DOMContentLoaded", render);
    document.body.addEventListener("htmx:afterSwap", render);
    document.body.addEventListener("htmx:afterSettle", render);
})();
