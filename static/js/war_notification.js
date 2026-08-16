/**
 * Toggle the defender rallying-cry editing interface.
 *
 * This file is loaded only by `wars/war_notification.html`. It applies when
 * the defending kingdom has already submitted a rallying cry and the template
 * therefore renders:
 *
 * - the saved rallying cry;
 * - an “Edit Rallying Cry” button;
 * - a hidden, pre-populated Django form;
 * - a “Cancel” button.
 *
 * The script shows and hides those existing elements by adding or removing
 * Bootstrap's `d-none` utility class. It does not validate, save, or modify the
 * rallying cry itself. Submission still passes through `WarForm`,
 * `notify_defender()`, Gemini evaluation, and the Django database workflow.
 */

// Targets the button rendered only when `war.defender_rallying_cry` already
// contains a saved response.
const editButton = document.getElementById("edit-rallying-cry");

    // Targets the non-submit Cancel button inside the hidden edit form.
    const cancelButton = document.getElementById("cancel-rallying-cry-edit");

    // Targets the pre-populated POST form that Django initially hides with
    // Bootstrap's `d-none` class.
    const rallyingCryForm = document.getElementById("rallying-cry-form");

    // All three elements exist only in the template branch for an already
    // submitted defender rallying cry. Requiring all of them prevents event
    // listener setup on the initial-response version of the page.
    if (editButton && cancelButton && rallyingCryForm) {
        /**
         * Reveal the edit form and hide the Edit button.
         *
         * The form already contains `WarForm`, initialised by Django with the
         * stored `War.defender_rallying_cry`. This handler changes presentation
         * only; no backend state is altered until the form is submitted.
         */
        editButton.addEventListener("click", () => {
            // Removing `d-none` reveals the existing edit form.
            rallyingCryForm.classList.remove("d-none");

            // Hide the Edit button while the form is open so the action is not
            // presented twice.
            editButton.classList.add("d-none");
        });

        /**
         * Hide the edit form and restore the Edit button.
         *
         * Because the button has `type="button"`, cancelling does not submit
         * the form or overwrite the stored rallying cry.
         */
        cancelButton.addEventListener("click", () => {
            // Restore the form's original hidden state.
            rallyingCryForm.classList.add("d-none");

            // Make the Edit action available again.
            editButton.classList.remove("d-none");
        });
    }