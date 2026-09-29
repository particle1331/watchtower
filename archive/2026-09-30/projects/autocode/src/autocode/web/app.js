const state = {
  sessions: [],
  sessionId: null,
  events: new Map(),
  cursor: 0,
  socket: null,
  streaming: false,
};

const elements = {
  newSession: document.querySelector("#new-session"),
  sessionList: document.querySelector("#session-list"),
  sessionTitle: document.querySelector("#session-title"),
  timeline: document.querySelector("#timeline"),
  composer: document.querySelector("#composer"),
  message: document.querySelector("#message"),
  send: document.querySelector("#send-message"),
  cancel: document.querySelector("#cancel-run"),
  help: document.querySelector("#composer-help"),
  connection: document.querySelector("#connection-status"),
  connectionLabel: document.querySelector("#connection-label"),
  modeBadge: document.querySelector("#mode-badge"),
  searchForm: document.querySelector("#search-form"),
  searchQuery: document.querySelector("#search-query"),
  searchResults: document.querySelector("#search-results"),
  artifactFile: document.querySelector("#artifact-file"),
  artifactStatus: document.querySelector("#artifact-status"),
};

elements.newSession.addEventListener("click", createSession);
elements.composer.addEventListener("submit", submitMessage);
elements.cancel.addEventListener("click", cancelRun);
elements.searchForm.addEventListener("submit", searchHistory);
elements.artifactFile.addEventListener("change", uploadArtifact);
window.addEventListener("beforeunload", () => state.socket?.close());

boot().catch(showError);

async function boot() {
  const [sessions, config] = await Promise.all([
    request("/api/sessions"),
    request("/api/config"),
  ]);
  state.sessions = sessions;
  elements.modeBadge.textContent = `${config.agent_mode} agent`;
  renderSessions();
  if (sessions.length) {
    await selectSession(sessions[0].session_id);
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

async function createSession() {
  const session = await request("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title: `Session ${state.sessions.length + 1}` }),
  });
  state.sessions.unshift(session);
  renderSessions();
  await selectSession(session.session_id);
}

async function selectSession(sessionId) {
  state.socket?.close();
  const session = await request(`/api/sessions/${sessionId}`);
  state.sessionId = session.session_id;
  state.events = new Map(session.events.map((event) => [event.event_id, event]));
  state.cursor = Math.max(0, ...session.events.map((event) => event.cursor));
  state.streaming = false;
  elements.sessionTitle.textContent = session.title;
  renderSessions();
  renderTimeline();
  connectSocket();
}

function connectSocket() {
  if (!state.sessionId) return;
  setConnection("connecting");
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(
    `${scheme}://${window.location.host}/ws/sessions/${state.sessionId}?after=${state.cursor}`,
  );
  state.socket = socket;
  socket.addEventListener("open", () => {
    setConnection("online");
    setComposerEnabled(true);
  });
  socket.addEventListener("message", (message) => applyEvent(JSON.parse(message.data)));
  socket.addEventListener("close", () => {
    if (state.socket !== socket) return;
    setConnection("offline");
    setComposerEnabled(false);
    window.setTimeout(connectSocket, 900);
  });
  socket.addEventListener("error", () => setConnection("offline"));
}

function submitMessage(event) {
  event.preventDefault();
  const content = elements.message.value.trim();
  if (!content || state.socket?.readyState !== WebSocket.OPEN || state.streaming) return;
  state.socket.send(JSON.stringify({ type: "user_message", content }));
  elements.message.value = "";
  elements.help.textContent = "Message sent. Waiting for the durable event stream.";
}

function cancelRun() {
  if (state.socket?.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify({ type: "cancel" }));
  }
}

async function searchHistory(event) {
  event.preventDefault();
  const query = elements.searchQuery.value.trim();
  if (!query) return;
  const hits = await request(`/api/search?q=${encodeURIComponent(query)}`);
  elements.searchResults.replaceChildren();
  if (!hits.length) {
    elements.searchResults.append(systemNode("No fresh session-history match.", false));
    return;
  }
  for (const hit of hits) {
    const node = document.createElement("div");
    node.className = "search-hit";
    node.textContent = `${hit.document_id} · ${hit.score.toFixed(2)} · ${hit.text}`;
    elements.searchResults.append(node);
  }
}

async function uploadArtifact() {
  const file = elements.artifactFile.files?.[0];
  if (!file) return;
  elements.artifactStatus.textContent = `Uploading ${file.name}…`;
  const response = await fetch("/api/artifacts", {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: await file.arrayBuffer(),
  });
  if (!response.ok) {
    elements.artifactStatus.textContent = `Upload failed (${response.status})`;
    return;
  }
  const artifact = await response.json();
  elements.artifactStatus.textContent = `${file.name} stored as ${artifact.digest.slice(0, 12)}…`;
  elements.artifactFile.value = "";
}

function applyEvent(event) {
  if (event.type === "protocol_error") {
    showError(typeof event.detail === "string" ? event.detail : JSON.stringify(event.detail));
    return;
  }
  if (!event.event_id || state.events.has(event.event_id)) return;
  state.events.set(event.event_id, event);
  state.cursor = Math.max(state.cursor, event.cursor);
  if (event.kind === "run_started") state.streaming = true;
  if (["run_finished", "run_error", "agent_error"].includes(event.kind)) state.streaming = false;
  renderTimeline();
  setComposerEnabled(true);
}

function renderSessions() {
  elements.sessionList.replaceChildren();
  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-button";
    if (session.session_id === state.sessionId) button.setAttribute("aria-current", "page");
    const title = document.createElement("strong");
    title.textContent = session.title;
    const metadata = document.createElement("span");
    metadata.textContent = `${session.version ?? 0} events`;
    button.append(title, metadata);
    button.addEventListener("click", () => selectSession(session.session_id).catch(showError));
    elements.sessionList.append(button);
  }
}

function renderTimeline() {
  const events = [...state.events.values()].sort((left, right) => left.cursor - right.cursor);
  if (!events.length) {
    elements.timeline.replaceChildren(emptyState());
    return;
  }

  const nodes = [];
  let streamedText = "";
  for (const event of events) {
    if (event.kind === "user_message") {
      flushStream(nodes, streamedText, false);
      streamedText = "";
      nodes.push(messageNode("user", event.payload.content));
    } else if (event.kind === "text_delta") {
      streamedText += event.payload.content || "";
    } else if (event.kind === "assistant_message") {
      streamedText = "";
      nodes.push(messageNode("assistant", event.payload.content || ""));
    } else if (event.kind === "tool_started" || event.kind === "tool_finished") {
      nodes.push(toolNode(event));
    } else if (event.kind === "run_error" || event.kind === "agent_error") {
      flushStream(nodes, streamedText, false);
      streamedText = "";
      nodes.push(systemNode(event.payload.error || "Agent run failed", true));
    } else if (event.kind === "run_finished" && event.payload.reason === "cancelled") {
      flushStream(nodes, streamedText, false);
      streamedText = "";
      nodes.push(systemNode("Run cancelled", false));
    }
  }
  flushStream(nodes, streamedText, state.streaming);
  elements.timeline.replaceChildren(...nodes);
  elements.timeline.scrollTop = elements.timeline.scrollHeight;
}

function flushStream(nodes, content, streaming) {
  if (content) nodes.push(messageNode("assistant", content, streaming));
}

function messageNode(role, content, streaming = false) {
  const article = document.createElement("article");
  article.className = `message ${role}${streaming ? " streaming" : ""}`;
  article.textContent = content;
  return article;
}

function toolNode(event) {
  const card = document.createElement("div");
  card.className = "tool-card";
  const name = event.payload.name || "tool";
  card.textContent = `${name}: ${event.kind === "tool_started" ? "running" : event.payload.success === false ? "error" : "done"}`;
  return card;
}

function systemNode(content, isError) {
  const node = document.createElement("div");
  node.className = `system-event${isError ? " error" : ""}`;
  node.textContent = content;
  return node;
}

function emptyState() {
  const wrapper = document.createElement("div");
  wrapper.className = "empty-state";
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Durable session ready";
  const heading = document.createElement("h3");
  heading.textContent = "Send the first task.";
  const body = document.createElement("p");
  body.textContent = "The browser will send a command over WebSocket and rebuild this timeline from SQLite-backed events.";
  wrapper.append(eyebrow, heading, body);
  return wrapper;
}

function setConnection(value) {
  elements.connection.dataset.state = value;
  elements.connectionLabel.textContent = value;
}

function setComposerEnabled(connected) {
  elements.message.disabled = !connected || state.streaming;
  elements.send.disabled = !connected || state.streaming;
  elements.cancel.hidden = !state.streaming;
  elements.help.textContent = state.streaming
    ? "The run is streaming. Cancel records a terminal event."
    : connected
      ? "Enter sends. Refresh reconnects from the last durable cursor."
      : "Create or select a session to connect.";
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  elements.timeline.prepend(systemNode(message, true));
}
