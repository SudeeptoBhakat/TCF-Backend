(function() {
    const input = document.querySelector("input[multiple]");
    if (!input) return;

    const dropZone = document.createElement("div");
    dropZone.style.border = "2px dashed #999";
    dropZone.style.padding = "20px";
    dropZone.style.marginTop = "10px";
    dropZone.style.borderRadius = "8px";
    dropZone.style.textAlign = "center";
    dropZone.style.cursor = "pointer";
    dropZone.innerHTML = "Drag & Drop Images Here<br><small>(or click above to select files)</small>";

    input.insertAdjacentElement("afterend", dropZone);

    dropZone.addEventListener("dragover", e => {
        e.preventDefault();
        dropZone.style.borderColor = "#3c8dbc";
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "#999";
    });

    dropZone.addEventListener("drop", e => {
        e.preventDefault();
        dropZone.style.borderColor = "#28a745";
        input.files = e.dataTransfer.files;
    });
})();
