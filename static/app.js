document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("themeToggle");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const shell = document.querySelector(".app-shell");
  if (shell && localStorage.getItem("gatekeeper-sidebar") === "collapsed") {
    shell.classList.add("sidebar-collapsed");
  }
  if (sidebarToggle && shell) {
    sidebarToggle.addEventListener("click", () => {
      shell.classList.toggle("sidebar-collapsed");
      localStorage.setItem("gatekeeper-sidebar", shell.classList.contains("sidebar-collapsed") ? "collapsed" : "open");
    });
  }
  if (toggle) {
    toggle.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("gatekeeper-theme", next);
    });
  }

  const bannerSelect = document.getElementById("bannerSelect");
  const bannerPreview = document.getElementById("bannerImagePreview");
  const bannerEmpty = document.getElementById("bannerImageEmpty");
  if (bannerSelect) {
    const updateBannerPreview = () => {
      const option = bannerSelect.selectedOptions[0];
      const url = option ? option.dataset.preview : "";
      if (!url) {
        if (bannerPreview) bannerPreview.hidden = true;
        if (bannerEmpty) bannerEmpty.hidden = false;
        return;
      }
      let image = bannerPreview;
      if (!image) {
        image = document.createElement("img");
        image.id = "bannerImagePreview";
        image.alt = "Selected banner preview";
        bannerSelect.closest("form").querySelector(".banner-picker-preview").prepend(image);
      }
      image.src = url;
      image.hidden = false;
      if (bannerEmpty) bannerEmpty.hidden = true;
    };
    bannerSelect.addEventListener("change", updateBannerPreview);
    updateBannerPreview();
  }

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.tab;
      document.querySelectorAll(".tab-button").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${tab}`));
      localStorage.setItem("gatekeeper-server-tab", tab);
    });
  });

  const savedTab = localStorage.getItem("gatekeeper-server-tab");
  if (savedTab) {
    const button = document.querySelector(`.tab-button[data-tab="${savedTab}"]`);
    if (button) button.click();
  }
  if (!document.querySelector(".tab-button.active")) {
    const firstTab = document.querySelector(".tab-button");
    if (firstTab) firstTab.click();
  }

  const displayModeSelect = document.getElementById("displayModeSelect");
  const updateModePanels = () => {
    if (!displayModeSelect) return;
    const mode = displayModeSelect.value;
    document.querySelectorAll(".mode-panel").forEach((panel) => {
      panel.hidden = panel.dataset.displayMode !== mode;
    });
  };
  if (displayModeSelect) {
    displayModeSelect.addEventListener("change", updateModePanels);
    updateModePanels();
  }

  const embedColorMode = document.getElementById("embedColorMode");
  const updateEmbedColorFields = () => {
    if (!embedColorMode) return;
    const mode = embedColorMode.value;
    document.querySelectorAll(".embed-color-field").forEach((field) => {
      field.hidden = field.dataset.colorMode !== mode;
    });
  };
  if (embedColorMode) {
    embedColorMode.addEventListener("change", updateEmbedColorFields);
    updateEmbedColorFields();
  }

  document.querySelectorAll(".timezone-search").forEach((input) => {
    const label = input.closest("label");
    const select = label ? label.querySelector(".timezone-select") : null;
    if (!select) return;
    const current = select.dataset.current || select.value || "UTC";
    const timezoneOffsetLabel = (timezone) => {
      const date = new Date();
      const formatter = new Intl.DateTimeFormat("en-US", {
        timeZone: timezone,
        timeZoneName: "shortOffset",
        hour: "2-digit",
      });
      const zonePart = formatter.formatToParts(date).find((part) => part.type === "timeZoneName");
      const raw = zonePart ? zonePart.value.replace("GMT", "UTC") : "UTC+00:00";
      if (raw === "UTC") return "UTC+00:00";
      const match = raw.match(/UTC([+-])(\d{1,2})(?::?(\d{2}))?/);
      if (!match) return "UTC+00:00";
      return `UTC${match[1]}${match[2].padStart(2, "0")}:${match[3] || "00"}`;
    };
    const timezoneOffsetMinutes = (timezone) => {
      const label = timezoneOffsetLabel(timezone);
      const match = label.match(/UTC([+-])(\d{2}):?(\d{2})?/);
      if (!match) return 0;
      const sign = match[1] === "-" ? -1 : 1;
      return sign * ((Number(match[2]) * 60) + Number(match[3] || 0));
    };
    if (Intl.supportedValuesOf) {
      const existing = new Set(Array.from(select.options).map((option) => option.value));
      Intl.supportedValuesOf("timeZone").forEach((timezone) => {
        if (existing.has(timezone)) return;
        const option = document.createElement("option");
        option.value = timezone;
        option.dataset.offset = String(timezoneOffsetMinutes(timezone));
        option.textContent = `${timezoneOffsetLabel(timezone)} - ${timezone}`;
        select.append(option);
        existing.add(timezone);
      });
      Array.from(select.options)
        .forEach((option) => {
          if (!option.dataset.offset) option.dataset.offset = String(timezoneOffsetMinutes(option.value));
          if (!option.textContent.includes(" - ")) option.textContent = `${timezoneOffsetLabel(option.value)} - ${option.value}`;
        });
      Array.from(select.options)
        .sort((a, b) => (Number(a.dataset.offset) - Number(b.dataset.offset)) || a.value.localeCompare(b.value))
        .forEach((option) => select.append(option));
      if (existing.has(current)) select.value = current;
    }
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      if (!query) return;
      const option = Array.from(select.options).find((item) =>
        item.value.toLowerCase().includes(query) || item.textContent.toLowerCase().includes(query)
      );
      if (option) {
        select.value = option.value;
        option.scrollIntoView({ block: "nearest" });
      }
    });
  });

  const recentChanges = document.getElementById("recentChanges");
  if (recentChanges && recentChanges.dataset.liveUrl) {
    const renderLogs = (logs) => {
      recentChanges.innerHTML = "";
      if (!logs.length) {
        const empty = document.createElement("p");
        empty.className = "muted";
        empty.textContent = "No changes logged yet.";
        recentChanges.append(empty);
        return;
      }
      logs.forEach((log) => {
        const row = document.createElement("div");
        const id = document.createElement("strong");
        const date = document.createElement("span");
        const code = document.createElement("code");
        id.textContent = `#${log.id}`;
        date.textContent = log.date;
        code.textContent = log.log;
        row.append(id, date, code);
        recentChanges.append(row);
      });
    };
    const refreshLogs = async () => {
      try {
        const response = await fetch(recentChanges.dataset.liveUrl, { headers: { "Accept": "application/json" } });
        if (response.ok) renderLogs(await response.json());
      } catch (_error) {
        // Keep the existing list if a poll misses.
      }
    };
    setInterval(refreshLogs, 5000);
  }

  const overviewServerList = document.getElementById("overviewServerList");
  if (overviewServerList && overviewServerList.dataset.liveUrl) {
    const statusLabels = {
      amp_connected: ["AMP connected", "AMP not connected"],
      container_online: ["Container online", "Container offline"],
      dedicated_online: ["Server online", "Server offline"],
    };
    const refreshServerDots = async () => {
      try {
        const response = await fetch(overviewServerList.dataset.liveUrl, { headers: { "Accept": "application/json" } });
        if (!response.ok) return;
        const statuses = await response.json();
        overviewServerList.querySelectorAll("[data-instance-id]").forEach((card) => {
          const status = statuses[card.dataset.instanceId] || {};
          card.querySelectorAll("[data-status-dot]").forEach((dot) => {
            const key = dot.dataset.statusDot;
            const on = Boolean(status[key]);
            const starting = key === "dedicated_online" && Boolean(status.dedicated_starting);
            dot.classList.toggle("on", on);
            dot.classList.toggle("warn", starting);
            dot.classList.toggle("off", !on && !starting);
            const wrapper = dot.closest("span");
            if (wrapper && statusLabels[key]) wrapper.title = starting ? "Server starting" : statusLabels[key][on ? 0 : 1];
          });
        });
      } catch (_error) {
        // Keep existing status dots if the poll fails.
      }
    };
    refreshServerDots();
    setInterval(refreshServerDots, 5000);
  }

  const serverStatusStack = document.getElementById("serverStatusStack");
  if (serverStatusStack && serverStatusStack.dataset.liveUrl) {
    const statusText = {
      amp_connected: ["Connected", "Disconnected"],
      container_online: ["Online", "Offline"],
      dedicated_online: ["Online", "Offline"],
    };
    const refreshServerStatus = async () => {
      try {
        const response = await fetch(serverStatusStack.dataset.liveUrl, { headers: { "Accept": "application/json" } });
        if (!response.ok) return;
        const statuses = await response.json();
        const status = statuses[serverStatusStack.dataset.instanceId] || {};
        serverStatusStack.querySelectorAll("[data-status-dot]").forEach((dot) => {
          const key = dot.dataset.statusDot;
          const on = Boolean(status[key]);
          const starting = key === "dedicated_online" && Boolean(status.dedicated_starting);
          dot.classList.toggle("on", on);
          dot.classList.toggle("warn", starting);
          dot.classList.toggle("off", !on && !starting);
        });
        serverStatusStack.querySelectorAll("[data-status-text]").forEach((text) => {
          const key = text.dataset.statusText;
          const on = Boolean(status[key]);
          if (key === "dedicated_online" && status.dedicated_starting) {
            text.textContent = "Starting";
          } else if (statusText[key]) {
            text.textContent = statusText[key][on ? 0 : 1];
          }
        });
      } catch (_error) {
        // Keep the last known status if a poll misses.
      }
    };
    refreshServerStatus();
    setInterval(refreshServerStatus, 5000);
  }

  document.querySelectorAll("form[data-autosave-url]").forEach((form) => {
    const state = form.querySelector("[data-autosave-state]");
    const timers = new Map();
    const setState = (text, className = "") => {
      if (!state) return;
      state.textContent = text;
      state.classList.remove("saving", "saved", "error");
      if (className) state.classList.add(className);
    };
    const fieldValue = (field) => {
      if (field.type === "checkbox") return field.checked ? "1" : "0";
      return field.value;
    };
    const saveField = async (field) => {
      if (!field.name || field.name === "form_scope") return;
      const url = field.dataset.autosaveUrl || form.dataset.autosaveUrl;
      setState("Saving...", "saving");
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ field: field.name, value: fieldValue(field) }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.ok === false) {
          throw new Error(result.error || "Save failed.");
        }
        setState("Saved", "saved");
        window.setTimeout(() => setState("Changes save automatically"), 1200);
      } catch (error) {
        setState(error.message || "Save failed", "error");
      }
    };
    const queueSave = (field) => {
      const immediate = ["checkbox", "select-one", "color", "number"].includes(field.type) || field.tagName === "SELECT";
      if (field.type === "checkbox") {
        const label = field.closest("label")?.querySelector("[data-switch-label]");
        if (label) label.textContent = field.checked ? label.dataset.on : label.dataset.off;
      }
      window.clearTimeout(timers.get(field));
      timers.set(field, window.setTimeout(() => saveField(field), immediate ? 0 : 500));
    };
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      setState("Settings already save automatically", "saved");
      window.setTimeout(() => setState("Changes save automatically"), 1200);
    });
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach((field) => {
      const eventName = field.type === "text" || field.type === "search" || field.tagName === "TEXTAREA" ? "input" : "change";
      field.addEventListener(eventName, () => queueSave(field));
      if (eventName !== "change") field.addEventListener("change", () => queueSave(field));
    });
  });

  const updateEmbedPreview = () => {
    const titleInput = document.querySelector('[data-preview-source="title"]');
    const hostInput = document.querySelector('[data-preview-source="host"]');
    const colorModeInput = document.querySelector('[name="Embed_Color_Mode"]');
    const colorInput = document.querySelector('[name="Embed_Color"]');
    const roleColorInput = document.querySelector('[name="Embed_Color_Role"]');
    const onlineColorInput = document.querySelector('[name="Embed_Color_Online"]');
    const startingColorInput = document.querySelector('[name="Embed_Color_Starting"]');
    const offlineColorInput = document.querySelector('[name="Embed_Color_Offline"]');
    const thumbSelect = document.querySelector('[data-preview-source="thumb"]');
    const imageSelect = document.querySelector('[data-preview-source="image"]');
    const timezoneSelect = document.querySelector('[data-preview-source="footer-timezone"]');
    const formatSelect = document.querySelector('[data-preview-source="footer-format"]');
    const hideDonator = document.querySelector('[name="Embed_Donator_Hidden"]');
    const hideWhitelist = document.querySelector('[name="Embed_Whitelist_Hidden"]');
    const whitelist = document.querySelector('[name="Whitelist"]');
    const donator = document.querySelector('[name="Donator"]');
    const displayName = titleInput && titleInput.value.trim() ? titleInput.value.trim() : null;

    document.querySelectorAll("[data-preview-title]").forEach((title) => {
      if (title.closest('[data-preview-kind="display"]')) {
        title.textContent = `======= ${displayName || title.textContent.replace(/^=======\s*|\s*=======$/g, "") || "Server"} =======`;
      } else {
        title.textContent = displayName || title.textContent || "Server";
      }
    });
    document.querySelectorAll('[data-preview-field="Host"]').forEach((field) => {
      field.textContent = hostInput && hostInput.value.trim() ? hostInput.value.trim() : "Not set";
    });
    document.querySelectorAll('[data-preview-field="Donator Only"]').forEach((field) => {
      const wrapper = field.closest(".embed-field");
      if (wrapper) wrapper.hidden = Boolean(hideDonator && hideDonator.checked);
      field.textContent = donator && donator.checked ? "✅ On" : "❌ Off";
    });
    document.querySelectorAll('[data-preview-field="Whitelist Requests"]').forEach((field) => {
      const wrapper = field.closest(".embed-field");
      if (wrapper) wrapper.hidden = Boolean(hideWhitelist && hideWhitelist.checked);
      field.textContent = whitelist && whitelist.checked ? "✅ On" : "❌ Off";
    });
    const statusText = document.querySelector('[data-preview-field="Dedicated Server Status"]')?.textContent || "";
    const mode = colorModeInput ? colorModeInput.value : "static";
    let previewColor = colorInput ? colorInput.value : "#71368a";
    if (mode === "role" && roleColorInput) previewColor = roleColorInput.value;
    if (mode === "status") {
      if (statusText.includes("Starting") && startingColorInput) previewColor = startingColorInput.value;
      else if (statusText.includes("Online") && onlineColorInput) previewColor = onlineColorInput.value;
      else if (offlineColorInput) previewColor = offlineColorInput.value;
    }
    document.querySelectorAll("[data-preview-color]").forEach((bar) => {
      bar.style.background = previewColor;
    });
    const updatePreviewImage = (selector, source) => {
      const value = source ? source.value : "";
      document.querySelectorAll(selector).forEach((img) => {
        if (value) {
          img.src = value;
          img.hidden = false;
        } else {
          img.hidden = true;
        }
      });
    };
    updatePreviewImage("[data-preview-thumb]", thumbSelect);
    updatePreviewImage("[data-preview-image]", imageSelect);
    if (timezoneSelect || formatSelect) {
      const timezone = timezoneSelect ? timezoneSelect.value : "UTC";
      const format = formatSelect ? formatSelect.value : "%Y-%m-%d %I:%M %p %Z";
      const now = new Date();
      let footer = now.toLocaleString("en-US", { timeZone: timezone, timeZoneName: "short" });
      if (format.includes("%Y-%m-%d")) {
        footer = now.toLocaleString("sv-SE", { timeZone: timezone }).replace("T", " ");
      }
      document.querySelectorAll("[data-preview-footer]").forEach((footerNode) => {
        footerNode.textContent = footer;
      });
    }
  };
  document.querySelectorAll("[data-preview-source]").forEach((field) => {
    field.addEventListener("input", updateEmbedPreview);
    field.addEventListener("change", updateEmbedPreview);
  });
  document.querySelectorAll('#tab-embeds input[name], #tab-embeds select[name], #tab-overview input[name]').forEach((field) => {
    field.addEventListener("input", updateEmbedPreview);
    field.addEventListener("change", updateEmbedPreview);
  });
  updateEmbedPreview();

  const thumbnailFile = document.getElementById("thumbnailEditorFile");
  const thumbnailCanvas = document.getElementById("thumbnailEditorCanvas");
  const thumbnailData = document.getElementById("editedThumbnailData");
  const thumbnailZoom = document.getElementById("thumbnailZoom");
  const thumbnailOffsetX = document.getElementById("thumbnailOffsetX");
  const thumbnailOffsetY = document.getElementById("thumbnailOffsetY");
  if (thumbnailFile && thumbnailCanvas && thumbnailData) {
    const ctx = thumbnailCanvas.getContext("2d");
    const image = new Image();
    const drawThumbnail = () => {
      ctx.fillStyle = "#20242b";
      ctx.fillRect(0, 0, thumbnailCanvas.width, thumbnailCanvas.height);
      if (!image.src) return;
      const zoom = Number(thumbnailZoom.value || 1);
      const offsetX = Number(thumbnailOffsetX.value || 0);
      const offsetY = Number(thumbnailOffsetY.value || 0);
      const scale = Math.max(thumbnailCanvas.width / image.width, thumbnailCanvas.height / image.height) * zoom;
      const width = image.width * scale;
      const height = image.height * scale;
      const x = (thumbnailCanvas.width - width) / 2 + offsetX;
      const y = (thumbnailCanvas.height - height) / 2 + offsetY;
      ctx.drawImage(image, x, y, width, height);
      thumbnailData.value = thumbnailCanvas.toDataURL("image/png");
    };
    thumbnailFile.addEventListener("change", () => {
      const file = thumbnailFile.files && thumbnailFile.files[0];
      if (!file) return;
      image.onload = drawThumbnail;
      image.src = URL.createObjectURL(file);
    });
    [thumbnailZoom, thumbnailOffsetX, thumbnailOffsetY].forEach((input) => {
      if (input) input.addEventListener("input", drawThumbnail);
    });
    drawThumbnail();
  }
});
