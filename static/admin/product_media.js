/**
 * product_media.js
 * Simple native file input with a thumbnail preview box below it.
 * No drag-drop overlays, no hidden inputs. Fully accessible native clicks.
 */

(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    // 1. Find the native file input field
    const fileInput = document.querySelector('input.multi-image-simple-input[type="file"]');
    if (!fileInput) return;

    // 2. We want to place the Preview Box immediately after the file input's row.
    const fieldRow = fileInput.closest('.form-row') || fileInput.parentElement;
    if (!fieldRow) return;

    // 3. Build the Preview Box HTML
    const previewBox = document.createElement('div');
    previewBox.className = 'multi-image-preview-box';
    previewBox.innerHTML = `
      <div class="preview-box-header">Preview Selected Images (0)</div>
      <div class="upload-preview-strip">
        <div class="preview-empty-text">No images selected yet. Click the "Choose Files" button above.</div>
      </div>
    `;

    // 4. Insert the Preview Box right below the file upload field
    fieldRow.insertAdjacentElement('afterend', previewBox);

    const header = previewBox.querySelector('.preview-box-header');
    const strip = previewBox.querySelector('.upload-preview-strip');

    // 5. Listen to native 'change' event on the standard file input
    fileInput.addEventListener('change', function () {
      const files = this.files;
      const count = files.length;

      // Update header count
      header.textContent = `Preview Selected Images (${count})`;
      
      // Clear current previews
      strip.innerHTML = '';

      if (count === 0) {
        strip.innerHTML = '<div class="preview-empty-text">No images selected yet. Click the "Choose Files" button above.</div>';
        return;
      }

      // 6. Generate a thumbnail for each selected file natively
      for (let i = 0; i < count; i++) {
        const file = files[i];
        
        // Only preview images
        if (!file.type.startsWith('image/')) continue;

        const thumbWrapper = document.createElement('div');
        thumbWrapper.className = 'upload-preview-item';
        thumbWrapper.title = file.name;

        const img = document.createElement('img');
        const objectUrl = URL.createObjectURL(file);
        img.src = objectUrl;
        img.onload = function() {
          // Free memory
          URL.revokeObjectURL(objectUrl);
        };

        thumbWrapper.appendChild(img);
        strip.appendChild(thumbWrapper);
      }
    });

  });
})();
