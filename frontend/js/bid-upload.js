/**
 * BidUpload — handles PDF bid document upload, parsing, and quote creation.
 *
 * Uses:
 *   POST /api/bid/upload           — upload PDF, extract scope
 *   POST /api/bid/{id}/quote-items — create quote sessions from selected items
 */

const BidUpload = {
    currentBidId: null,

    initBidUpload() {
        const dropZone = document.getElementById('bid-drop-zone');
        const fileInput = document.getElementById('bid-file-input');
        if (!dropZone || !fileInput) return;

        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) this._handleBidFile(file);
        });

        fileInput.addEventListener('change', () => {
            const file = fileInput.files[0];
            if (file) this._handleBidFile(file);
        });
    },

    async _handleBidFile(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('Please select a PDF file.');
            return;
        }
        if (file.size > 50 * 1024 * 1024) {
            alert('File too large. Maximum size is 50 MB.');
            return;
        }

        const dropZone = document.getElementById('bid-drop-zone');
        const resultsDiv = document.getElementById('bid-results');

        // Show progress
        dropZone.innerHTML = '<div class="spinner"></div><p class="processing-text">Uploading and analyzing bid document...</p>';

        try {
            const formData = new FormData();
            formData.append('file', file);

            const resp = await fetch('/api/bid/upload', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + Api.getToken() },
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || 'Upload failed');
            }

            const data = await resp.json();
            this._displayBidResults(data);
        } catch (err) {
            dropZone.innerHTML = '<p style="color:var(--error)">Error: ' + err.message + '</p>'
                + '<p style="margin-top:8px;cursor:pointer;color:var(--accent)" '
                + 'onclick="BidUpload._resetDropZone()">Try again</p>';
        }
    },

    _resetDropZone() {
        const dropZone = document.getElementById('bid-drop-zone');
        if (dropZone) {
            dropZone.innerHTML = '<p>Drop PDF here or click to select</p>';
        }
        const fileInput = document.getElementById('bid-file-input');
        if (fileInput) fileInput.value = '';
        const resultsDiv = document.getElementById('bid-results');
        if (resultsDiv) resultsDiv.style.display = 'none';
    },

    _displayBidResults(data) {
        const dropZone = document.getElementById('bid-drop-zone');
        const resultsDiv = document.getElementById('bid-results');

        this.currentBidId = data.bid_id;
        const items = data.scope_items || [];

        dropZone.innerHTML = '<p>Uploaded: ' + (data.filename || 'bid document') + '</p>';

        if (!items.length) {
            resultsDiv.innerHTML = '<p>No metal fabrication scope items found in this document.</p>';
            resultsDiv.style.display = 'block';
            return;
        }

        let html = '<h3>Extracted Scope Items</h3>'
            + '<p class="bid-hint">Select items to create quote sessions:</p>'
            + '<div class="bid-results-list">';

        items.forEach((item, idx) => {
            html += '<div class="bid-item">'
                + '<label><input type="checkbox" class="bid-item-check" data-idx="' + idx + '" checked> '
                + '<strong>' + (item.description || item.title || 'Item ' + (idx + 1)) + '</strong></label>';
            if (item.csi_division) {
                html += ' <span style="color:var(--text-secondary);font-size:0.8rem">'
                    + '(CSI ' + item.csi_division + ')</span>';
            }
            if (item.quantity) {
                html += ' <span style="font-size:0.85rem">Qty: ' + item.quantity + '</span>';
            }
            html += '</div>';
        });

        html += '</div>'
            + '<div style="margin-top:16px;display:flex;gap:8px">'
            + '<button class="btn btn-primary" onclick="BidUpload._createQuotesFromBid()">Create Quotes from Selected</button>'
            + '<button class="btn btn-secondary" onclick="BidUpload._resetDropZone()">Upload Different File</button>'
            + '</div>';

        resultsDiv.innerHTML = html;
        resultsDiv.style.display = 'block';
    },

    async _createQuotesFromBid() {
        if (!this.currentBidId) return;

        const checkboxes = document.querySelectorAll('.bid-item-check:checked');
        const selectedIndices = Array.from(checkboxes).map(cb => parseInt(cb.dataset.idx));

        if (!selectedIndices.length) {
            alert('Select at least one item.');
            return;
        }

        try {
            const resp = await fetch('/api/bid/' + this.currentBidId + '/quote-items', {
                method: 'POST',
                headers: {
                    'Authorization': 'Bearer ' + Api.getToken(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ selected_indices: selectedIndices }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to create quotes');
            }

            const data = await resp.json();
            const count = (data.sessions || []).length;
            alert(count + ' quote session(s) created. Switch to "New Quote" to continue.');
            this._resetDropZone();
        } catch (err) {
            alert('Error: ' + err.message);
        }
    },
};
