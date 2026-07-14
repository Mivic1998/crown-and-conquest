const editButton = document.getElementById("edit-rallying-cry");
    const cancelButton = document.getElementById("cancel-rallying-cry-edit");
    const rallyingCryForm = document.getElementById("rallying-cry-form");

    if (editButton && cancelButton && rallyingCryForm) {
        editButton.addEventListener("click", () => {
            rallyingCryForm.classList.remove("d-none");
            editButton.classList.add("d-none");
        });

        cancelButton.addEventListener("click", () => {
            rallyingCryForm.classList.add("d-none");
            editButton.classList.remove("d-none");
        });
    }