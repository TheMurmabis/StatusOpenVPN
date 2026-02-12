document.addEventListener("DOMContentLoaded", () => {
  const adminAddInput = document.getElementById("adminAddInput");
  const adminAddButton = document.getElementById("adminAddButton");
  const adminCandidates = document.getElementById("adminCandidates");
  const adminAlert = document.getElementById("adminAlert");
  const adminList = document.getElementById("adminList");
  const adminIdInput = document.getElementById("admin_id");
  const botStatusIndicator = document.getElementById("botStatusIndicator");
  const adminCandidatesListId = adminAddInput?.dataset?.listId;
  const input = document.getElementById("bot_token");
  const toggle = document.getElementById("toggleToken");
  const icon = document.getElementById("toggleTokenIcon");

  const showAlert = (type, message) => {
    if (!adminAlert) return;
    adminAlert.innerHTML = `
      <div class="alert alert-${type} alert-dismissible fade show" role="alert">
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      </div>`;
  };

  const renderAdminList = (admins) => {
    if (!adminList) return;
    adminList.innerHTML = "";
    if (!admins || admins.length === 0) {
      adminList.innerHTML =
        '<li class="list-group-item text-muted">Администраторы не добавлены.</li>';
      return;
    }
    admins.forEach((admin) => {
      const item = document.createElement("li");
      item.className =
        "list-group-item d-flex justify-content-between align-items-center";
      item.innerHTML = `
        <span>${admin.display}</span>
        <button type="button" class="btn btn-sm btn-outline-danger js-remove-admin"
          data-admin-id="${admin.id}">✕</button>`;
      adminList.appendChild(item);
    });
  };

  const renderCandidates = (availableAdmins) => {
    if (!adminCandidates) return;
    adminCandidates.innerHTML = "";
    if (!availableAdmins || availableAdmins.length === 0) {
      return;
    }
    availableAdmins.forEach((admin) => {
      const option = document.createElement("option");
      option.value = admin.id;
      option.textContent = admin.display;
      adminCandidates.appendChild(option);
    });
  };

  const updateBotStatus = (active) => {
    if (!botStatusIndicator) return;
    botStatusIndicator.textContent = active ? "on" : "off";
    botStatusIndicator.classList.toggle("bg-success", active);
    botStatusIndicator.classList.toggle("bg-danger", !active);
  };

  const applyResponse = (data) => {
    if (!data) return;
    renderAdminList(data.admins);
    renderCandidates(data.available_admins);
    if (adminIdInput) {
      adminIdInput.value = data.admin_id_value || "";
    }
    if (typeof data.bot_service_active !== "undefined") {
      updateBotStatus(Boolean(data.bot_service_active));
    }
  };

  const addAdmin = async () => {
    const value = adminAddInput?.value?.trim();
    if (!value) {
      showAlert("warning", "Введите ID или выберите пользователя.");
      return;
    }

    if (adminAddButton) {
      adminAddButton.setAttribute("disabled", "disabled");
    }

    try {
      const basePath = window.basePath || '';
      const response = await fetch(`${basePath}/api/admins/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_id: value }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const message = data?.message || "Произошла ошибка.";
        showAlert("danger", message);
        return;
      }
      applyResponse(data);
      if (adminAddInput) {
        adminAddInput.value = "";
      }
      showAlert("success", data.message || "Администратор добавлен.");
    } catch (error) {
      showAlert("danger", "Произошла ошибка при добавлении.");
    } finally {
      adminAddButton?.removeAttribute("disabled");
    }
  };

  adminAddButton?.addEventListener("click", addAdmin);

  adminList?.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains("js-remove-admin")) return;

    const adminId = target.getAttribute("data-admin-id");
    if (!adminId) return;

    try {
      target.setAttribute("disabled", "disabled");
      const basePath = window.basePath || '';
      const response = await fetch(`${basePath}/api/admins/remove`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_id: adminId }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const message = data?.message || "Произошла ошибка.";
        showAlert("danger", message);
        return;
      }
      applyResponse(data);
      showAlert("success", data.message || "Администратор удалён.");
    } catch (error) {
      showAlert("danger", "Произошла ошибка при удалении.");
    } finally {
      target.removeAttribute("disabled");
    }
  });

  adminAddInput?.addEventListener("input", () => {
    const value = adminAddInput.value.trim();
    if (value && adminCandidatesListId) {
      adminAddInput.setAttribute("list", adminCandidatesListId);
    } else {
      adminAddInput.removeAttribute("list");
    }
  });

  adminAddInput?.addEventListener("focus", () => {
    adminAddInput.removeAttribute("list");
  });

  adminAddInput?.addEventListener("blur", () => {
    if (!adminAddInput.value.trim()) {
      adminAddInput.removeAttribute("list");
    }
  });

  // Функции для показа/скрытия токена
  if (!input || !toggle) return;

  toggle.addEventListener("click", () => {
    const isHidden = input.classList.contains("masked");

    input.classList.toggle("masked", !isHidden);
    icon.classList.toggle("fa-eye", !isHidden);
    icon.classList.toggle("fa-eye-slash", isHidden);
  });

});
