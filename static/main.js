/* ==========================================================================
   CosmosUI v2.0 - Core Frontend Script Logic
   Handles Modals, JSON validation, AJAX CRUD, pagination, and dropdowns.
   ========================================================================== */

// --- Dynamic Variables for the Document Editor ---
let activeEditMode = "edit"; // 'edit' or 'create'
let activeDeleteItem = { id: null, pkVal: null };

// --- 1. Dropdown Navigation ---
function toggleDropdown(id) {
    const dropdown = document.getElementById(id);
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
}

// Close dropdowns if user clicks outside
window.addEventListener('click', function(e) {
    if (!e.target.closest('.export-group')) {
        document.querySelectorAll('.dropdown-menu').forEach(el => {
            el.classList.remove('active');
        });
    }
});

// --- 2. Generic Modal Actions ---
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden'; // prevent bg scroll
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modals when clicking backdrop
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeModal(this.id);
        }
    });
});

// --- 3. Dynamic Search Input Formatting ---
function toggleSearchMode(mode) {
    const input = document.getElementById('search_query');
    if (!input) return;
    
    if (mode === 'advanced') {
        input.placeholder = "c.category = 'Electronics' AND c.price > 49.99";
    } else {
        input.placeholder = "Search by document ID...";
    }
}

// --- 4. Pagination / Page Limit Selector ---
function changePageSize(size) {
    const url = new URL(window.location.href);
    url.searchParams.set('limit', size);
    url.searchParams.set('page', '1'); // reset to page 1
    window.location.href = url.toString();
}

// --- 5. Bulk Import Upload File UI ---
function updateFileNameDisplay(input) {
    const display = document.getElementById('importFileName');
    if (display) {
        if (input.files && input.files.length > 0) {
            display.textContent = input.files[0].name;
            display.style.color = '#fff';
            display.style.fontWeight = '500';
        } else {
            display.textContent = "No file chosen";
            display.style.color = '';
            display.style.fontWeight = '';
        }
    }
}

function openImportModal() {
    // Reset file input
    const fileInput = document.getElementById('importFile');
    if (fileInput) fileInput.value = '';
    
    const display = document.getElementById('importFileName');
    if (display) display.textContent = "No file chosen";
    
    openModal('importModal');
}

// --- 6. JSON Editor Workspace Code Logic ---
const textarea = document.getElementById('jsonEditor');
const errorBanner = document.getElementById('jsonErrorBanner');
const errorMessage = document.getElementById('jsonErrorMessage');
const btnSave = document.getElementById('btnSaveDocument');

if (textarea) {
    textarea.addEventListener('input', validateJsonOnInput);
}

function validateJsonOnInput() {
    const val = textarea.value.strip ? textarea.value.strip() : textarea.value.trim();
    if (!val) {
        setEditorError(true, "Document JSON cannot be empty.");
        return false;
    }
    
    try {
        const obj = JSON.parse(val);
        
        // Ensure id property is present
        if (!obj.hasOwnProperty('id') || String(obj.id).trim() === "") {
            setEditorError(true, "Document must contain a non-empty string 'id' attribute at the top level.");
            return false;
        }

        // Ensure partition key is present
        if (CONFIG && CONFIG.cleanPk) {
            const pkPathParts = CONFIG.cleanPk.split('/');
            // For simple top-level partition keys, we check top-level key existence
            if (pkPathParts.length === 1) {
                const pk = pkPathParts[0];
                if (!obj.hasOwnProperty(pk) || obj[pk] === null) {
                    setEditorError(true, `Document must contain the partition key attribute: '${pk}'`);
                    return false;
                }
            }
        }
        
        setEditorError(false);
        return true;
    } catch (err) {
        setEditorError(true, "JSON Syntax Error: " + err.message);
        return false;
    }
}

function setEditorError(hasError, message = "") {
    if (hasError) {
        errorMessage.textContent = message;
        errorBanner.classList.add('active');
        btnSave.disabled = true;
        btnSave.style.opacity = '0.5';
        btnSave.style.cursor = 'not-allowed';
    } else {
        errorBanner.classList.remove('active');
        btnSave.disabled = false;
        btnSave.style.opacity = '';
        btnSave.style.cursor = '';
    }
}

function formatEditorJson() {
    const val = textarea.value.trim();
    if (!val) return;
    try {
        const obj = JSON.parse(val);
        textarea.value = JSON.stringify(obj, null, 2);
        validateJsonOnInput();
    } catch (err) {
        setEditorError(true, "Format failed! JSON Syntax Error: " + err.message);
    }
}

function openCreateModal() {
    activeEditMode = "create";
    document.getElementById('modalTitle').textContent = "Create New Document";
    
    // Create template skeleton
    const skeleton = {
        id: "new-doc-id"
    };
    
    // Inject the partition key attribute if configured
    if (CONFIG && CONFIG.cleanPk) {
        const pkParts = CONFIG.cleanPk.split('/');
        if (pkParts.length === 1 && pkParts[0] !== 'id') {
            skeleton[pkParts[0]] = "default-value";
        }
    }
    
    textarea.value = JSON.stringify(skeleton, null, 2);
    setEditorError(false);
    openModal('documentModal');
}

function openEditModal(rawItem) {
    activeEditMode = "edit";
    document.getElementById('modalTitle').textContent = "Edit Document: " + rawItem.id;
    textarea.value = JSON.stringify(rawItem, null, 2);
    setEditorError(false);
    openModal('documentModal');
}

// --- 7. Save Document (Create/Update AJAX) ---
function saveDocument() {
    if (!validateJsonOnInput()) return;
    
    const bodyText = textarea.value.trim();
    const data = JSON.parse(bodyText);
    
    const url = `/cosmos-ui/api/db/${CONFIG.dbId}/container/${CONFIG.containerId}/item`;
    
    // Disable save button to prevent double-submit
    btnSave.disabled = true;
    btnSave.querySelector('span').textContent = "Saving...";
    
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(res => {
        if (res.status === 'success') {
            closeModal('documentModal');
            // Refresh container to display saved item
            window.location.reload();
        } else {
            setEditorError(true, res.message || "Failed to save document.");
            btnSave.disabled = false;
            btnSave.querySelector('span').textContent = "Save Document";
        }
    })
    .catch(err => {
        console.error(err);
        setEditorError(true, "Network connection error: " + err.message);
        btnSave.disabled = false;
        btnSave.querySelector('span').textContent = "Save Document";
    });
}

// --- 8. Confirm Delete Flow ---
function confirmDelete(id, pkVal) {
    activeDeleteItem = { id: id, partitionKey: pkVal };
    document.getElementById('deleteItemIdDisplay').textContent = id;
    openModal('deleteModal');
}

function executeDelete() {
    const btnConfirm = document.getElementById('btnConfirmDelete');
    btnConfirm.disabled = true;
    btnConfirm.querySelector('span').textContent = "Deleting...";

    const url = `/cosmos-ui/api/db/${CONFIG.dbId}/container/${CONFIG.containerId}/item/delete`;

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            id: activeDeleteItem.id,
            partition_key: activeDeleteItem.partitionKey
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.status === 'success') {
            closeModal('deleteModal');
            window.location.reload();
        } else {
            alert("Error: " + res.message);
            btnConfirm.disabled = false;
            btnConfirm.querySelector('span').textContent = "Delete";
        }
    })
    .catch(err => {
        console.error(err);
        alert("Delete failed due to network error.");
        btnConfirm.disabled = false;
        btnConfirm.querySelector('span').textContent = "Delete";
    });
}

// --- 9. Theme Management Logic ---
function initTheme() {
    const storedTheme = localStorage.getItem("theme") || "dark";
    if (storedTheme === "light") {
        document.body.classList.add("light-theme");
        updateThemeToggleButton(true);
    } else {
        document.body.classList.remove("light-theme");
        updateThemeToggleButton(false);
    }
}

function toggleTheme() {
    const isCurrentlyLight = document.body.classList.contains("light-theme");
    if (isCurrentlyLight) {
        document.body.classList.remove("light-theme");
        localStorage.setItem("theme", "dark");
        updateThemeToggleButton(false);
    } else {
        document.body.classList.add("light-theme");
        localStorage.setItem("theme", "light");
        updateThemeToggleButton(true);
    }
}

function updateThemeToggleButton(isLight) {
    const toggleBtns = document.querySelectorAll("#themeToggle");
    toggleBtns.forEach(btn => {
        const icon = btn.querySelector("i");
        if (icon) {
            if (isLight) {
                icon.className = "fa-solid fa-sun";
            } else {
                icon.className = "fa-solid fa-moon";
            }
        }
    });
}

// Initialize theme immediately on script execute or DOMContentLoaded
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTheme);
} else {
    initTheme();
}

/// --- 10. Database and Container Provisioning ---
function toggleDbSource(source) {
    const selectWrapper = document.getElementById("db_select_wrapper");
    const inputWrapper = document.getElementById("db_input_wrapper");
    const dbInput = document.getElementById("create_db_id");
    
    if (source === "existing") {
        if (selectWrapper) selectWrapper.style.display = "block";
        if (inputWrapper) inputWrapper.style.display = "none";
        if (dbInput) dbInput.removeAttribute("required");
    } else {
        if (selectWrapper) selectWrapper.style.display = "none";
        if (inputWrapper) inputWrapper.style.display = "block";
        if (dbInput) dbInput.setAttribute("required", "true");
    }
}

function toggleModalDbSource(source) {
    const selectWrapper = document.getElementById("modal_db_select_wrapper");
    const inputWrapper = document.getElementById("modal_db_input_wrapper");
    const dbInput = document.getElementById("modal_db_id");
    
    if (source === "existing") {
        if (selectWrapper) selectWrapper.style.display = "block";
        if (inputWrapper) inputWrapper.style.display = "none";
        if (dbInput) dbInput.removeAttribute("required");
    } else {
        if (selectWrapper) selectWrapper.style.display = "none";
        if (inputWrapper) inputWrapper.style.display = "block";
        if (dbInput) dbInput.setAttribute("required", "true");
    }
}

function handleSingleCreate(e) {
    e.preventDefault();
    let dbId = "";
    const dbSourceRadio = document.querySelector("input[name='db_source']:checked");
    const dbSource = dbSourceRadio ? dbSourceRadio.value : "new";
    
    if (dbSource === "existing") {
        const selectEl = document.getElementById("create_db_select");
        dbId = selectEl ? selectEl.value : "";
    } else {
        const inputEl = document.getElementById("create_db_id");
        dbId = inputEl ? inputEl.value.trim() : "";
    }
    
    const containerEl = document.getElementById("create_container_id");
    const containerId = containerEl ? containerEl.value.trim() : "";
    const pkEl = document.getElementById("create_partition_key");
    const partitionKey = pkEl ? pkEl.value.trim() : "";
    
    submitProvisionRequest(dbId, containerId, partitionKey, "singleCreateForm");
}

function handleGlobalCreate(e) {
    e.preventDefault();
    let dbId = "";
    const dbSourceRadio = document.querySelector("input[name='modal_db_source']:checked");
    const dbSource = dbSourceRadio ? dbSourceRadio.value : "new";
    
    if (dbSource === "existing") {
        const selectEl = document.getElementById("modal_db_select");
        dbId = selectEl ? selectEl.value : "";
    } else {
        const inputEl = document.getElementById("modal_db_id");
        dbId = inputEl ? inputEl.value.trim() : "";
    }
    
    const containerEl = document.getElementById("modal_container_id");
    const containerId = containerEl ? containerEl.value.trim() : "";
    const pkEl = document.getElementById("modal_partition_key");
    const partitionKey = pkEl ? pkEl.value.trim() : "";
    
    submitProvisionRequest(dbId, containerId, partitionKey, "globalCreateModal");
}

function submitProvisionRequest(dbId, containerId, partitionKey, sourceElementId) {
    let submitBtn = null;
    if (sourceElementId === "singleCreateForm") {
        submitBtn = document.querySelector("#singleCreateForm button[type='submit']");
    } else {
        submitBtn = document.getElementById("btnGlobalCreate");
    }
    
    const originalBtnText = submitBtn ? submitBtn.innerHTML : "";
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> <span>Provisioning...</span>";
    }
    
    fetch("/cosmos-ui/api/provision", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            db_id: dbId,
            container_id: containerId,
            partition_key: partitionKey
        })
    })
    .then(res => res.json())
    .then(res => {
        if (res.status === "success") {
            if (sourceElementId === "globalCreateModal") {
                closeModal("globalCreateModal");
            }
            alert(res.message);
            window.location.reload();
        } else {
            alert("Error provisioning resources: " + res.message);
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        }
    })
    .catch(err => {
        console.error(err);
        alert("Provisioning failed due to network error.");
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        }
    });
}

function openCreateStructureModal() {
    // Reset global modal inputs
    const dbField = document.getElementById("modal_db_id");
    const containerField = document.getElementById("modal_container_id");
    const pkField = document.getElementById("modal_partition_key");
    if (dbField) dbField.value = "";
    if (containerField) containerField.value = "";
    if (pkField) pkField.value = "/id";
    
    // Default modal source to existing if we have options, otherwise new
    const existingRadio = document.querySelector("input[name='modal_db_source'][value='existing']");
    if (existingRadio) {
        existingRadio.checked = true;
        toggleModalDbSource("existing");
    } else {
        const newRadio = document.querySelector("input[name='modal_db_source'][value='new']");
        if (newRadio) newRadio.checked = true;
        toggleModalDbSource("new");
    }
    
    openModal("globalCreateModal");
}

function updateBulkFileNameDisplay(input) {
    const display = document.getElementById('bulkCreateFileName');
    if (display) {
        if (input.files && input.files.length > 0) {
            display.textContent = input.files[0].name;
            display.style.color = 'var(--text-white)';
            display.style.fontWeight = '500';
        } else {
            display.textContent = "Choose CSV or Excel file";
            display.style.color = '';
            display.style.fontWeight = '';
        }
    }
}

// --- 11. Secure Database Deletion ---
let activeDeleteDbId = null;

function confirmDeleteDb(dbId) {
    activeDeleteDbId = dbId;
    document.getElementById("deleteDbNameDisplay").textContent = dbId;
    document.getElementById("delete_db_confirm_input").value = "";
    document.getElementById("deleteDbError").style.display = "none";
    openModal("deleteDbModal");
}

function executeDeleteDb(e) {
    e.preventDefault();
    const confirmInput = document.getElementById("delete_db_confirm_input").value.trim();
    const errorBanner = document.getElementById("deleteDbError");
    
    if (confirmInput !== activeDeleteDbId) {
        errorBanner.style.display = "block";
        errorBanner.textContent = `Database ID does not match. Expected: ${activeDeleteDbId}`;
        return;
    }
    
    errorBanner.style.display = "none";
    const btnConfirm = document.getElementById("btnConfirmDeleteDb");
    btnConfirm.disabled = true;
    btnConfirm.querySelector("span").textContent = "Deleting...";
    
    fetch(`/cosmos-ui/api/db/${activeDeleteDbId}/delete`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        }
    })
    .then(res => res.json())
    .then(res => {
        if (res.status === "success") {
            closeModal("deleteDbModal");
            alert(res.message);
            window.location.href = "/cosmos-ui/dashboard";
        } else {
            alert("Error deleting database: " + res.message);
            btnConfirm.disabled = false;
            btnConfirm.querySelector("span").textContent = "Delete Database";
        }
    })
    .catch(err => {
        console.error(err);
        alert("Database deletion failed due to network error.");
        btnConfirm.disabled = false;
        btnConfirm.querySelector("span").textContent = "Delete Database";
    });
}

// --- 12. Secure Container Deletion ---
let activeDeleteContainerDbId = null;
let activeDeleteContainerId = null;

function confirmDeleteContainer(dbId, containerId) {
    activeDeleteContainerDbId = dbId;
    activeDeleteContainerId = containerId;
    document.getElementById("deleteContainerNameDisplay").textContent = containerId;
    document.getElementById("delete_container_confirm_input").value = "";
    document.getElementById("deleteContainerError").style.display = "none";
    openModal("deleteContainerModal");
}

function executeDeleteContainer(e) {
    e.preventDefault();
    const confirmInput = document.getElementById("delete_container_confirm_input").value.trim();
    const errorBanner = document.getElementById("deleteContainerError");
    
    if (confirmInput !== activeDeleteContainerId) {
        errorBanner.style.display = "block";
        errorBanner.textContent = `Container ID does not match. Expected: ${activeDeleteContainerId}`;
        return;
    }
    
    errorBanner.style.display = "none";
    const btnConfirm = document.getElementById("btnConfirmDeleteContainer");
    btnConfirm.disabled = true;
    btnConfirm.querySelector("span").textContent = "Deleting...";
    
    fetch(`/cosmos-ui/api/db/${activeDeleteContainerDbId}/container/${activeDeleteContainerId}/delete`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        }
    })
    .then(res => res.json())
    .then(res => {
        if (res.status === "success") {
            closeModal("deleteContainerModal");
            alert(res.message);
            
            // Redirect to dashboard if we deleted the container we were currently viewing
            if (typeof CONFIG !== "undefined" && CONFIG.dbId === activeDeleteContainerDbId && CONFIG.containerId === activeDeleteContainerId) {
                window.location.href = "/cosmos-ui/dashboard";
            } else {
                window.location.reload();
            }
        } else {
            alert("Error deleting container: " + res.message);
            btnConfirm.disabled = false;
            btnConfirm.querySelector("span").textContent = "Delete Container";
        }
    })
    .catch(err => {
        console.error(err);
        alert("Container deletion failed due to network error.");
        btnConfirm.disabled = false;
        btnConfirm.querySelector("span").textContent = "Delete Container";
    });
}

// --- 13. Bulk Create Flow ---
document.addEventListener("DOMContentLoaded", () => {
    const bulkForm = document.getElementById("bulkCreateForm");
    if (bulkForm) {
        bulkForm.addEventListener("submit", function(e) {
            e.preventDefault();
            
            const formData = new FormData(bulkForm);
            
            // Show loading state on button
            const btn = bulkForm.querySelector('button[type="submit"]');
            const originalHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Checking...</span>';

            fetch("/cosmos-ui/api/bulk-check", {
                method: "POST",
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                
                if (data.status === "success") {
                    if (data.existing_dbs && data.existing_dbs.length > 0) {
                        const list = document.getElementById("bulkExistingDbsList");
                        if (list) {
                            list.innerHTML = "";
                            data.existing_dbs.forEach(db => {
                                const li = document.createElement("li");
                                li.textContent = db;
                                list.appendChild(li);
                            });
                        }
                        openModal("bulkConfirmModal");
                    } else {
                        // No existing DBs, submit immediately
                        submitBulkCreate("merge"); 
                    }
                } else {
                    alert("Error checking file: " + data.message);
                }
            })
            .catch(err => {
                console.error(err);
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                alert("Network error checking bulk upload.");
            });
        });
    }
});

function closeBulkConfirmModal() {
    closeModal("bulkConfirmModal");
}

function submitBulkCreate(mode) {
    const bulkForm = document.getElementById("bulkCreateForm");
    if (!bulkForm) return;
    
    // Remove existing mode input if any
    let existingModeInput = bulkForm.querySelector('input[name="mode"]');
    if (existingModeInput) {
        existingModeInput.remove();
    }
    
    // Add mode input
    const modeInput = document.createElement("input");
    modeInput.type = "hidden";
    modeInput.name = "mode";
    modeInput.value = mode;
    bulkForm.appendChild(modeInput);
    
    // Disable button to show loading
    const btn = bulkForm.querySelector('button[type="submit"]');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Uploading...</span>';
    }
    
    closeBulkConfirmModal();
    
    // Submit natively
    bulkForm.submit();
}
