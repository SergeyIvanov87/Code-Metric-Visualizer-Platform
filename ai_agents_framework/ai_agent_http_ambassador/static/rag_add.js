"use strict";
const fileInput = document.getElementById("file");
const status = document.getElementById("status");
const resultBox = document.getElementById("result");
const documentParameter = Object.entries(requestParameters)
  .find(([name, value]) => !name.startsWith("-") && value === "")?.[0];

if (!documentParameter) {
  throw new Error("Document schema has no inline-data parameter");
}

function encodeBase64(bytes) {
  let binary = "";
  const chunkSize = 32768;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  fileInput.disabled = true;
  status.textContent = `Adding ${file.name}…`;
  resultBox.textContent = "";
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const parameters = {[documentParameter]: encodeBase64(bytes)};
    const response = await fetch(window.location.pathname, {
      method: requestMethod,
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(parameters),
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
