const appEl = document.getElementById("chat-app");
const currentUserId = appEl ? appEl.dataset.userId : null;
let currentChatId = null;

const socketio = io({ auth: { userId: currentUserId } });

socketio.on("connect_error", function (error) {
  console.error("Messaging connection failed:", error.message);
});

socketio.on("message", function (msg) {
  updateChatSidebar(msg);
  if (String(msg.chatId) === String(currentChatId)) {
    hideTypingIndicator();
    markChatRead(msg.chatId);
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

function setTypingIndicator(isTyping, username) {
  const indicator = document.getElementById("typing-indicator");
  if (!indicator) {
    return;
  }
  indicator.innerText = isTyping ? `${username} is typing...` : "";
  indicator.classList.toggle("d-none", !isTyping);
}

function hideTypingIndicator() {
  setTypingIndicator(false, "");
}

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
    lastMessage.innerText = msg.message;
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

  const text = document.createElement("p");
  text.className = "mb-0";
  text.innerText = message.message;

  const metadata = document.createElement("small");
  metadata.className = "d-block mt-2 small opacity-75";
  metadata.innerText = formatChatTime(message.timestamp);

  bubble.appendChild(senderLabel);
  bubble.appendChild(text);
  bubble.appendChild(metadata);
  item.appendChild(bubble);
  document.getElementById("conversation-messages").appendChild(item);

  const area = document.getElementById("conversation-area");
  area.scrollTop = area.scrollHeight;
}

function showMessageBox() {
  document.getElementById("message-box").classList.remove("d-none");
  document.getElementById("no-chat-message").classList.add("d-none");
}

function getMessages(displayName, chatId) {
  if (currentChatId === chatId) {
    return;
  }
  if (currentChatId) {
    stopTyping();
    socketio.emit("leave_chat", {
      chatId: currentChatId,
      userId: currentUserId,
    });
  }
  currentChatId = chatId;
  hideTypingIndicator();
  markChatRead(chatId);
  showMessageBox();

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
      document.getElementById("chat-header").innerText = displayName;
      const messageBox = document.getElementById("conversation-messages");
      messageBox.innerHTML = "";
      data.forEach((message) => {
        createChatItem(message, displayName);
      });
    })
    .catch((error) => console.error("Chat message loading failed:", error));
}

function sendMessage() {
  const msgInput = document.getElementById("message-input");
  if (currentChatId === null || msgInput.value.trim() === "") return;
  const msg = msgInput.value;
  stopTyping();
  socketio.emit("message", {
    message: msg,
    chatId: currentChatId,
    senderId: currentUserId,
    timestamp: new Date().toISOString(),
  });
  msgInput.value = "";
}

let typingTimeout = null;
let isTyping = false;

function stopTyping() {
  if (isTyping && currentChatId !== null) {
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

const messageInput = document.getElementById("message-input");

messageInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter") {
    sendMessage();
  }
});

messageInput.addEventListener("input", function (event) {
  if (currentChatId === null) {
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