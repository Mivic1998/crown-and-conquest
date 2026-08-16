/**
 * Display the remaining response time for a pending declaration of war.
 *
 * This file is loaded by both:
 *
 * - `wars/war_pending.html`, shown to the attacking kingdom;
 * - `wars/war_notification.html`, shown to the defending kingdom.
 *
 * Django places the authoritative `War.defender_response_deadline` timestamp
 * into the `data-deadline` attribute of `#countdown-timer`. This script parses
 * that timestamp, displays a live hours/minutes/seconds countdown, and reloads
 * the page when the visible deadline expires.
 *
 * The timer is presentational only. JavaScript does not update the War,
 * determine its status, resolve combat, or write to the database. On reload,
 * Django must inspect the stored War and decide what should happen next.
 */

 // Both warfare templates contain one heading with this ID.
const timerElement = document.getElementById("countdown-timer");

// Safely skip all countdown behaviour when the expected element is absent.
if (timerElement) {

    // Django renders `War.defender_response_deadline` through the ISO-8601
    // `date:"c"` filter into `data-deadline`.
    //
    // `new Date(...)` parses that server-generated timestamp, and `getTime()`
    // converts it into milliseconds since the Unix epoch for subtraction.
    const deadline = new Date(
        timerElement.dataset.deadline
    ).getTime();

    /**
     * Recalculate and display the remaining response time.
     *
     * The function compares the fixed deadline supplied by Django with the
     * browser's current clock. While time remains, it writes a human-readable
     * countdown into `#countdown-timer`.
     *
     * Once the deadline is reached, it displays an expiry message, stops the
     * repeating interval, and reloads the page so Django can evaluate the
     * authoritative War state.
     *
     * @returns {void}
     */
    function updateCountdown() {

        // Use the current browser time in milliseconds so it can be subtracted
        // directly from the parsed deadline.
        const now = new Date().getTime();
        const distance = deadline - now;

        if (distance <= 0) {

            // Give immediate visual feedback before navigation begins.
            timerElement.textContent = "Response time expired";

            // Stop further one-second updates once the timer has completed.
            clearInterval(countdownInterval);

            // Reload rather than resolving the War in JavaScript. On the
            // attacker's pending page, the Django view checks `war.has_expired`
            // and invokes the server-side warfare simulation.
            window.location.reload();

            return;
        }

        // Hours are calculated from the complete remaining duration and are not
        // restricted to a 24-hour clock.
        const hours = Math.floor(
            distance / (1000 * 60 * 60)
        );

        // Remove complete hours before calculating remaining minutes.
        const minutes = Math.floor(
            (distance % (1000 * 60 * 60)) / (1000 * 60)
        );

        // Remove complete minutes before calculating remaining seconds.
        const seconds = Math.floor(
            (distance % (1000 * 60)) / 1000
        );

        // Replace the template's initial “Calculating...” text with the current
        // countdown. `textContent` treats the value as plain text rather than
        // interpreting it as HTML.
        timerElement.textContent =
            `${hours}h ${minutes}m ${seconds}s`;
    }

    // Display the countdown immediately rather than waiting one second for the
    // first scheduled interval call.
    updateCountdown();

    // Recalculate the display once per second until the deadline is reached.
    const countdownInterval = setInterval(
        updateCountdown,
        1000
    );

}