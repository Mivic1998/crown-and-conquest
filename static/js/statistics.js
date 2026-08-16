/**
 * Render premium historical kingdom statistics using Chart.js library.
 *
 * Django prepares one chronological data structure in the
 * `kingdom_statistics` view and embeds it safely in
 * `kingdoms/statistics.html` using Django's `json_script` filter.
 *
 * Each chart canvas has an ID matching one key in that data structure. This
 * allows the same loop and Chart.js configuration to render all nine metrics
 * without duplicating chart-construction code.
 *
 * This script is presentational only. It does not calculate simulation values,
 * change Kingdom or TurnHistory records, enforce premium access, or request
 * additional data from Django. The backend remains authoritative over all
 * historical values and premium permissions.
 */

/* global Chart */

// Select the nine canvas elements inside `.statistics-chart` containers.
// These canvases are rendered only when the kingdom is premium and has at
// least two TurnHistory records.
const charts = document.querySelectorAll(".statistics-chart canvas");

// Django's `json_script` filter creates a `<script type="application/json">`
// element with this ID. Its text content contains safely escaped JSON rather
// than executable JavaScript.
const chartDataElement = document.getElementById("chart-data");

// Standard users do not receive the chart-data element or load this script.
// The check also prevents parsing when the expected embedded data is absent.
if (chartDataElement) {
    // Convert Django's serialized JSON text into a normal JavaScript object.
    //
    // Expected keys:
    // - labels
    // - population
    // - treasury
    // - food
    // - happiness
    // - stability
    // - army_size
    // - army_quality
    // - a_eff
    // - infra
    const chartData = JSON.parse(chartDataElement.textContent);

    // Canvas IDs correspond to backend dictionary keys. This mapping provides
    // clearer human-readable titles for chart axes and datasets.
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

    // Create one independent Chart.js instance for each metric canvas.
    for (const chart of charts) {
        // Use the friendly mapping when available. Falling back to the raw ID
        // means an additional canvas can still render even if its label has not
        // yet been added to this object.
        const metricLabel = labels[chart.id] || chart.id;

        // Chart is supplied globally by the Chart.js CDN script loaded before
        // this file in the statistics template.
        new Chart(chart, {
            // Historical values are plotted as continuous trends over turns.
            type: "line",

            data: {
                // The view constructs labels from TurnHistory.turn_number in
                // ascending chronological order.
                labels: chartData.labels,

                datasets: [{
                    // The legend is hidden below, but this label still identifies
                    // the dataset internally and may be used by Chart.js tooltips.
                    label: metricLabel,

                    // The canvas ID selects the matching backend series. For
                    // example, `<canvas id="food">` uses `chartData.food`.
                    data: chartData[chart.id],//The data in the backend and the labels in the frontend/JS both match the canvas IDs, so they can be matched to one another to create the charts.

                    // Apply a moderate curve between historical points.
                    tension: 0.25,

                    // Keep individual turn markers visible without dominating
                    // the line.
                    pointRadius: 2,

                    // Use a relatively prominent trend line.
                    borderWidth: 3,
                }],
            },

            options: {
                // Recalculate chart dimensions when the containing layout or
                // viewport changes.
                responsive: true,

                // Allow the chart to fill the height supplied by its CSS
                // container instead of enforcing Chart.js's default ratio.
                maintainAspectRatio: false,

                // Every chart contains one dataset and already has a visible
                // section heading, so a separate legend would be redundant.
                plugins: {
                    legend: {
                        display: false,
                    },
                },

                scales: {
                    x: {
                        // All charts use completed kingdom turns as the
                        // horizontal sequence.
                        title: {
                            display: true,
                            text: "Turn",
                        },

                        // Hiding vertical grid lines keeps the chart visually
                        // lighter while retaining axis labels.
                        grid: {
                            display: false,
                        },
                    },

                    y: {
                        // The axis title changes according to the canvas ID.
                        title: {
                            display: true,
                            text: metricLabel,
                        },

                        // Historical metrics such as population and treasury are
                        // shown around their actual range rather than forcing
                        // every graph to begin at zero.
                        beginAtZero: false,
                    },
                },
            },
        });
    }
}