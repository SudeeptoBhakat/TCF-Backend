<script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>

document.addEventListener("DOMContentLoaded", function () {
    const fileInput = document.querySelector(".multi-upload-input");

    if (!fileInput) return;

    // Build dropzone
    const dz = document.createElement("div");
    dz.className = "dropzone";
    dz.innerHTML = "<strong>Drag & Drop Images Here</strong><br>OR click to select.";
    fileInput.parentNode.insertBefore(dz, fileInput);
    dz.appendChild(fileInput);

    // Preview container
    const previewBox = document.createElement("div");
    previewBox.style.display = "flex";
    previewBox.style.flexWrap = "wrap";
    fileInput.parentNode.appendChild(previewBox);

    // ------------------------
    // DRAG & DROP EVENTS
    // ------------------------
    dz.addEventListener("dragover", (e) => {
        e.preventDefault();
        dz.style.borderColor = "#28a745";
    });

    dz.addEventListener("dragleave", () => {
        dz.style.borderColor = "#888";
    });

    dz.addEventListener("drop", (e) => {
        e.preventDefault();
        fileInput.files = e.dataTransfer.files;
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener("change", (e) => {
        handleFiles(e.target.files);
    });

    // ------------------------
    // HANDLE FILES + PREVIEW
    // ------------------------
    function handleFiles(files) {
        previewBox.innerHTML = "";
        Array.from(files).forEach(file => {
            const img = document.createElement("img");
            img.className = "preview-thumb";
            img.file = file;

            previewBox.appendChild(img);

            const reader = new FileReader();
            reader.onload = (e) => {
                img.src = e.target.result;
                enableCrop(img, file);
            };
            reader.readAsDataURL(file);
        });
    }

    // ------------------------
    // CROP USING CROPPER JS
    // ------------------------
    function enableCrop(img, file) {
        img.addEventListener("click", function () {
            const modal = document.createElement("div");
            modal.style.cssText = `
                position: fixed; top:0; left:0; right:0; bottom:0;
                background: rgba(0,0,0,0.7); display:flex;
                align-items:center; justify-content:center;
                z-index: 9999;
            `;

            const wrapper = document.createElement("div");
            wrapper.style.background = "#fff";
            wrapper.style.padding = "20px";
            wrapper.style.borderRadius = "8px";

            const cropImg = document.createElement("img");
            cropImg.src = img.src;

            wrapper.appendChild(cropImg);
            modal.appendChild(wrapper);
            document.body.appendChild(modal);

            const cropper = new Cropper(cropImg, {
                aspectRatio: 1,
                viewMode: 2,
            });

            // SAVE BUTTON
            const saveBtn = document.createElement("button");
            saveBtn.innerText = "Save Crop";
            saveBtn.style.marginTop = "10px";
            wrapper.appendChild(saveBtn);

            saveBtn.onclick = () => {
                cropper.getCroppedCanvas().toBlob((blob) => {
                    const newFile = new File([blob], file.name.replace(/\.\w+$/, ".webp"), {
                        type: "image/webp",
                    });

                    replaceFile(fileInput, file, newFile);
                }, "image/webp");

                document.body.removeChild(modal);
            };
        });
    }

    // REPLACE FILE in input.files
    function replaceFile(input, oldFile, newFile) {
        const dt = new DataTransfer();

        Array.from(input.files).forEach(f => {
            dt.items.add(f === oldFile ? newFile : f);
        });

        input.files = dt.files;
    }
});
