// ---- Shared state ----
const appEl = document.getElementById("chat-app");
const currentUserId = appEl ? appEl.dataset.userId : null;
const chatLayout = document.querySelector(".messages-layout");
const chatStatus = document.getElementById("chat-status");
const messageInput = document.getElementById("message-input");
const chatDrafts = new Map();
let currentChatId = null;
let sending = false;
let typingTimeout = null;
let isTyping = false;
const socketio = io({ auth: { userId: currentUserId } });

/** Shows or clears the status banner under the chat heading. */
function showChatStatus(text = "") {
  chatStatus.textContent = text;
  chatStatus.hidden = !text;
  sizeConversation();
}
/** Enables or disables Send and shows the disconnected banner based on connection state. */
function updateConnection() {
  document.getElementById('send-btn').disabled = !socketio.connected || !navigator.onLine || sending;
  if (!socketio.connected || !navigator.onLine) showChatStatus('Messaging disconnected. Reconnecting… Your typed message will stay here.');
  else if (!sending) showChatStatus();
}
/** Fits the mobile conversation panel to the visible viewport height. */
function sizeConversation() {
  if (!window.matchMedia('(max-width: 767px)').matches) return;
  const viewport = window.visualViewport;
  const bottom = (viewport?.height || window.innerHeight) + (viewport?.offsetTop || 0);
  const top = chatLayout.getBoundingClientRect().top;
  const nav = document.querySelector('.platform-nav');
  const navHeight = nav && getComputedStyle(nav).position === 'fixed' ? nav.getBoundingClientRect().height : 0;
  chatLayout.style.setProperty('--chat-height', `${Math.max(140, bottom - top - navHeight - 12)}px`);
}
window.visualViewport?.addEventListener('resize', sizeConversation);
window.visualViewport?.addEventListener('scroll', sizeConversation);
window.addEventListener('resize', sizeConversation);
// Banners and the bottom navigation change the available space without resizing
// the viewport. Keep the composer in view when these elements change height.
if ('ResizeObserver' in window) {
  const layoutObserver = new ResizeObserver(sizeConversation);
  document.querySelectorAll('.pwa-toolbar, .platform-nav, .messages-heading, #chat-status').forEach(element => layoutObserver.observe(element));
}
sizeConversation();
document.getElementById('chat-back').addEventListener('click', () => {
  stopTyping();
  chatLayout.classList.remove('conversation-open');
  const selected = document.getElementById(`chat-${currentChatId}`);
  selected?.focus();
});

/** Reloads the open conversation so messages missed while disconnected appear. */
function refreshCurrentChat() {
  const selected = document.getElementById(`chat-${currentChatId}`);
  if (selected) getMessages(selected.dataset.displayName, currentChatId, true);
}

/** True when the user can currently see the open conversation. */
function isConversationVisible() {
  return document.visibilityState === "visible" &&
    (chatLayout.classList.contains("conversation-open") || !window.matchMedia("(max-width: 767px)").matches);
}

// ---- Socket and connection handlers ----
socketio.on("connect", () => {
  updateConnection();
  refreshCurrentChat();
});
socketio.on("disconnect", updateConnection);
window.addEventListener("offline", updateConnection);
window.addEventListener("online", updateConnection);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && socketio.connected) refreshCurrentChat();
});
updateConnection();
socketio.on("connect_error", function (error) {
  updateConnection();
  console.error("Messaging connection failed:", error.message);
});

socketio.on("message", function (msg) {
  updateChatSidebar(msg);
  if (String(msg.chatId) === String(currentChatId)) {
    hideTypingIndicator();
    if (isConversationVisible()) markChatRead(msg.chatId);
    createChatItem(msg, document.getElementById("chat-header").innerText);
  }
});

socketio.on("typing", function (update) {
  if (
    String(update.chatId) === String(currentChatId) &&
    String(update.senderId) !== String(currentUserId)
  ) {
    setTypingIndicator(update.isTyping, update.senderUsername);
  }
});

/** Shows "<username> is typing..." above the composer, or hides it. */
function setTypingIndicator(isTyping, username) {
  const indicator = document.getElementById("typing-indicator");
  if (!indicator) {
    return;
  }
  indicator.innerText = isTyping ? `${username} is typing...` : "";
  indicator.classList.toggle("d-none", !isTyping);
}

/** Clears the typing indicator. */
function hideTypingIndicator() {
  setTypingIndicator(false, "");
}

/** Returns the sidebar preview text: the message, or the file name for file messages. */
function messagePreview(msg) {
  return msg.message || (msg.messageType === "file" ? `File: ${msg.fileName}` : "");
}

/** Updates a chat's sidebar preview and time, moves it to the top, and bolds it if unread. */
function updateChatSidebar(msg) {
  const chatList = document.getElementById("chat-list");
  const chatEl = document.getElementById(`chat-${String(msg.chatId)}`);

  if (!chatList) {
    return;
  }
  if (!chatEl) {
    return;
  }

  const lastMessage = chatEl.querySelector(".last-msg");
  const lastTime = chatEl.querySelector(".last-time");
  if (lastMessage) {
    lastMessage.innerText = messagePreview(msg);
  }
  if (lastTime) {
    lastTime.innerText = formatChatTime(msg.timestamp);
  }
  if (
    String(msg.senderId) !== String(currentUserId) &&
    String(msg.chatId) !== String(currentChatId)
  ) {
    chatEl.classList.add("fw-bold");
    if (lastMessage) {
      lastMessage.classList.add("fw-bold");
    }
  }
  chatList.prepend(chatEl);
}

/** Formats a timestamp as a time for today, or a date otherwise. */
function formatChatTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const isCurrentYear = date.getFullYear() === now.getFullYear();

  return isToday
    ? date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(
        [],
        isCurrentYear
          ? { day: "numeric", month: "short" }
          : { day: "numeric", month: "short", year: "numeric" },
      );
}

document.querySelectorAll(".last-time[data-timestamp]").forEach((lastTime) => {
  lastTime.innerText = formatChatTime(lastTime.dataset.timestamp);
});

/** Saves the read state on the server and removes the unread styling from the sidebar. */
function markChatRead(chatId) {
  const chatEl = document.getElementById(`chat-${String(chatId)}`);
  if (!chatEl) {
    return;
  }

  fetch(`/api/messaging/mychats/chat/${encodeURIComponent(String(chatId))}/read`, {
    method: "POST",
  }).catch((error) => console.error("Unable to save read state:", error));

  chatEl.classList.remove("fw-bold");
  const lastMessage = chatEl.querySelector(".last-msg");
  if (lastMessage) {
    lastMessage.classList.remove("fw-bold");
  }
}

/** Renders one message bubble (text and/or file link) at the bottom of the conversation. */
function createChatItem(message, displayName) {
  const mine = String(message.senderId) === String(currentUserId);
  const item = document.createElement("li");
  const bubble = document.createElement("div");

  item.className =
    "d-flex mb-3 " + (mine ? "justify-content-end" : "justify-content-start");
  bubble.className =
    "p-3 rounded shadow-sm " + (mine ? "bg-primary text-white" : "bg-white border");

  const senderLabel = document.createElement("p");
  senderLabel.className = "fw-bold small mb-1";
  senderLabel.innerText = mine ? "You" : displayName;

  bubble.appendChild(senderLabel);

  if (message.messageType === "file") {
    const fileLink = document.createElement("a");
    fileLink.className = "d-block mb-1 " + (mine ? "link-light" : "");
    fileLink.href = `/api/messaging/mychats/chat/${encodeURIComponent(String(message.chatId))}/files/${encodeURIComponent(String(message.messageId))}`;
    fileLink.download = message.fileName;
    fileLink.innerText = `File: ${message.fileName}`;
    bubble.appendChild(fileLink);
  }

  if (message.message || message.messageType !== "file") {
    const text = document.createElement("p");
    text.className = "mb-0";
    text.innerText = message.message;
    bubble.appendChild(text);
  }

  const metadata = document.createElement("small");
  metadata.className = "d-block mt-2 small opacity-75";
  metadata.innerText = formatChatTime(message.timestamp);

  bubble.appendChild(metadata);
  item.appendChild(bubble);
  document.getElementById("conversation-messages").appendChild(item);

  const area = document.getElementById("conversation-area");
  area.scrollTop = area.scrollHeight;
}

/** Shows the message composer and hides the "no chat selected" hint. */
function showMessageBox() {
  document.getElementById("message-box").classList.remove("d-none");
  document.getElementById("no-chat-message").classList.add("d-none");
}

/**
 * Opens a conversation: joins its socket room, saves the current draft,
 * and loads its messages. refresh=true reloads without clearing the screen.
 */
function getMessages(displayName, chatId, refresh = false) {
  if (!refresh) chatLayout.classList.add('conversation-open');
  sizeConversation();
  if (currentChatId) {
    stopTyping();
    socketio.emit("leave_chat", {
      chatId: currentChatId,
      userId: currentUserId,
    });
  }
  if (String(currentChatId) !== String(chatId)) {
    const input = document.getElementById('message-input');
    if (currentChatId !== null) chatDrafts.set(String(currentChatId), input.value);
    input.value = chatDrafts.get(String(chatId)) || '';
  }
  currentChatId = chatId;
  hideTypingIndicator();
  showMessageBox();
  document.getElementById('chat-header').innerText = displayName;
  if (!refresh) document.getElementById('conversation-messages').replaceChildren();

  socketio.emit("join_chat", { chatId: chatId, userId: currentUserId });
  fetch("/api/messaging/mychats/chat/" + encodeURIComponent(String(chatId)), {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Unable to load chat (${response.status})`);
      }
      return response.json();
    })
    .then((data) => {
      if (String(currentChatId) !== String(chatId)) return;
      if (isConversationVisible()) markChatRead(chatId);
      document.getElementById("chat-header").innerText = displayName;
      const messageBox = document.getElementById("conversation-messages");
      messageBox.innerHTML = "";
      data.forEach((message) => {
        createChatItem(message, displayName);
      });
    })
    .catch(() => {
      if (String(currentChatId) === String(chatId)) showChatStatus('Could not load this conversation. Select it again to retry.');
    });
}

/** Sends the message text to the open chat over the socket and clears it once the server acknowledges. */
function sendMessage() {
  const msgInput = document.getElementById("message-input");
  if (currentChatId === null || msgInput.value.trim() === "" || sending || !socketio.connected || !navigator.onLine) return;
  const msg = msgInput.value;
  const sendingChatId = currentChatId;
  sending = true;
  updateConnection();
  stopTyping();
  socketio.timeout(10000).emit("message", {
    message: msg,
    chatId: currentChatId,
    senderId: currentUserId,
    timestamp: new Date().toISOString(),
  }, (error, result) => {
    sending = false;
    updateConnection();
    if (error || !result?.ok) {
      showChatStatus('Delivery could not be confirmed. Check the conversation before trying again.');
      return;
    }
    if (String(currentChatId) === String(sendingChatId) && msgInput.value === msg) msgInput.value = "";
    if (chatDrafts.get(String(sendingChatId)) === msg) chatDrafts.delete(String(sendingChatId));
  });
}

/** Tells the other member typing has stopped and cancels the pending stop timer. */
function stopTyping() {
  if (isTyping && currentChatId !== null && socketio.connected) {
    socketio.emit("typing", { chatId: currentChatId, isTyping: false });
  }
  isTyping = false;
  if (typingTimeout) {
    clearTimeout(typingTimeout);
    typingTimeout = null;
  }
}

// One listener on the list handles every chat button
document.getElementById("chat-list").addEventListener("click", function (event) {
  const chatItem = event.target.closest(".chat-item");
  if (!chatItem) return;
  getMessages(chatItem.dataset.displayName, chatItem.dataset.chatId);
});

document.getElementById("send-btn").addEventListener("click", sendMessage);

messageInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter") {
    event.preventDefault();
    sendMessage();
  }
});

messageInput.addEventListener("input", function (event) {
  if (currentChatId === null || !socketio.connected || !navigator.onLine) {
    return;
  }

  if (event.target.value.trim() && !isTyping) {
    socketio.emit("typing", { chatId: currentChatId, isTyping: true });
    isTyping = true;
  } else if (!event.target.value.trim()) {
    stopTyping();
    return;
  }

  if (typingTimeout) {
    clearTimeout(typingTimeout);
  }
  typingTimeout = setTimeout(stopTyping, 1000);
});

messageInput.addEventListener("blur", stopTyping);

// Auto-open the chat passed in by the server (e.g. a newly created chat)
const openId = appEl && appEl.dataset.openChatId;
if (openId) {
  const btn = document.getElementById(`chat-${openId}`);
  if (btn) getMessages(btn.dataset.displayName, openId);
}

/** Uploads the first selected file to the open chat, using the composer text as its caption. */
async function uploadFile(files) {
  const input = document.getElementById("file-upload");
  const file = files[0];
  input.value = "";
  if (!file) return;
  if (currentChatId === null) {
    showChatStatus("Open a conversation before uploading a file.");
    return;
  }
  if (sending) {
    showChatStatus("Wait for the current message to finish sending, then upload again.");
    return;
  }
  if (!socketio.connected || !navigator.onLine) {
    showChatStatus("You are offline. Reconnect before uploading a file.");
    return;
  }

  const msgInput = document.getElementById("message-input");
  const caption = msgInput.value.trim();
  const uploadChatId = currentChatId;
  const body = new FormData();
  body.append("file", file);
  if (caption) body.append("message", caption);

  sending = true;
  updateConnection();
  let errorText = "";
  try {
    const response = await fetch(`/api/messaging/mychats/chat/${encodeURIComponent(String(uploadChatId))}/files`, {
      method: "POST",
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Upload failed (${response.status})`);
    if (String(currentChatId) === String(uploadChatId) && msgInput.value.trim() === caption) msgInput.value = "";
  } catch (error) {
    errorText = error.message || "The file could not be uploaded. Try again.";
  } finally {
    sending = false;
    input.value = "";
    updateConnection();
  }
  if (errorText) showChatStatus(errorText);
}

document.getElementById("file-upload").addEventListener("change", (event) => uploadFile(event.target.files));

