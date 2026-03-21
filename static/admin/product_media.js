/**
 * product_media.js
 * Professional multi-image upload UI for Django Admin — ProductMedia
 *
 * CRITICAL FIX: fieldRow is captured BEFORE zone.appendChild(realInput)
 * because appendChild moves the element out of the DOM, making `.closest()`
 * return null and causing the entire upload zone to never be inserted.
 */

(function () {
  'use strict';

  const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

  document.addEventListener('DOMContentLoaded', function () {

    // ── 1. Locate the real file input ──────────────────────────────────────
    const realInput = document.querySelector('input.multi-image-upload-input[type="file"]');
    if (!realInput) return;

    // ── 2. Capture the parent BEFORE moving the input anywhere ────────────
    //    This MUST happen before zone.appendChild(realInput), because once
    //    the input is moved into an off-DOM element, .closest() returns null.
    const fieldRow = realInput.closest('.form-row')
                  || realInput.closest('.field-upload_images')
                  || realInput.parentElement;

    if (!fieldRow) return;

    // ── 3. Build the drag-drop zone wrapper ───────────────────────────────
    const zone = document.createElement('div');
    zone.className = 'multi-image-upload-zone';
    zone.innerHTML =
      '<div class="upload-icon">📁</div>' +
      '<div class="upload-label">' +
        '<strong>Click to browse</strong> or drag &amp; drop images here<br>' +
        '<span style="font-size:12px;color:#90a4ae;">JPG · PNG · WEBP · GIF — max 10 MB each</span>' +
      '</div>';

    // ── 4. Insert zone into the DOM first (while input is still there) ───
    fieldRow.insertBefore(zone, realInput);

    // ── 5. Now move the real input into the zone (overlay trick) ─────────
    //    The input is position:absolute / opacity:0 via CSS so the zone
    //    itself acts as the visible click target.
    zone.appendChild(realInput);

    // ── 6. File count label and thumbnail strip (siblings of zone) ────────
    const countLabel = document.createElement('div');
    countLabel.className = 'upload-file-count';

    const strip = document.createElement('div');
    strip.className = 'upload-preview-strip';

    // Insert after zone in the same parent
    zone.insertAdjacentElement('afterend', strip);
    zone.insertAdjacentElement('afterend', countLabel);

    // ── DataTransfer — lets us control the file list programmatically ─────
    let dt = new DataTransfer();

    // ── Helpers ───────────────────────────────────────────────────────────

    function syncInputFiles() {
      realInput.files = dt.files;
    }

    function formatBytes(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    }

    function updateCountLabel() {
      const n = dt.files.length;
      if (n === 0) {
        countLabel.textContent = '';
        return;
      }
      let totalSize = 0;
      for (let i = 0; i < dt.files.length; i++) totalSize += dt.files[i].size;
      countLabel.textContent =
        n + ' image' + (n !== 1 ? 's' : '') + ' selected (' + formatBytes(totalSize) + ' total)';
    }

    function buildThumbnail(file, index) {
      const item = document.createElement('div');
      item.className = 'upload-preview-item';
      item.dataset.index = index;

      const img = document.createElement('img');
      const objectUrl = URL.createObjectURL(file);
      img.src = objectUrl;
      img.alt = file.name;
      img.onload = function () { URL.revokeObjectURL(objectUrl); };

      const nameTag = document.createElement('div');
      nameTag.className = 'upload-preview-name';
      nameTag.textContent = file.name;
      nameTag.title = file.name;

      const removeBtn = document.createElement('button');
      removeBtn.className = 'upload-preview-remove';
      removeBtn.type = 'button';
      removeBtn.title = 'Remove this image';
      removeBtn.textContent = '\u00D7';   // ×
      removeBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        removeFile(parseInt(item.dataset.index, 10));
      });

      item.appendChild(img);
      item.appendChild(nameTag);
      item.appendChild(removeBtn);
      return item;
    }

    function rebuildStrip() {
      strip.innerHTML = '';
      for (let i = 0; i < dt.files.length; i++) {
        strip.appendChild(buildThumbnail(dt.files[i], i));
      }
      updateCountLabel();
    }

    function addFiles(fileList) {
      var skipped = 0;
      for (var i = 0; i < fileList.length; i++) {
        var f = fileList[i];
        if (!ALLOWED_TYPES.has(f.type)) {
          skipped++;
          continue;
        }
        dt.items.add(f);
      }
      if (skipped > 0) {
        alert(skipped + ' file(s) were skipped — not a valid image format (JPG/PNG/WEBP/GIF).');
      }
      syncInputFiles();
      rebuildStrip();
    }

    function removeFile(index) {
      var newDt = new DataTransfer();
      for (var i = 0; i < dt.files.length; i++) {
        if (i !== index) newDt.items.add(dt.files[i]);
      }
      dt = newDt;
      syncInputFiles();
      rebuildStrip();
    }

    // ── File input change ─────────────────────────────────────────────────
    realInput.addEventListener('change', function () {
      addFiles(this.files);
      // Reset so re-selecting same file fires 'change' again
      try { this.value = ''; } catch (e) { /* IE fallback */ }
    });

    // ── Drag-and-drop ─────────────────────────────────────────────────────
    zone.addEventListener('dragenter', function (e) {
      e.preventDefault();
      zone.classList.add('drag-over');
    });

    zone.addEventListener('dragover', function (e) {
      e.preventDefault();
      zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', function (e) {
      if (!zone.contains(e.relatedTarget)) {
        zone.classList.remove('drag-over');
      }
    });

    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (e.dataTransfer && e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    });

  });

}());
