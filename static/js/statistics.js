const charts = document.querySelectorAll(".statistics-chart canvas");

const chartData = JSON.parse(
    document.getElementById("chart-data").textContent
);

for (const chart of charts) {

    new Chart(chart, {

        type: "line",

        data: {

            labels: chartData.labels,

            datasets: [

                {

                    label:
                        chart.id.charAt(0).toUpperCase() +
                        chart.id.slice(1),

                    data: chartData[chart.id],

                    tension: 0.25

                }

            ]

        }

    });

}