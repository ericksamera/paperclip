(async function () {
  const serverUrlInput = document.getElementById("serverUrl");
  const status = document.getElementById("status");
  const saveBtn = document.getElementById("saveBtn");

  const { serverUrl } = await chrome.storage.sync.get({ serverUrl: "http://127.0.0.1:8000" });
  serverUrlInput.value = serverUrl;

  saveBtn.addEventListener("click", async () => {
    await chrome.storage.sync.set({ serverUrl: serverUrlInput.value.trim() });
    status.textContent = "Saved!";
    setTimeout(() => status.textContent = "", 1500);
  });
})();
