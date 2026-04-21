document.addEventListener("DOMContentLoaded", () => {
    const textarea = document.querySelector(".form-textarea");
    const counter = document.getElementById("job-description-count");
    if (textarea && counter) {
        const updateCounter = () => {
            counter.textContent = `${textarea.value.length}/${textarea.maxLength}`;
        };
        textarea.addEventListener("input", updateCounter);
        updateCounter();
    }
});
