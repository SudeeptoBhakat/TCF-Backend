document.addEventListener('DOMContentLoaded', function () {
  // try to find our upload_files input created by the form
  let uploadInput = document.querySelector('input[name="upload_files"]');
  if (!uploadInput) {
    // If the form didn't render upload_files (customizations), create it next to media_file
    let mediaFile = document.querySelector('input[name="media_file"]');
    if (mediaFile) {
      uploadInput = document.createElement('input');
      uploadInput.type = 'file';
      uploadInput.name = 'upload_files';
      uploadInput.multiple = true;
      uploadInput.style.display = 'block';
      mediaFile.parentNode.insertBefore(uploadInput, mediaFile.nextSibling);
    }
  }

  if (uploadInput) {
    // create small UI element to show how many files are chosen
    let info = document.createElement('div');
    info.style.marginTop = '6px';
    info.style.fontSize = '0.9em';
    uploadInput.parentNode.insertBefore(info, uploadInput.nextSibling);

    uploadInput.addEventListener('change', function (ev) {
      const files = uploadInput.files;
      if (!files || files.length === 0) {
        info.textContent = 'No files selected';
        return;
      }
      info.textContent = files.length + ' file(s) selected';
      // optional: show small thumbnails (requires reading files and creating object URLs)
      // keep this minimal to avoid heavy DOM ops in admin.
    });
  }
});
