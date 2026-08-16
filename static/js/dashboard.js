/**
 * Dashboard interaction and turn-availability enhancements.
 *
 * This file supports two independent pieces of client-side behaviour on
 * `kingdoms/dashboard.html`:
 *
 * 1. It displays a live countdown until the player can next take a turn.
 * 2. It synchronises each policy range slider with its paired manual number
 *    input.
 *
 * Django remains authoritative over turn availability and policy validation.
 * The countdown is presentational: the backend determines whether a cooldown
 * or daily reset has actually expired. Likewise, JavaScript clamps visible
 * policy values for convenience, while `PolicyForm` repeats the real
 * validation when the form is submitted.
 */


/**
 * Initialise the turn-availability countdown after the dashboard DOM exists.
 *
 * Django places the current turn allowance, cooldown deadline, and daily reset
 * deadline into `data-*` attributes on the `#turn-timer` section. This handler
 * reads those values, determines the latest restriction currently preventing
 * another turn, and updates the visible countdown once per second. !!!!!
 */
document.addEventListener("DOMContentLoaded", () => {
    // Targets the Turn Availability section rendered by dashboard.html.
    const timer = document.getElementById("turn-timer");

    // The script may be included only on the dashboard, but this guard ensures
    // that no countdown code runs if the expected section is absent.
    if (!timer) return;

    // Django renders `turn_limit.turns_remaining_today` into
    // `data-turns-remaining`. Dataset values are strings, so Number() converts
    // the value before it is compared numerically.
    const turnsRemaining =
        Number(timer.dataset.turnsRemaining);

    // Django formats `turn_limit.cooldown_ends_at` with the ISO-8601 `date:'c'`
    // filter. An empty attribute means that no cooldown timestamp currently
    // applies.
    const cooldownEndsAt =
        timer.dataset.cooldownEndsAt
            ? new Date(timer.dataset.cooldownEndsAt)
            : null;

    // The next daily reset is also rendered as an ISO-8601 timestamp from
    // `turn_limit.daily_reset_at`.
    const dailyResetAt =
        timer.dataset.dailyResetAt
            ? new Date(timer.dataset.dailyResetAt)
            : null;

    // This paragraph is hidden by CSS until the `active` class is added.
    const message =
        document.getElementById("turn-timer-message");

    // The remaining hours, minutes, and seconds are written into this span.
    const countdown =
        document.getElementById("turn-countdown");

    /**
     * Convert a millisecond duration into an HH:MM:SS string.
     *
     * @param {number} milliseconds - Remaining duration before availability.
     * @returns {string} A zero-padded time string.
     */
    function formatTime(milliseconds) {
        // Avoid displaying negative values while the page is preparing to
        // reload after expiry.
        if (milliseconds <= 0) {
            return "00:00:00";
        }

        // Discard incomplete milliseconds because the interface updates at
        // whole-second intervals.
        const totalSeconds =
            Math.floor(milliseconds / 1000);

        // Hours are not limited to 24, so a future deadline longer than one day
        // would still be represented accurately.
        const hours =
            Math.floor(totalSeconds / 3600);

        const minutes =
            Math.floor(
                (totalSeconds % 3600) / 60
            );

        const seconds =
            totalSeconds % 60;

        // padStart() keeps every unit at least two characters wide.
        return (
            String(hours).padStart(2, "0")
            + ":"
            + String(minutes).padStart(2, "0")
            + ":"
            + String(seconds).padStart(2, "0")
        );
    }

    /**
     * Determine the timestamp at which all current turn restrictions end.
     *
     * If the player has no daily turns remaining, the daily reset is included.
     * If a cooldown exists, its expiry is included. When both apply, the later
     * timestamp is selected because the player must wait until both conditions
     * have cleared.
     *
     * @returns {Date|null} The latest relevant restriction or null when no
     *     countdown is required.
     */
    function getNextTurnTarget() {
        const targets = [];

        // The daily reset matters only after the current daily allowance has
        // been exhausted.
        if (turnsRemaining <= 0 && dailyResetAt) {
            targets.push(dailyResetAt);
        }

        // A cooldown can block the next turn even while daily turns remain.
        if (cooldownEndsAt) {
            targets.push(cooldownEndsAt);
        }

        if (targets.length === 0) {
            return null;
        }

        // Select the latest timestamp because reaching an earlier one would not
        // make the player eligible if another restriction were still active.
        return new Date(
            Math.max(
                ...targets.map(target => target.getTime())
            )
        );
    }

    /**
     * Refresh the visible turn countdown and reload the page at expiry.
     *
     * Reloading asks Django to recalculate the authoritative TurnLimit state.
     * JavaScript does not locally enable the End Turn button or alter model
     * data when the timer reaches zero.
     */
    function updateTimer() {
        const target = getNextTurnTarget();

        // When neither the cooldown nor daily allowance requires a wait, keep
        // the explanatory countdown paragraph hidden.
        if (!target) {
            message.classList.remove("active");
            return;
        }

        const now = new Date();

        // Subtracting Date objects produces a duration in milliseconds.
        const remaining = target - now;

        if (remaining <= 0) {
            // The server may now clear an expired cooldown, replenish daily
            // turns, and re-render the correct button and context state.
            window.location.reload();
            return;
        }

        countdown.textContent = formatTime(remaining);

        // CSS changes the paragraph from `display: none` to `display: block`.
        message.classList.add("active");
    }

    // Populate the countdown immediately rather than leaving the span empty
    // until the first interval completes.
    updateTimer();

    // Refresh once per second to maintain a live HH:MM:SS display.
    setInterval(updateTimer, 1000);
});


/**
 * Connect every policy range control to its paired manual number input.
 *
 * Each `.policy-slider` contains a `data-input` value naming the ID of its
 * corresponding number input. The range control has the real `name` attribute
 * submitted to Django; the number input exists as a more precise editing aid.
 */
document.querySelectorAll(".policy-slider").forEach((slider) => {
    // For example, `data-input="tax_rate_manual"` resolves to the manual tax
    // number input rendered beside the range control.
    const manualInput = document.getElementById(slider.dataset.input);

    // Skip a slider safely if its paired element is absent or the data attribute
    // does not match an existing ID.
    if (!manualInput) {
        return;
    }

    /**
     * Mirror range-slider movement into the manual number input.
     */
    slider.addEventListener("input", () => {
        manualInput.value = slider.value;
    });

    /**
     * Validate the manual input against the range element's limits and copy the
     * result back to both controls.
     *
     * This is a user-interface safeguard only. Django's `PolicyForm` validates
     * taxation, individual investment ranges, and the combined 100% allocation
     * after submission.
     */
    function updateSlider() {
        // Number() converts the number input's string value for comparison.
        let value = Number(manualInput.value);

        // The range controls define their permitted limits in dashboard.html:
        // tax uses 0–50, while investments use 0–100.
        const min = Number(slider.min);
        const max = Number(slider.max);

        // If the manual field cannot be parsed as a number, restore the current
        // slider value rather than copying NaN into the interface.
        if (Number.isNaN(value)) {
            value = Number(slider.value);
        }

        // Clamp the manual value to the associated range input's limits.
        value = Math.max(min, Math.min(max, value));

        // Keep both visual controls in agreement. Only the slider carries a
        // form-field name and is therefore submitted to Django.
        manualInput.value = value;
        slider.value = value;
    }

    /**
     * Apply a typed value when Enter is pressed without submitting the policy
     * form from the manual input.
     */
    manualInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            // Prevent Enter from triggering the surrounding form submission.
            event.preventDefault();
            updateSlider();
        }
    });

    // Apply and clamp the value when the player leaves the number input.
    manualInput.addEventListener("blur", updateSlider);
});