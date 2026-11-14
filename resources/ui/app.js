"use strict";
const $ = (s) => document.querySelector(s);
const state = {
  page: "start",
  kind: "local",
  file: "",
  records: [],
  selected: null,
  filter: "ALL",
  config: null,
  polling: false,
  detailSignature: "",
};
const labels = {
  PENDING: "等待中",
  RUNNING: "处理中",
  SUCCESS: "已完成",
  FAIL: "未完成",
  INTERRUPTED: "已中断",
};
const busy = (t) => ["PENDING", "RUNNING"].includes(t.status);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const title = (t) => t.source_title || `任务 ${t.task_id.slice(0, 8)}`;
const date = (s) => (s || "").replace("T", " ").slice(0, 16);
const badge = (t) =>
  `<span class="badge ${t.status === "SUCCESS" ? "success" : busy(t) ? "running" : "fail"}">${esc(labels[t.status] || t.status)}</span>`;
const stage = (t) =>
  `<span class="stage-line">${busy(t) ? '<i class="spinner" aria-hidden="true"></i>' : ""}${esc(t.stage || "")}</span>`;
async function call(name, ...args) {
  if (!window.pywebview?.api)
    throw new Error("当前为界面预览。请从桌面程序打开以使用本地功能。");
  const r = await window.pywebview.api[name](...args);
  if (!r.ok) throw new Error(r.error || "操作失败");
  return r.data;
}
let toastTimer;
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
async function perform(button, fn, errorTarget) {
  if (button?.disabled) return;
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  if (errorTarget) errorTarget.hidden = true;
  try {
    return await fn();
  } catch (e) {
    if (errorTarget) {
      errorTarget.textContent = e.message;
      errorTarget.hidden = false;
    } else toast(e.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
}
function showPage(page) {
  state.page = page;
  document
    .querySelectorAll(".page")
    .forEach((e) => (e.hidden = e.id !== `page-${page}`));
  document.querySelectorAll(".nav").forEach((b) => {
    const yes = b.dataset.page === page;
    b.classList.toggle("active", yes);
    if (yes) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  $("#breadcrumb").textContent = {
    start: "开始转写",
    history: "转写记录",
    settings: "设置",
  }[page];
  if (page === "history") renderHistory();
  window.scrollTo(0, 0);
}
function setKind(kind, focus = false) {
  state.kind = kind;
  ["local", "douyin"].forEach((k) => {
    const yes = k === kind;
    const tab = $(`#tab-${k}`);
    tab.classList.toggle("selected", yes);
    tab.setAttribute("aria-selected", String(yes));
    tab.tabIndex = yes ? 0 : -1;
    $(`#${k}-panel`).hidden = !yes;
  });
  if (focus) $(`#tab-${kind}`).focus();
}
function renderRecent() {
  const tasks = state.records.slice(0, 3);
  $("#recent-list").innerHTML = tasks.length
    ? tasks
        .map(
          (t) =>
            `<button class="recent-item" data-id="${esc(t.task_id)}"><span class="file-icon" aria-hidden="true">${t.source_type === "douyin" ? "↗" : "▤"}</span><span class="recent-copy"><strong>${esc(title(t))}</strong><small>${date(t.created_at)} · ${t.source_type === "douyin" ? "抖音链接" : "本地素材"}</small>${busy(t) ? stage(t) : ""}</span>${badge(t)}<span aria-hidden="true">↗</span></button>`,
        )
        .join("")
    : '<div class="empty-inline">暂无记录</div>';
}
function renderHistory() {
  $("#history-count").textContent = `${state.records.length} 条记录`;
  const query = $("#search").value.toLowerCase();
  const tasks = state.records.filter(
    (t) =>
      title(t).toLowerCase().includes(query) &&
      (state.filter === "ALL" ||
        (state.filter === "RUNNING"
          ? busy(t)
          : state.filter === "FAIL"
            ? ["FAIL", "INTERRUPTED"].includes(t.status)
            : t.status === state.filter)),
  );
  $("#record-list").innerHTML = tasks.length
    ? tasks
        .map(
          (t) =>
            `<button class="record-item ${t.task_id === state.selected ? "selected" : ""}" data-id="${esc(t.task_id)}" aria-pressed="${t.task_id === state.selected}"><span class="record-title">${esc(title(t))}</span><span class="record-meta"><span>${date(t.created_at)}</span>${badge(t)}</span>${stage(t)}</button>`,
        )
        .join("")
    : '<div class="empty-inline">暂无匹配记录</div>';
}
async function openDetail(id) {
  state.selected = id;
  state.detailSignature = "";
  showPage("history");
  await refreshDetail();
}
async function refreshDetail() {
  if (!state.selected) return;
  const id = state.selected;
  const task = state.records.find((t) => t.task_id === id);
  if (!task) {
    state.selected = null;
    $("#detail-panel").innerHTML =
      '<div class="empty-detail"><h2>记录已删除</h2><p>选择其他记录查看</p></div>';
    return;
  }
  const signature = JSON.stringify(task);
  if (signature === state.detailSignature) return;
  const t = await call("detail", id);
  if (state.selected !== id) return;
  state.detailSignature = signature;
  $("#detail-panel").innerHTML =
    `<h2 class="detail-heading">${esc(title(t))}</h2><div class="detail-meta">${date(t.created_at)} · ${t.source_type === "douyin" ? "抖音素材" : "本地素材"}${t.duration_seconds ? " · " + Math.ceil(t.duration_seconds) + " 秒" : ""}</div><div class="detail-status">${badge(t)}${stage(t)}${t.error_message ? `<p class="error">${esc(t.error_message)}</p>` : ""}</div><div class="transcript" tabindex="0" aria-label="完整文字稿">${t.raw_text ? esc(t.raw_text) : busy(t) ? "正在处理，请稍候。" : "暂无文字稿"}</div><div class="detail-tools"><button class="button primary" data-action="copy_text" ${!t.raw_text ? "disabled" : ""}>复制文字稿 ↗</button><button class="button" data-action="export_text" ${!t.raw_text ? "disabled" : ""}>导出 TXT</button>${["FAIL", "INTERRUPTED"].includes(t.status) ? '<button class="button" data-action="retry">重试</button>' : ""}</div><div class="detail-secondary"><button data-action="open_folder">打开素材目录 ↗</button><button data-action="delete_record" ${busy(t) ? "disabled" : ""}>删除记录</button>${t.source_type === "douyin" && t.downloaded_path ? `<button data-action="clean_download" ${busy(t) ? "disabled" : ""}>清理下载文件</button>` : ""}</div>`;
}
async function update() {
  if (state.polling || !window.pywebview?.api) return;
  state.polling = true;
  try {
    const tasks = await call("snapshot");
    const changed = JSON.stringify(tasks) !== JSON.stringify(state.records);
    state.records = tasks;
    if (changed) {
      renderRecent();
      renderHistory();
    }
    if (state.page === "history") await refreshDetail();
  } catch (e) {
    console.error("刷新暂时失败");
  } finally {
    state.polling = false;
  }
}
function fillConfig(config) {
  state.config = config;
  for (const [id, key] of [
    ["setting-url", "url"],
    ["setting-resource", "resource_id"],
    ["setting-model", "model_name"],
    ["setting-timeout", "timeout"],
    ["setting-output", "output_dir"],
    ["output", "output_dir"],
  ])
    $("#" + id).value = config[key];
  $("#setting-key").value = "";
  $("#setting-key").placeholder = config.has_key
    ? "已安全保存；留空保留原密钥"
    : "输入你的 API Key";
  $("#key-status").textContent = config.has_key ? "（已保存）" : "";
}
async function initialize() {
  try {
    const data = await call("bootstrap");
    fillConfig(data.config);
    $("#data-dir").textContent = data.data_dir;
    if (data.warning) toast(data.warning);
    await update();
  } catch (e) {
    toast(e.message);
  }
}
function confirmAction(action) {
  return new Promise((resolve) => {
    const dialog = $("#confirm-dialog");
    $("#dialog-title").textContent =
      action === "delete_record" ? "删除这条记录？" : "清理这份下载文件？";
    $("#dialog-message").textContent =
      action === "delete_record"
        ? "只删除处理记录。原始素材和应用下载文件都会保留。"
        : "只删除这条任务的应用下载视频。文字稿和历史记录继续保留。";
    $("#dialog-confirm").textContent =
      action === "delete_record" ? "删除记录" : "清理文件";
    dialog.returnValue = "";
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "confirm"),
      { once: true },
    );
    dialog.showModal();
    dialog.querySelector('[value="cancel"]').focus();
  });
}
document
  .querySelectorAll(".nav")
  .forEach((b) => (b.onclick = () => showPage(b.dataset.page)));
$("#all-history").onclick = () => showPage("history");
$(".brand").onclick = (e) => {
  e.preventDefault();
  showPage("start");
};
for (const kind of ["local", "douyin"]) {
  $(`#tab-${kind}`).onclick = () => setKind(kind);
  $(`#tab-${kind}`).onkeydown = (e) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      setKind(
        e.key === "Home"
          ? "local"
          : e.key === "End"
            ? "douyin"
            : state.kind === "local"
              ? "douyin"
              : "local",
        true,
      );
    }
  };
}
$("#choose-file").onclick = (e) =>
  perform(e.currentTarget, async () => {
    const path = await call("choose_file");
    if (path) {
      state.file = path;
      $("#file-name").textContent = path.split(/[\\/]/).pop();
      $("#file-hint").textContent = path;
      $(".upload-pick").textContent = "↻ 换一个文件";
    }
  });
async function chooseOutput(button) {
  await perform(button, async () => {
    const path = await call("choose_directory");
    if (path) {
      $("#output").value = path;
      $("#setting-output").value = path;
    }
  });
}
$("#choose-output").onclick = (e) => chooseOutput(e.currentTarget);
$("#setting-folder").onclick = (e) => chooseOutput(e.currentTarget);
$("#output").onchange = () => ($("#setting-output").value = $("#output").value);
$("#setting-output").onchange = () =>
  ($("#output").value = $("#setting-output").value);
$("#start-task").onclick = (e) =>
  perform(
    e.currentTarget,
    async () => {
      const id = await call(
        "start_task",
        state.kind,
        state.kind === "local" ? state.file : $("#share").value,
        $("#output").value,
      );
      toast("任务已加入队列");
      await update();
      await openDetail(id);
    },
    $("#start-error"),
  );
$("#search").oninput = renderHistory;
document.querySelectorAll("[data-filter]").forEach(
  (b) =>
    (b.onclick = () => {
      state.filter = b.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((x) => {
        const yes = x === b;
        x.classList.toggle("selected", yes);
        x.setAttribute("aria-pressed", String(yes));
      });
      renderHistory();
    }),
);
for (const selector of ["#recent-list", "#record-list"])
  $(selector).onclick = (e) => {
    const b = e.target.closest("[data-id]");
    if (b) perform(null, () => openDetail(b.dataset.id));
  };
$("#detail-panel").onclick = (e) => {
  const b = e.target.closest("[data-action]");
  if (!b || b.disabled) return;
  perform(b, async () => {
    const action = b.dataset.action;
    const id = state.selected;
    if (
      ["delete_record", "clean_download"].includes(action) &&
      !(await confirmAction(action))
    )
      return;
    const result = await call(action, id);
    if (action === "copy_text") toast("文字稿已复制。");
    else if (action === "export_text") {
      if (result) toast("TXT 已导出。");
    } else if (action !== "open_folder") {
      toast(action === "retry" ? "已重新加入队列。" : "已完成。");
      state.detailSignature = "";
      await update();
    }
  });
};
$("#toggle-key").onclick = () => {
  const input = $("#setting-key");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  $("#toggle-key").textContent = show ? "隐藏" : "显示";
  $("#toggle-key").setAttribute("aria-pressed", String(show));
};
$("#settings-form").onsubmit = (e) => {
  e.preventDefault();
  perform(
    $('#settings-form button[type="submit"]'),
    async () => {
      const config = await call("save_settings", {
        url: $("#setting-url").value,
        api_key: $("#setting-key").value,
        resource_id: $("#setting-resource").value,
        model_name: $("#setting-model").value,
        timeout: $("#setting-timeout").value,
        output_dir: $("#setting-output").value,
      });
      fillConfig(config);
      toast("配置已保存");
    },
    $("#settings-error"),
  );
};
window.addEventListener("pywebviewready", initialize);
setInterval(update, 1200);
if (!window.pywebview) $("#data-dir").textContent = "请从桌面程序打开";
