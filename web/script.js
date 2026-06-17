// Elements
const el = {
    platformSelect: document.getElementById('platform-select'),
    btnOpenSource: document.getElementById('btn-open-source'),
    btnOpenData: document.getElementById('btn-open-data'),
    btnLogin: document.getElementById('btn-login'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnStart: document.getElementById('btn-start'),
    btnClear: document.getElementById('btn-clear'),
    btnChooseDir: document.getElementById('btn-choose-dir'),
    archiveDirInput: document.getElementById('archive-dir-input'),
    btnChooseSourceDir: document.getElementById('btn-choose-source-dir'),
    sourceDirInput: document.getElementById('source-dir-input'),
    bookSelect: document.getElementById('book-select'),
    bookStatus: document.getElementById('book-status'),
    publishCount: document.getElementById('publish-count'),
    volumeNum: document.getElementById('volume-num'),
    logContainer: document.getElementById('log-container'),
    statusBadge: document.getElementById('status-badge'),
    progressWrapper: document.getElementById('progress-wrapper'),
    progressBar: document.getElementById('progress-bar'),
    progressText: document.getElementById('progress-text'),
};

let currentBooks = [];
let currentPlatform = '';
let isPublishing = false;

// ============ Logging (must be defined FIRST — called by init) ============

window.appendLog = function (msg, colorClass = "text-slate-400") {
    const div = document.createElement('div');
    div.className = `fade-in break-words ${colorClass}`;
    div.textContent = msg;
    el.logContainer.appendChild(div);
    el.logContainer.scrollTop = el.logContainer.scrollHeight;
};

// ============ Progress (called from Python via evaluate_js) ============

window.updateProgress = function (current, total) {
    if (total <= 0) return;
    const percent = Math.min(100, Math.round((current / total) * 100));
    el.progressWrapper.classList.remove('hidden');
    el.progressText.classList.remove('hidden');
    el.progressBar.style.width = percent + '%';
    el.progressText.textContent = `${current} / ${total}`;
};

// ============ Platform Management ============

async function loadPlatforms() {
    try {
        appendLog(">>> 正在加载平台列表...", "text-slate-500");
        const platforms = await window.pywebview.api.get_platforms();
        appendLog(`>>> API 返回: ${JSON.stringify(platforms)}`, "text-amber-400");
        el.platformSelect.innerHTML = '';
        if (!platforms || platforms.length === 0) {
            appendLog("[错误] 平台列表为空", "text-rose-500 font-bold");
            el.platformSelect.innerHTML = '<option value="">无可用平台</option>';
            return;
        }
        platforms.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.key;
            opt.textContent = p.name;
            el.platformSelect.appendChild(opt);
        });
        el.platformSelect.value = platforms[0].key;
        currentPlatform = platforms[0].key;
        appendLog(`>>> 已加载 ${platforms.length} 个平台`, "text-emerald-400 font-bold");
    } catch (e) {
        console.error(e);
        appendLog(`[错误] 加载平台列表失败: ${e}`, "text-rose-500 font-bold");
        el.platformSelect.innerHTML = '<option value="">加载失败</option>';
    }
}

el.platformSelect.addEventListener('change', async () => {
    currentPlatform = el.platformSelect.value;
    appendLog(`>>> 已切换平台: ${el.platformSelect.options[el.platformSelect.selectedIndex].text}`, "text-accent-400 font-bold");
    await updatePlatformDirs();
    checkState();
    refreshBooks();
});

// ============ State Management ============

async function updatePlatformDirs() {
    if (!window.pywebview || !currentPlatform) return;
    try {
        const dirs = await window.pywebview.api.get_platform_dirs(currentPlatform);
        if (dirs && dirs.source_dir) {
            el.sourceDirInput.value = dirs.source_dir;
        }
        if (dirs && dirs.archive_dir) {
            el.archiveDirInput.value = dirs.archive_dir;
        }
    } catch (e) {
        console.error(e);
    }
}

async function checkState() {
    if (!window.pywebview || !currentPlatform) return;
    try {
        const ok = await window.pywebview.api.check_login_state(currentPlatform);
        if (ok) {
            el.statusBadge.innerHTML = `<div class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_3px_currentColor]"></div> 已登录`;
            el.statusBadge.className = "px-3 py-2 rounded-lg text-[11px] font-bold tracking-widest bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-2 shadow-sm";
        } else {
            el.statusBadge.innerHTML = `<div class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse shadow-[0_0_3px_currentColor]"></div> 未登录`;
            el.statusBadge.className = "px-3 py-2 rounded-lg text-[11px] font-bold tracking-widest bg-rose-500/10 text-rose-400 border border-rose-500/30 flex items-center gap-2 shadow-sm";
        }
    } catch (e) {
        console.error(e);
    }
}

// ============ Book Management ============

async function refreshBooks() {
    el.bookSelect.innerHTML = '<option value="">扫描中...</option>';
    el.bookStatus.textContent = '';

    const icon = document.getElementById('refresh-icon');
    if (icon) icon.classList.add('animate-spin');

    try {
        currentBooks = await window.pywebview.api.get_books(currentPlatform, el.sourceDirInput.value);

        el.bookSelect.innerHTML = '';

        if (currentBooks.length === 0) {
            el.bookSelect.innerHTML = '<option value="">chapters 目录下暂无小说</option>';
            el.bookStatus.textContent = '请先设置草稿来源目录';
        } else {
            currentBooks.forEach((b, i) => {
                const opt = document.createElement('option');
                opt.value = i;
                opt.textContent = `${b.name} (${b.count}章未发)`;
                el.bookSelect.appendChild(opt);
            });
            if (currentBooks.length > 0) {
                el.bookSelect.value = "0";
                updateBookStatus();
            }
        }
    } catch (e) {
        console.error(e);
        appendLog(`[错误] 刷新小说列表失败: ${e}`, "text-rose-500");
    } finally {
        setTimeout(() => {
            const icon = document.getElementById('refresh-icon');
            if (icon) icon.classList.remove('animate-spin');
        }, 500);
    }
}

el.bookSelect.addEventListener('change', updateBookStatus);
el.btnRefresh.addEventListener('click', refreshBooks);

function updateBookStatus() {
    const idx = parseInt(el.bookSelect.value);
    if (!isNaN(idx) && currentBooks[idx]) {
        const book = currentBooks[idx];
        el.bookStatus.textContent = `共 ${book.count} 个待发布章节`;
    }
}

// ============ UI Toggle ============

function toggleUI(disabled) {
    isPublishing = disabled;
    el.btnStart.disabled = disabled;
    el.btnLogin.disabled = disabled;
    el.btnRefresh.disabled = disabled;
    el.btnChooseDir.disabled = disabled;
    el.btnChooseSourceDir.disabled = disabled;
    el.bookSelect.disabled = disabled;
    el.publishCount.disabled = disabled;
    el.volumeNum.disabled = disabled;
    el.platformSelect.disabled = disabled;

    if (disabled) {
        el.btnStart.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> 正在发布中...`;
        el.btnStart.classList.add('opacity-50', 'cursor-not-allowed', 'shadow-none');
        el.statusBadge.innerHTML = `<div class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse shadow-[0_0_3px_currentColor]"></div> 运行中`;
        el.statusBadge.className = "px-3 py-2 rounded-lg text-[11px] font-bold tracking-widest bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-2 shadow-sm";
    } else {
        el.btnStart.innerHTML = `<i class="fa-solid fa-rocket"></i> 启动全自动发布`;
        el.btnStart.classList.remove('opacity-50', 'cursor-not-allowed', 'shadow-none');
        el.progressWrapper.classList.add('hidden');
        el.progressText.classList.add('hidden');
        el.progressBar.style.width = '0%';
        checkState();
    }
}

// ============ Actions ============

el.btnLogin.addEventListener('click', async () => {
    if (isPublishing) return;
    if (!currentPlatform) {
        appendLog("[错误] 请先选择一个平台", "text-rose-500");
        return;
    }
    toggleUI(true);
    el.btnStart.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 等待登录完成...`;
    try {
        await window.pywebview.api.do_login(currentPlatform);
    } finally {
        toggleUI(false);
    }
});

el.btnOpenSource.addEventListener('click', async () => {
    if (!el.sourceDirInput.value) return;
    await window.pywebview.api.open_folder(el.sourceDirInput.value);
});

el.btnOpenData.addEventListener('click', async () => {
    if (!el.archiveDirInput.value) return;
    await window.pywebview.api.open_folder(el.archiveDirInput.value);
});

el.btnChooseDir.addEventListener('click', async () => {
    if (isPublishing) return;
    const dir = await window.pywebview.api.choose_dir('archive_dir');
    if (dir) {
        el.archiveDirInput.value = dir;
        appendLog(`[系统] 归档目录已设置: ${dir}`, "text-emerald-400");
    }
});

el.btnChooseSourceDir.addEventListener('click', async () => {
    if (isPublishing) return;
    const dir = await window.pywebview.api.choose_dir('source_dir');
    if (dir) {
        el.sourceDirInput.value = dir;
        appendLog(`[系统] 草稿目录已设置: ${dir}`, "text-emerald-400");
        refreshBooks();
    }
});

el.btnStart.addEventListener('click', async () => {
    if (isPublishing) return;

    if (!el.sourceDirInput.value || !el.archiveDirInput.value) {
        appendLog("[错误] 请先设置草稿来源目录和归档目录", "text-rose-500 font-bold");
        return;
    }

    if (currentBooks.length === 0) {
        appendLog("[错误] 未找到任何小说，请先设置正确的草稿目录并刷新", "text-rose-500 font-bold");
        return;
    }

    const idx = parseInt(el.bookSelect.value);
    if (isNaN(idx) || !currentBooks[idx]) {
        appendLog("[错误] 请选择要发布的小说", "text-rose-500 font-bold");
        return;
    }

    const book = currentBooks[idx];

    let pCount = parseInt(el.publishCount.value);
    if (isNaN(pCount) || pCount <= 0) pCount = null;
    if (pCount && pCount > book.count) pCount = book.count;

    let vNum = parseInt(el.volumeNum.value);
    if (isNaN(vNum) || vNum <= 0) vNum = null;

    toggleUI(true);

    try {
        await window.pywebview.api.start_publish(currentPlatform, book.name, pCount, vNum);
    } catch (e) {
        console.error(e);
        appendLog(`[错误] 发布过程异常: ${e}`, "text-rose-500 font-bold");
    } finally {
        toggleUI(false);
        refreshBooks();
    }
});

el.btnClear.addEventListener('click', () => {
    el.logContainer.innerHTML = '<div class="text-slate-600 fade-in font-semibold">> 运行日志已被清空。</div>';
});

// ============ Init ============

// pywebview timing: api.js creates `window.pywebview` (with empty `api: {}`)
// BEFORE page load. But `_createApi()` populates the actual API methods in
// `finish.js`, which runs on the `loaded` event — AFTER our <script> runs.
// So we must check whether API methods actually exist before calling them.

function _apiReady() {
    return !!(window.pywebview && window.pywebview.api &&
              typeof window.pywebview.api.get_platforms === 'function');
}

async function initApp() {
    if (window._appInitialized) return;
    window._appInitialized = true;
    appendLog(">>> UI 框架加载成功，已连接 Python 内核", "text-accent-400 font-bold");

    // Load config and platform dirs
    try {
        const config = await window.pywebview.api.get_config();
        if (config && config.archive_dir) {
            el.archiveDirInput.value = config.archive_dir;
        }
        if (config && config.source_dir) {
            el.sourceDirInput.value = config.source_dir;
        }
    } catch (e) {
        appendLog(`[警告] 加载配置失败: ${e}`, "text-amber-400");
    }

    await loadPlatforms();
    await updatePlatformDirs();
    await checkState();
    await refreshBooks();
}

function tryInit() {
    if (!window._appInitialized && _apiReady()) {
        appendLog(">>> pywebview API 就绪，开始初始化...", "text-accent-400");
        initApp().catch(e => {
            console.error(e);
            appendLog(`[错误] 初始化失败: ${e}`, "text-rose-500 font-bold");
        });
    }
}

// Strategy: listen for pywebviewready (which fires AFTER _createApi), AND
// poll aggressively in case the event fires before our listener is attached.
window.addEventListener('pywebviewready', tryInit);

// Poll every 100ms for up to 5s until API is ready
let _pollCount = 0;
const _pollTimer = setInterval(() => {
    _pollCount++;
    if (_apiReady()) {
        clearInterval(_pollTimer);
        tryInit();
    } else if (_pollCount > 50) {
        clearInterval(_pollTimer);
        appendLog("[错误] pywebview API 超时 (5s) 仍未就绪", "text-rose-500 font-bold");
    }
}, 100);

// Also try immediately (API might already be ready)
tryInit();

// ============ Theme ============

function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
}

document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('theme') || 'blue';
    setTheme(saved);
});

(function () {
    const saved = localStorage.getItem('theme') || 'blue';
    document.documentElement.setAttribute('data-theme', saved);
})();

// Theme modal
document.getElementById('btn-open-theme').addEventListener('click', () => {
    const backdrop = document.getElementById('theme-modal-backdrop');
    const box = document.getElementById('theme-modal-box');
    backdrop.classList.remove('opacity-0', 'pointer-events-none');
    box.classList.remove('scale-95');
    box.classList.add('scale-100');
});

document.getElementById('theme-modal-close').addEventListener('click', () => {
    const backdrop = document.getElementById('theme-modal-backdrop');
    const box = document.getElementById('theme-modal-box');
    backdrop.classList.add('opacity-0', 'pointer-events-none');
    box.classList.remove('scale-100');
    box.classList.add('scale-95');
});

document.getElementById('theme-modal-backdrop').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        const backdrop = document.getElementById('theme-modal-backdrop');
        const box = document.getElementById('theme-modal-box');
        backdrop.classList.add('opacity-0', 'pointer-events-none');
        box.classList.remove('scale-100');
        box.classList.add('scale-95');
    }
});
