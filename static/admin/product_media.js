/**
 * product_media.js
 * Professional multi-image upload UI for Django Admin — ProductMedia
 *
 * Features:
 *  - Wraps the file input in a styled drag-drop zone
 *  - Shows live thumbnail previews on file select / drop
 *  - "× " button to remove individual files before submit
 *  - File count + total size display
 *  - Client-side mime type guard (images only)
 */

(function () {
  'use strict';

  const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

  document.addEventListener('DOMContentLoaded', function () {
    // Locate the real file input rendered by MultipleFileInput widget
    const realInput = document.querySelector('input.multi-image-upload-input[type="file"]');
    if (!realInput) return;

    // ── Build the drag-drop zone wrapper ──────────────────────────────────
    const zone = document.createElement('div');
    zone.className = 'multi-image-upload-zone';
    zone.innerHTML = `
      <div class="upload-icon">📁</div>
      <div class="upload-label">
        <strong>Click to browse</strong> or drag &amp; drop images here<br>
        <span style="font-size:12px;color:#90a4ae;">JPG · PNG · WEBP · GIF — max 10 MB each</span>
      </div>
    `;

    // Move the real input inside the zone (it becomes the invisible click target)
    realInput.classList.add('multi-image-upload-input');
    zone.appendChild(realInput);

    // Insert the zone before the old input's parent row
    const fieldRow = realInput.closest('.form-row') || realInput.closest('div');
    if (fieldRow) {
      fieldRow.insertBefore(zone, fieldRow.firstChild);
    }

    // File count label
    const countLabel = document.createElement('div');
    countLabel.className = 'upload-file-count';
    zone.after(countLabel);

    // Thumbnail strip
    const strip = document.createElement('div');
    strip.className = 'upload-preview-strip';
    countLabel.after(strip);

    // ── DataTransfer — lets us control the file list programmatically ──
    let dt = new DataTransfer();

    // ── Helpers ───────────────────────────────────────────────────────────

    function syncInputFiles() {
      // Push our controlled DataTransfer back into the real input
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
      countLabel.textContent = `${n} image${n !== 1 ? 's' : ''} selected  (${formatBytes(totalSize)} total)`;
    }

    function buildThumbnail(file, index) {
      const item = document.createElement('div');
      item.className = 'upload-preview-item';
      item.dataset.index = index;

      const img = document.createElement('img');
      img.src = URL.createObjectURL(file);
      img.alt = file.name;
      img.onload = () => URL.revokeObjectURL(img.src);

      const nameTag = document.createElement('div');
      nameTag.className = 'upload-preview-name';
      nameTag.textContent = file.name;
      nameTag.title = file.name;

      const removeBtn = document.createElement('button');
      removeBtn.className = 'upload-preview-remove';
      removeBtn.type = 'button';
      removeBtn.title = 'Remove this image';
      removeBtn.textContent = '×';
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
        const thumb = buildThumbnail(dt.files[i], i);
        strip.appendChild(thumb);
      }
      updateCountLabel();
    }

    function addFiles(fileList) {
      let skipped = 0;
      for (let i = 0; i < fileList.length; i++) {
        const f = fileList[i];
        if (!ALLOWED_TYPES.has(f.type)) {
          skipped++;
          continue;
        }
        dt.items.add(f);
      }
      if (skipped > 0) {
        alert(`${skipped} file(s) were skipped because they are not valid image formats.`);
      }
      syncInputFiles();
      rebuildStrip();
    }

    function removeFile(index) {
      // Rebuild DataTransfer without the removed file
      const newDt = new DataTransfer();
      for (let i = 0; i < dt.files.length; i++) {
        if (i !== index) newDt.items.add(dt.files[i]);
      }
      dt = newDt;
      syncInputFiles();
      rebuildStrip();
    }

    // ── File input change handler ──────────────────────────────────────────
    realInput.addEventListener('change', function () {
      addFiles(this.files);
      // Clear the native value so next selection triggers change even for same file
      this.value = '';
    });

    // ── Drag-drop handlers ────────────────────────────────────────────────
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
      const dropped = e.dataTransfer ? e.dataTransfer.files : null;
      if (dropped && dropped.length > 0) {
        addFiles(dropped);
      }
    });
  });

}());
