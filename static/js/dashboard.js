document.addEventListener("DOMContentLoaded", () => {
    const timer = document.getElementById("turn-timer");

    if (!timer) return;

    const turnsRemaining =
        Number(timer.dataset.turnsRemaining);

    const cooldownEndsAt =
        timer.dataset.cooldownEndsAt
            ? new Date(timer.dataset.cooldownEndsAt)
            : null;

    const dailyResetAt =
        timer.dataset.dailyResetAt
            ? new Date(timer.dataset.dailyResetAt)
            : null;

    const message =
        document.getElementById("turn-timer-message");

    const countdown =
        document.getElementById("turn-countdown");

    function formatTime(milliseconds) {
        if (milliseconds <= 0) {
            return "00:00:00";
        }

        const totalSeconds =
            Math.floor(milliseconds / 1000);

        const hours =
            Math.floor(totalSeconds / 3600);

        const minutes =
            Math.floor(
                (totalSeconds % 3600) / 60
            );

        const seconds =
            totalSeconds % 60;

        return (
            String(hours).padStart(2, "0")
            + ":"
            + String(minutes).padStart(2, "0")
            + ":"
            + String(seconds).padStart(2, "0")
        );
    }

    function getNextTurnTarget() {
        const targets = [];

        if (turnsRemaining <= 0 && dailyResetAt) {
            targets.push(dailyResetAt);
        }

        if (cooldownEndsAt) {
            targets.push(cooldownEndsAt);
        }

        if (targets.length === 0) {
            return null;
        }

        return new Date(
            Math.max(
                ...targets.map(target => target.getTime())
            )
        );
    }

    function updateTimer() {
        const target = getNextTurnTarget();

        if (!target) {
            message.classList.remove("active");
            return;
        }

        const now = new Date();
        const remaining = target - now;

        if (remaining <= 0) {
            window.location.reload();
            return;
        }

        countdown.textContent = formatTime(remaining);
        message.classList.add("active");
    }

    updateTimer();

    setInterval(updateTimer, 1000);
});