const timerElement = document.getElementById("countdown-timer");

if (timerElement) {

    const deadline = new Date(
        timerElement.dataset.deadline
    ).getTime();

    function updateCountdown() {

        const now = new Date().getTime();
        const distance = deadline - now;

        if (distance <= 0) {

            timerElement.textContent = "Response time expired";

            clearInterval(countdownInterval);

            window.location.reload();

            return;
        }

        const hours = Math.floor(
            distance / (1000 * 60 * 60)
        );

        const minutes = Math.floor(
            (distance % (1000 * 60 * 60)) / (1000 * 60)
        );

        const seconds = Math.floor(
            (distance % (1000 * 60)) / 1000
        );

        timerElement.textContent =
            `${hours}h ${minutes}m ${seconds}s`;
    }

    updateCountdown();

    const countdownInterval = setInterval(
        updateCountdown,
        1000
    );

}