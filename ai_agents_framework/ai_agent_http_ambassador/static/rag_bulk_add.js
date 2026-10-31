"use strict";
const filePicker = document.getElementById("bulk-files");
const folderPicker = document.getElementById("bulk-folders");
const uploadButton = document.getElementById("bulk-upload");
const selectionSummary = document.getElementById("selection-summary");
const statusBox = document.getElementById("status");
const progress = document.getElementById("bulk-progress");
const resultBox = document.getElementById("result");
const parameterInputs = [...document.querySelectorAll("[data-parameter]")];
const selectedFiles = new Map();
const selectedFolders = new Set();

function relativePath(file) {
  return file.webkitRelativePath || file.name;
}

function addSelection(fileList) {
  for (const file of fileList) {
    const path = relativePath(file);
    selectedFiles.set(path, file);
    if (file.webkitRelativePath) {
      selectedFolders.add(file.webkitRelativePath.split("/", 1)[0]);
    }
  }
  const folderSummary = selectedFolders.size
    ? ` from ${selectedFolders.size} folder(s)`
    : "";
  selectionSummary.textContent = selectedFiles.size
    ? `${selectedFiles.size} file(s) selected${folderSummary}.`
    : "No files selected.";
  uploadButton.disabled = selectedFiles.size === 0;
}

for (const picker of [filePicker, folderPicker]) {
  picker.addEventListener("change", () => {
    addSelection(picker.files);
    picker.value = "";
  });
}

function requestSettings() {
  return Object.fromEntries(
    parameterInputs.map((input) => [input.dataset.parameter, input.value])
  );
}

function uploadConcurrency(settings) {
  const requested = Number(settings[uploadConcurrencyParameter] || 4);
  return Math.max(1, Math.min(8, requested));
}

async function readJson(response) {
  const result = await response.json();
  if (!response.ok) {
    const failedCount = result.result && Array.isArray(result.result.failed)
      ? result.result.failed.length
      : 0;
    const error = new Error(
      result.error || result.error_description ||
      (failedCount
        ? `Bulk ingestion finished with ${failedCount} failed file(s).`
        : "Bulk upload failed")
    );
    error.payload = result;
    throw error;
  }
  return result;
}

async function uploadOne(uploadId, path, file) {
  const query = new URLSearchParams({upload_id: uploadId, path});
  const response = await fetch(`${window.location.pathname}?${query}`, {
    method: "PUT",
    headers: {"Content-Type": "application/octet-stream"},
    body: file,
  });
  return readJson(response);
}

uploadButton.addEventListener("click", async () => {
  const entries = [...selectedFiles.entries()];
  if (!entries.length) return;

  const settings = requestSettings();
  const failures = [];
  let completed = 0;
  let uploadId = null;
  uploadButton.disabled = true;
  filePicker.disabled = true;
  folderPicker.disabled = true;
  for (const input of parameterInputs) input.disabled = true;
  resultBox.textContent = "";
  progress.hidden = false;
  progress.max = entries.length;
  progress.value = 0;

  try {
    statusBox.textContent = "Starting bulk RAG upload...";
    const startResponse = await fetch(window.location.pathname, {
      method: requestMethod,
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(settings),
    });
    const started = await readJson(startResponse);
    uploadId = started.upload_id;

    let nextIndex = 0;
    const worker = async () => {
      while (nextIndex < entries.length) {
        const index = nextIndex++;
        const [path, file] = entries[index];
        try {
          await uploadOne(uploadId, path, file);
        } catch (error) {
          failures.push({path, error: error.message});
        } finally {
          completed += 1;
          progress.value = completed;
          statusBox.textContent = `Uploaded ${completed} of ${entries.length} file(s)...`;
        }
      }
    };
    const workerCount = Math.min(uploadConcurrency(settings), entries.length);
    await Promise.all(Array.from({length: workerCount}, worker));

    statusBox.textContent = "Finalizing RAG ingestion...";
    const finishQuery = new URLSearchParams({upload_id: uploadId});
    const finishResponse = await fetch(
      `${window.location.pathname}?${finishQuery}`,
      {method: "PATCH"}
    );
    const finished = await readJson(finishResponse);
    resultBox.textContent = JSON.stringify(
      {upload_failures: failures, ...finished},
      null,
      2
    );
    const statistics = finished.result && finished.result.statistics;
    statusBox.textContent = statistics
      ? `Bulk ingestion finished: ${statistics.added} added, ${statistics.failed} failed.`
      : "Bulk ingestion finished.";
    if (!failures.length) {
      selectedFiles.clear();
      selectedFolders.clear();
      selectionSummary.textContent = "No files selected.";
    }
  } catch (error) {
    statusBox.textContent = error.message;
    if (error.payload) {
      resultBox.textContent = JSON.stringify(error.payload, null, 2);
    }
  } finally {
    progress.hidden = true;
    filePicker.disabled = false;
    folderPicker.disabled = false;
    for (const input of parameterInputs) input.disabled = false;
    uploadButton.disabled = selectedFiles.size === 0;
  }
});
