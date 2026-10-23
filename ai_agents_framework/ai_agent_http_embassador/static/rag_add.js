"use strict";
const fileInput = document.getElementById("file");
const status = document.getElementById("status");
const resultBox = document.getElementById("result");
fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  fileInput.disabled = true;
  status.textContent = `Adding ${file.name}…`;
  resultBox.textContent = "";
  try {
    const response = await fetch(window.location.pathname, {
      method: "PUT",
      headers: {"Content-Type": "application/octet-stream"},
      body: file,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.error_msg || "Upload failed");
    status.textContent = `${file.name} was added to the knowledge base.`;
    resultBox.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    status.textContent = error.message;
  } finally {
    fileInput.disabled = false;
    fileInput.value = "";
  }
});
