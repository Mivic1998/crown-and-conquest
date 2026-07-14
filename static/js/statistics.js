/* global Chart */

const charts = document.querySelectorAll(".statistics-chart canvas");
const chartDataElement = document.getElementById("chart-data");

if (chartDataElement) {
    const chartData = JSON.parse(chartDataElement.textContent);

    const labels = {
        population: "Population",
        treasury: "Treasury",
        food: "Food",
        happiness: "Happiness",
        stability: "Stability",
        army_size: "Army Size",
        army_quality: "Army Quality",
        a_eff: "Agricultural Efficiency",
        infra: "Infrastructure",
    };

    for (const chart of charts) {
        const metricLabel = labels[chart.id] || chart.id;
        new Chart(chart, {
            type: "line",
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: metricLabel,
                    data: chartData[chart.id],
                    tension: 0.25,
                    pointRadius: 2,
                    borderWidth: 3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { title: { display: true, text: "Turn" }, grid: { display: false } },
                    y: { title: { display: true, text: metricLabel }, beginAtZero: false }
                }
            }
        });
    }
}
