const tg = window.Telegram?.WebApp;

const state = {
  page: "login",
  mode: "ai",
  user: null,
  activeTicketId: sessionStorage.getItem("kdbl-active-ticket-id") || "",
  seenMessageIds: new Set(),
  aiHistory: [],
  pollTimer: null,
  adminPollTimer: null,
  adminTickets: [],
  selectedAdminTicketId: "",
  profile: JSON.parse(localStorage.getItem("kdbl-profile") || "{}"),
};

const $ = (selector) => document.querySelector(selector);
const pages = {
  login: $("#loginPage"),
  main: $("#mainPage"),
  work: $("#workPage"),
  admin: $("#adminPage"),
};

const elements = {
  sessionLabel: $("#sessionLabel"),
  telegramLoginBox: $("#telegramLoginBox"),
  loginHint: $("#loginHint"),
  homeWorkButton: $("#homeWorkButton"),
  homeAdminButton: $("#homeAdminButton"),
  firstName: $("#firstName"),
  lastName: $("#lastName"),
  department: $("#department"),
  question: $("#question"),
  questionLabel: $("#questionLabel"),
  ticketFields: $("#ticketFields"),
  category: $("#category"),
  priority: $("#priority"),
  submitButton: $("#submitButton"),
  chatTitle: $("#chatTitle"),
  chatMessages: $("#chatMessages"),
  clearChatButton: $("#clearChatButton"),
  toast: $("#toast"),
  adminLogin: $("#adminLogin"),
  adminPanel: $("#adminPanel"),
  adminLoginInput: $("#adminLoginInput"),
  adminPasswordInput: $("#adminPasswordInput"),
  adminLoginButton: $("#adminLoginButton"),
  adminTotal: $("#adminTotal"),
  adminOpen: $("#adminOpen"),
  adminClosed: $("#adminClosed"),
  adminUsers: $("#adminUsers"),
  adminStats: $("#adminStats"),
  adminTickets: $("#adminTickets"),
  adminTicketStatus: $("#adminTicketStatus"),
  adminTicketDepartment: $("#adminTicketDepartment"),
  selectedTicketInfo: $("#selectedTicketInfo"),
  adminTicketMessages: $("#adminTicketMessages"),
  adminRouteDepartment: $("#adminRouteDepartment"),
  adminRouteButton: $("#adminRouteButton"),
  adminCloseTicketButton: $("#adminCloseTicketButton"),
  adminReplyText: $("#adminReplyText"),
  adminSendReplyButton: $("#adminSendReplyButton"),
};

window.onTelegramAuth = async (user) => {
  const response = await api("/api/auth/telegram", {
    method: "POST",
    body: JSON.stringify(user),
  });
  if (!response.ok) {
    showToast("Telegram login не прошел проверку.");
    return;
  }
  await loadSession();
  setPage("main");
};

init();

async function init() {
  tg?.ready();
  tg?.expand();
  bindEvents();
  hydrateProfile();
  await loadSession();
  await renderTelegramLogin();
  setPage(state.user ? (location.hash.replace("#", "") || "main") : "login");
  if (state.activeTicketId) {
    startTicketPolling();
  }
}

function bindEvents() {
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => setPage(button.dataset.page));
  });
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      renderMode();
    });
  });
  elements.homeWorkButton.addEventListener("click", () => setPage("work"));
  elements.homeAdminButton.addEventListener("click", () => setPage("admin"));
  [elements.firstName, elements.lastName, elements.department].forEach((input) => {
    input.addEventListener("input", saveProfile);
  });
  elements.submitButton.addEventListener("click", submitWork);
  elements.clearChatButton.addEventListener("click", resetChat);
  elements.adminLoginButton.addEventListener("click", adminLogin);
  $("#refreshAdminButton").addEventListener("click", loadAdmin);
  elements.adminTicketStatus.addEventListener("change", renderAdminTickets);
  elements.adminTicketDepartment.addEventListener("change", renderAdminTickets);
  elements.adminRouteButton.addEventListener("click", routeSelectedTicket);
  elements.adminCloseTicketButton.addEventListener("click", closeSelectedTicket);
  elements.adminSendReplyButton.addEventListener("click", sendAdminReply);
  document.addEventListener("keydown", handleHotkeys);
}

async function loadSession() {
  const params = new URLSearchParams();
  if (tg?.initData) {
    params.set("initData", tg.initData);
  }
  const response = await fetch(`/api/auth/session?${params}`, { credentials: "include" });
  if (!response.ok) {
    state.user = null;
    elements.sessionLabel.textContent = "Требуется Telegram-вход";
    return;
  }
  const data = await response.json();
  state.user = data.user;
  const name = [data.user?.firstName, data.user?.lastName].filter(Boolean).join(" ") || data.user?.username || data.user?.id;
  elements.sessionLabel.textContent = `Вход: ${name}`;
}

async function renderTelegramLogin() {
  if (tg?.initData && state.user) {
    elements.loginHint.textContent = "Вход через TMA initData выполнен.";
    return;
  }
  const config = await fetch("/api/config").then((r) => r.json()).catch(() => ({}));
  if (!config.telegramBotUsername) {
    elements.telegramLoginBox.textContent = "Для входа через браузер заполните TELEGRAM_BOT_USERNAME и настройте домен в @BotFather.";
    return;
  }
  elements.telegramLoginBox.replaceChildren();
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://telegram.org/js/telegram-widget.js?22";
  script.setAttribute("data-telegram-login", config.telegramBotUsername);
  script.setAttribute("data-size", "large");
  script.setAttribute("data-userpic", "false");
  script.setAttribute("data-request-access", "write");
  script.setAttribute("data-onauth", "onTelegramAuth(user)");
  elements.telegramLoginBox.append(script);
}

function setPage(page) {
  if (page !== "admin" && !state.user) {
    page = "login";
  }
  if (!pages[page]) {
    page = state.user ? "main" : "login";
  }
  state.page = page;
  location.hash = page;
  Object.entries(pages).forEach(([key, node]) => {
    node.hidden = key !== page;
  });
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.page === page);
  });
  if (page === "admin") {
    loadAdmin();
  } else {
    stopAdminPolling();
  }
  renderMode();
}

function renderMode() {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mode === state.mode);
  });
  const isTicket = state.mode === "ticket";
  elements.ticketFields.hidden = !isTicket;
  elements.questionLabel.textContent = isTicket ? "Опишите проблему для оператора" : "Что спросить у AI?";
  elements.submitButton.textContent = isTicket
    ? (state.activeTicketId ? `Ответить в тикет #${state.activeTicketId}` : "Создать тикет")
    : "Отправить AI";
  elements.chatTitle.textContent = state.activeTicketId ? `Тикет #${state.activeTicketId}` : "Диалог";
}

function hydrateProfile() {
  elements.firstName.value = state.profile.firstName || "";
  elements.lastName.value = state.profile.lastName || "";
  elements.department.value = state.profile.department || "";
  if (!elements.chatMessages.children.length) {
    addMessage("assistant", "Задайте вопрос AI или создайте тикет оператору.");
  }
}

function saveProfile() {
  state.profile = {
    firstName: elements.firstName.value.trim(),
    lastName: elements.lastName.value.trim(),
    department: elements.department.value.trim(),
  };
  localStorage.setItem("kdbl-profile", JSON.stringify(state.profile));
}

async function submitWork() {
  const text = elements.question.value.trim();
  if (!text) {
    showToast("Сначала напишите текст.");
    return;
  }
  addMessage("user", text);
  elements.submitButton.disabled = true;
  try {
    if (state.mode === "ticket") {
      if (state.activeTicketId) {
        const ok = await sendTicketMessage(text);
        if (ok) elements.question.value = "";
        return;
      }
      const ticketId = await createTicket(text);
      if (ticketId) {
        elements.question.value = "";
        state.activeTicketId = String(ticketId);
        sessionStorage.setItem("kdbl-active-ticket-id", state.activeTicketId);
        state.seenMessageIds = new Set();
        startTicketPolling();
      }
      return;
    }
    const answer = await askAi(text);
    if (answer) {
      elements.question.value = "";
      addMessage("assistant", answer);
      state.aiHistory.push({ role: "user", content: text }, { role: "assistant", content: answer });
      state.aiHistory = state.aiHistory.slice(-8);
    }
  } finally {
    elements.submitButton.disabled = false;
    renderMode();
  }
}

async function askAi(question) {
  const response = await api("/api/ai", {
    method: "POST",
    body: JSON.stringify({
      question,
      history: state.aiHistory,
      language: "ru",
      initData: tg?.initData || "",
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "AI не ответил.");
    return "";
  }
  return data.answer || "";
}

async function createTicket(question) {
  const response = await api("/api/tickets", {
    method: "POST",
    body: JSON.stringify({
      question,
      category: elements.category.value,
      priority: elements.priority.value,
      profile: state.profile,
      initData: tg?.initData || "",
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "Не удалось создать тикет.");
    return "";
  }
  addMessage("assistant", `Тикет #${data.ticketId} создан. Отдел: ${data.routing?.department || "operator"}.`);
  return data.ticketId;
}

async function sendTicketMessage(text) {
  const response = await api(`/api/tickets/${state.activeTicketId}/user-messages`, {
    method: "POST",
    body: JSON.stringify({
      text,
      profile: state.profile,
      initData: tg?.initData || "",
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "Не удалось отправить сообщение.");
    return false;
  }
  renderTicketMessages(data.messages || []);
  return true;
}

function startTicketPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
  }
  pollTicket();
  state.pollTimer = window.setInterval(pollTicket, 5000);
}

async function pollTicket() {
  if (!state.activeTicketId) return;
  const params = new URLSearchParams();
  if (tg?.initData) {
    params.set("initData", tg.initData);
  }
  const response = await api(`/api/tickets/${state.activeTicketId}/messages?${params}`);
  if (!response.ok) return;
  const data = await response.json();
  renderTicketMessages(data.messages || []);
  if (data.ticket?.status === "closed") {
    showToast(`Тикет #${state.activeTicketId} закрыт.`);
    clearActiveTicket();
  }
  renderMode();
}

function renderTicketMessages(messages) {
  elements.chatMessages.replaceChildren();
  messages.forEach((message) => {
    addMessage(message.role === "operator" ? "operator" : "user", `${message.senderName || message.role}: ${message.text}`);
    state.seenMessageIds.add(message.id);
  });
}

async function adminLogin() {
  const response = await api("/api/admin/login", {
    method: "POST",
    body: JSON.stringify({
      username: elements.adminLoginInput.value.trim(),
      password: elements.adminPasswordInput.value,
    }),
  });
  if (!response.ok) {
    showToast("Неверный логин или пароль админа.");
    return;
  }
  elements.adminPasswordInput.value = "";
  await loadAdmin();
}

async function loadAdmin() {
  const [summary, users, tickets] = await Promise.all([
    api("/api/admin/summary"),
    api("/api/admin/users"),
    api("/api/admin/tickets"),
  ]);
  const ok = summary.ok && users.ok && tickets.ok;
  elements.adminLogin.hidden = ok;
  elements.adminPanel.hidden = !ok;
  if (!ok) {
    stopAdminPolling();
    return;
  }
  const summaryData = await summary.json();
  renderSummary(summaryData);
  renderUsers((await users.json()).users || []);
  state.adminTickets = (await tickets.json()).tickets || [];
  renderAdminTickets();
  startAdminPolling();
}

function renderSummary(data) {
  elements.adminTotal.textContent = data.totals?.total ?? 0;
  elements.adminOpen.textContent = data.totals?.open ?? 0;
  elements.adminClosed.textContent = data.totals?.closed ?? 0;
  const rows = [
    ...(data.byDepartment || []).map((row) => [`Отдел ${row.department}`, `всего ${row.total}, закрыто ${row.closed || 0}`]),
    ...(data.byOperator || []).map((row) => [`Оператор ${row.operatorName}`, `закрыто ${row.closed}`]),
    ...(data.byUser || []).slice(0, 10).map((row) => [`Пользователь ${row.userName}`, `всего ${row.total}, закрыто ${row.closed || 0}`]),
  ];
  renderList(elements.adminStats, rows);
}

function renderUsers(users) {
  elements.adminUsers.replaceChildren(...users.map((user) => {
    const row = document.createElement("article");
    row.className = "list-row editable";
    const title = document.createElement("div");
    title.innerHTML = `<strong>${escapeHtml([user.firstName, user.lastName].filter(Boolean).join(" ") || user.username || user.telegramUserId)}</strong><span>@${escapeHtml(user.username || "-")} · ${escapeHtml(user.profileDepartment || "-")}</span>`;
    const department = select(["operator", "developer", "documents", "bot_admin", "unknown"], user.supportDepartment);
    const level = select(["user", "support", "lead", "admin"], user.accessLevel);
    const active = document.createElement("input");
    active.type = "checkbox";
    active.checked = Boolean(user.isActive);
    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "Сохранить";
    save.addEventListener("click", async () => {
      const response = await api(`/api/admin/users/${encodeURIComponent(user.telegramUserId)}`, {
        method: "PUT",
        body: JSON.stringify({
          supportDepartment: department.value,
          accessLevel: level.value,
          isActive: active.checked,
        }),
      });
      showToast(response.ok ? "Пользователь обновлен." : "Не удалось обновить пользователя.");
    });
    row.append(title, department, level, active, save);
    return row;
  }));
}

function renderAdminTickets() {
  const status = elements.adminTicketStatus.value;
  const department = elements.adminTicketDepartment.value;
  const tickets = state.adminTickets.filter((ticket) => {
    const statusOk = status === "all"
      || (status === "active" && ticket.status !== "closed")
      || ticket.status === status;
    const departmentOk = department === "all" || ticket.department === department;
    return statusOk && departmentOk;
  });
  elements.adminTickets.replaceChildren(...tickets.map((ticket) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "ticket-row";
    row.classList.toggle("is-active", String(ticket.id) === String(state.selectedAdminTicketId));
    row.innerHTML = `
      <strong>#${escapeHtml(ticket.id)} ${escapeHtml(ticket.userName || ticket.username || "Пользователь")}</strong>
      <span>${escapeHtml(ticket.status)} · ${escapeHtml(ticket.department || "unknown")} · ${escapeHtml(ticket.priority || "-")}</span>
    `;
    row.addEventListener("click", () => selectAdminTicket(ticket.id));
    return row;
  }));
  if (!tickets.length) {
    elements.adminTickets.innerHTML = `<article class="list-row"><strong>Нет тикетов</strong><span>По выбранному фильтру ничего нет.</span></article>`;
  }
}

async function selectAdminTicket(ticketId) {
  state.selectedAdminTicketId = String(ticketId);
  renderAdminTickets();
  await loadAdminTicketMessages();
}

async function loadAdminTicketMessages() {
  if (!state.selectedAdminTicketId) return;
  const response = await api(`/api/admin/tickets/${state.selectedAdminTicketId}/messages`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "Не удалось открыть тикет.");
    return;
  }
  renderSelectedTicket(data.ticket, data.messages || []);
}

function renderSelectedTicket(ticket, messages) {
  elements.selectedTicketInfo.innerHTML = `
    <strong>#${escapeHtml(ticket.id)} ${escapeHtml(ticket.userName || ticket.username || "Пользователь")}</strong>
    <span>${escapeHtml(ticket.status)} · ${escapeHtml(ticket.department)} · ${escapeHtml(ticket.category || "-")} · ${escapeHtml(ticket.priority || "-")}</span>
  `;
  elements.adminRouteDepartment.value = ticket.department || "operator";
  elements.adminTicketMessages.replaceChildren();
  messages.forEach((message) => {
    const item = document.createElement("article");
    item.className = `message ${message.role === "operator" ? "operator" : "user"}`;
    const body = document.createElement("span");
    body.textContent = `${message.senderName || message.role}: ${message.text}`;
    item.append(body);
    elements.adminTicketMessages.append(item);
  });
  elements.adminTicketMessages.scrollTop = elements.adminTicketMessages.scrollHeight;
}

async function sendAdminReply() {
  if (!state.selectedAdminTicketId) {
    showToast("Сначала выберите тикет.");
    return;
  }
  const text = elements.adminReplyText.value.trim();
  if (!text) {
    showToast("Напишите ответ.");
    return;
  }
  const response = await api(`/api/admin/tickets/${state.selectedAdminTicketId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text, operatorName: elements.adminLoginInput.value.trim() || "Admin" }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "Ответ не отправился.");
    return;
  }
  elements.adminReplyText.value = "";
  renderSelectedTicket(data.ticket, data.messages || []);
  await loadAdmin();
}

async function closeSelectedTicket() {
  if (!state.selectedAdminTicketId) {
    showToast("Сначала выберите тикет.");
    return;
  }
  const response = await api(`/api/admin/tickets/${state.selectedAdminTicketId}/status`, {
    method: "POST",
    body: JSON.stringify({ status: "closed", operatorName: elements.adminLoginInput.value.trim() || "Admin" }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "Не удалось закрыть тикет.");
    return;
  }
  renderSelectedTicket(data.ticket, data.messages || []);
  await loadAdmin();
}

async function routeSelectedTicket() {
  if (!state.selectedAdminTicketId) {
    showToast("Сначала выберите тикет.");
    return;
  }
  const response = await api(`/api/admin/tickets/${state.selectedAdminTicketId}/route`, {
    method: "POST",
    body: JSON.stringify({
      department: elements.adminRouteDepartment.value,
      operatorName: elements.adminLoginInput.value.trim() || "Admin",
      reason: "Route changed from Mini App admin panel.",
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(data.error || "Не удалось сменить отдел.");
    return;
  }
  renderSelectedTicket(data.ticket, data.messages || []);
  await loadAdmin();
}

function startAdminPolling() {
  if (state.adminPollTimer) return;
  state.adminPollTimer = window.setInterval(async () => {
    if (state.page !== "admin" || elements.adminPanel.hidden) return;
    const tickets = await api("/api/admin/tickets");
    if (tickets.ok) {
      state.adminTickets = (await tickets.json()).tickets || [];
      renderAdminTickets();
    }
    if (state.selectedAdminTicketId) {
      await loadAdminTicketMessages();
    }
  }, 6000);
}

function stopAdminPolling() {
  if (state.adminPollTimer) {
    window.clearInterval(state.adminPollTimer);
    state.adminPollTimer = null;
  }
}

function handleHotkeys(event) {
  if (state.page !== "admin" || elements.adminPanel.hidden) return;
  if (event.ctrlKey && event.key === "Enter") {
    event.preventDefault();
    sendAdminReply();
  }
  if (event.altKey && event.key.toLowerCase() === "c") {
    event.preventDefault();
    closeSelectedTicket();
  }
  const departmentByKey = {
    "1": "operator",
    "2": "developer",
    "3": "documents",
    "4": "bot_admin",
    "5": "unknown",
  };
  if (event.altKey && departmentByKey[event.key]) {
    event.preventDefault();
    elements.adminRouteDepartment.value = departmentByKey[event.key];
    routeSelectedTicket();
  }
}

function resetChat() {
  clearActiveTicket();
  state.aiHistory = [];
  state.seenMessageIds = new Set();
  elements.chatMessages.replaceChildren();
  addMessage("assistant", "Диалог очищен.");
}

function clearActiveTicket() {
  state.activeTicketId = "";
  sessionStorage.removeItem("kdbl-active-ticket-id");
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function addMessage(role, text) {
  const message = document.createElement("article");
  message.className = `message ${role}`;
  const body = document.createElement("span");
  body.textContent = text;
  message.append(body);
  elements.chatMessages.append(message);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function renderList(container, rows) {
  container.replaceChildren(...rows.map(([title, meta]) => {
    const row = document.createElement("article");
    row.className = "list-row";
    row.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(meta)}</span>`;
    return row;
  }));
}

function select(values, selected) {
  const node = document.createElement("select");
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === selected;
    node.append(option);
  });
  return node;
}

function api(url, options = {}) {
  return fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2600);
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}
