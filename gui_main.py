"""Unified multi-platform GUI for Novel Auto Publish.

Launches a pywebview desktop window that drives publish.py via
a progress callback, rather than re-implementing automation.
All platform-specific logic (KindEditor, Ant Design, Quill, etc.)
lives in publish.py — the GUI is a thin visual shell.
"""

import os
import sys
import json
import threading
import webview
from playwright.sync_api import sync_playwright

from platform_config import PLATFORMS
from publish import main as publish_main

CONFIG_FILE = "config.json"


class Api:
    """JS-Python bridge exposed to the webview frontend.

    IMPORTANT: pywebview's _createApi walks all public attributes on this
    object to build its function registry. Any non-primitive public attribute
    (especially the Window object) will be recursed into, causing infinite
    recursion on WinForms/WebView2 native control chains.
    Keep non-method attributes prefixed with '_'.
    """

    def __init__(self):
        self._window = None
        self._config = self._load_config()

    def _set_window(self, window):
        self._window = window

    # ---- config ------------------------------------------------------------

    def _load_config(self):
        base = os.path.dirname(os.path.abspath(__file__))
        default = {
            "archive_dir": os.path.join(base, "uploaded"),
            "source_dir": os.path.join(base, "chapters"),
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    default.update(json.load(f))
            except Exception:
                pass
        return default

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def get_config(self):
        return self._config

    def choose_dir(self, key="archive_dir"):
        """Open native folder picker and store result under *key* in config."""
        if not self._window:
            return None
        try:
            result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if result and result[0]:
                self._config[key] = result[0]
                self._save_config()
                return result[0]
        except Exception as e:
            self.log(f"[错误] 选择目录失败: {e}", "text-rose-400")
        return None

    def get_platform_dirs(self, platform_key):
        """Return default source_dir and archive_dir for a platform."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return {
            "source_dir": os.path.join(base_dir, "chapters", platform_key),
            "archive_dir": os.path.join(base_dir, "uploaded", platform_key),
        }

    # ---- platform helpers --------------------------------------------------

    def get_platforms(self):
        """Return all registered platforms for the dropdown."""
        return [
            {"key": p["key"], "name": p["name"]}
            for p in PLATFORMS.values()
        ]

    def _resolve_platform(self, platform_key):
        p = PLATFORMS.get(platform_key)
        if not p:
            raise ValueError(f"Unknown platform: {platform_key}")
        return p

    # ---- login state -------------------------------------------------------

    def check_login_state(self, platform_key):
        p = self._resolve_platform(platform_key)
        state_file = p.get("state_file", "state.json")
        return os.path.exists(state_file)

    def do_login(self, platform_key):
        """Launch browser for manual login, then save storage state."""
        p = self._resolve_platform(platform_key)
        state_file = p.get("state_file", "state.json")
        login_url = p["login_url"]
        name = p["name"]

        def _thread():
            self.log(f">>> 正在启动浏览器，目标平台: {name}", "text-indigo-400 font-bold")
            try:
                with sync_playwright() as pw:
                    # Try system browsers first (PyInstaller compatibility)
                    for channel in ("msedge", "chrome", None):
                        try:
                            if channel:
                                browser = pw.chromium.launch(channel=channel, headless=False)
                            else:
                                browser = pw.chromium.launch(headless=False)
                            break
                        except Exception:
                            continue

                    if os.path.exists(state_file):
                        self.log("发现已有登录凭证，尝试加载...")
                        context = browser.new_context(storage_state=state_file)
                    else:
                        context = browser.new_context()

                    page = context.new_page()
                    self.log(f"正在导航到 {name} 登录页...")
                    try:
                        page.goto(login_url, timeout=60000)
                    except Exception:
                        pass

                    self.log(f"【请在浏览器中完成登录】", "text-yellow-400 font-bold")

                    result = self._window.create_confirmation_dialog(
                        "登录确认",
                        f"请在浏览器窗口中完成 {name} 的登录操作。\n\n"
                        f"确认已看到作家后台主界面后，点击【确定】保存登录状态。\n"
                        f"点击【取消】则放弃保存。"
                    )

                    if result:
                        context.storage_state(path=state_file)
                        self.log(f"登录凭证已保存 -> {state_file}", "text-emerald-400 font-bold")
                    else:
                        self.log("登录流程已取消，凭证未保存。", "text-rose-400")

                    browser.close()
            except Exception as e:
                self.log(f"登录流程崩溃: {e}", "text-rose-500 font-bold")

        th = threading.Thread(target=_thread, daemon=True)
        th.start()
        th.join()
        return True

    # ---- book scanning -----------------------------------------------------

    def get_books(self, platform_key, source_dir=None):
        """Scan for book folders in the given source_dir, or auto-derive."""
        import glob
        books = []
        if not source_dir or not os.path.isdir(source_dir):
            source_dir = os.path.join("chapters", platform_key)

        if not os.path.isdir(source_dir):
            return books

        for name in sorted(os.listdir(source_dir)):
            sub = os.path.join(source_dir, name)
            if os.path.isdir(sub):
                txts = glob.glob(os.path.join(sub, "*.txt"))
                if txts:
                    books.append({
                        "name": name,
                        "count": len(txts),
                    })
        return books

    # ---- publish -----------------------------------------------------------

    def log(self, msg, color="text-slate-400"):
        """Push a log entry to the JS console."""
        if self._window:
            safe = msg.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            try:
                self._window.evaluate_js(f'window.appendLog("{safe}", "{color}");')
            except Exception:
                print(msg)

    def _update_progress(self, current, total):
        if self._window:
            try:
                self._window.evaluate_js(f"window.updateProgress({current}, {total});")
            except Exception:
                pass

    def _progress_cb(self, stage, data):
        """Callback passed to publish.main() — pushes progress to JS."""
        if stage == "init":
            total = data.get("total", 0)
            self._update_progress(0, total)
            self.log(f"发布队列已就绪，共 {total} 章", "text-accent-400 font-bold")

        elif stage == "chapter_start":
            n = data.get("chapter_num", "?")
            t = data.get("chapter_title", "")
            total = data.get("total", 0)
            self.log(f"[{n}/{total}] 开始发布: {t}", "text-yellow-300 font-bold")
            self._update_progress(data.get("current", 0), total)

        elif stage == "chapter_navigate":
            self.log(f"  -> 导航到编辑页面...", "text-slate-500")

        elif stage == "chapter_fill":
            self.log(f"  -> 填充章节内容...", "text-slate-500")

        elif stage == "chapter_publish":
            self.log(f"  -> 点击发布按钮...", "text-slate-500")

        elif stage == "chapter_done":
            success = data.get("success", False)
            reason = data.get("reason", "")
            n = data.get("chapter_num", "?")
            t = data.get("chapter_title", "")
            total = data.get("total", 0)
            current = data.get("current", 0)
            self._update_progress(current, total)
            if success:
                self.log(f"  [成功] 第{n}章 {t}", "text-emerald-400 font-bold")
                self.log(f"  [详情] {reason}", "text-emerald-600")
            else:
                self.log(f"  [失败] 第{n}章 {t}: {reason}", "text-rose-500 font-bold")

        elif stage == "all_done":
            results = data.get("results", [])
            ok = sum(1 for r in results if r.get("success"))
            fail = len(results) - ok
            self.log(f"\n{'='*50}", "text-indigo-400 font-bold")
            self.log(f"发布完成: 成功 {ok} 章, 失败 {fail} 章", "text-accent-400 font-bold text-lg")
            self.log(f"{'='*50}\n", "text-indigo-400 font-bold")
            self._update_progress(len(results), len(results))

    def start_publish(self, platform_key, book_name, publish_count, volume_num):
        """Run publish.main() with a progress callback on a background thread."""
        def _thread():
            try:
                publish_main(
                    platform_key=platform_key,
                    book_name=book_name,
                    publish_count=publish_count,
                    volume_num=volume_num,
                    no_prompt=True,
                    headless=False,
                    progress_cb=self._progress_cb,
                )
            except Exception as e:
                self.log(f"发布流程异常: {e}", "text-rose-500 font-bold")
                import traceback
                self.log(traceback.format_exc(), "text-rose-400")

        th = threading.Thread(target=_thread, daemon=True)
        th.start()
        th.join()
        return True

    # ---- file system helpers -----------------------------------------------

    def open_folder(self, path):
        """Open a folder in Windows Explorer."""
        if path and os.path.isdir(path):
            os.startfile(path)
            self.log(f"已打开目录: {path}", "text-slate-400")
        else:
            self.log(f"目录不存在: {path}", "text-rose-400")


# =========================================================================
if __name__ == "__main__":
    api = Api()

    # PyInstaller compatibility: resolve web/ directory
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    html_path = "file://" + os.path.join(base, "web", "index.html").replace("\\", "/")

    window = webview.create_window(
        "Novel Auto Publish PRO",
        html_path,
        js_api=api,
        width=1200,
        height=820,
        min_size=(900, 600),
        text_select=True,
    )
    api._set_window(window)
    webview.start()
