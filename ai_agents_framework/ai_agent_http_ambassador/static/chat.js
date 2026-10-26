"use strict";
const form = document.getElementById("chat-form");
const message = document.getElementById("message");
const includeHistory = document.getElementById("include-history");
const systemPrompt = document.getElementById("system-prompt");
const history = document.getElementById("history");
const status = document.getElementById("status");
const submit = document.getElementById("submit");
// The agent's API is stateless. Keep this conversation in this browser tab and
// pass previous turns as context in user_prompt on each successful submission.
const turns = [];
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = message.value;
  if (!text.trim() || submit.disabled) return;
  const prompt = includeHistory.checked
    ? [...turns, {role: "User", text}]
      .map((turn) => `${turn.role}:\n${turn.text}`).join("\n\n")
    : text;
  submit.disabled = true;
  status.textContent = "Waiting for the agent…";
  try {
    const response = await fetch(window.location.pathname, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({user_prompt: prompt, system_prompt: systemPrompt.value}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.error_msg || "Chat request failed");
    const reply = typeof result.response === "string" ? result.response : JSON.stringify(result.response);
    turns.push({role: "User", text}, {role: "Assistant", text: reply});
    history.value = turns.map((turn) => `${turn.role}:\n${turn.text}`).join("\n\n");
    history.scrollTop = history.scrollHeight;
    message.value = "";
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
    message.focus();
  }
});
