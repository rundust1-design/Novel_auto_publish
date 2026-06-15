def attach_dialog_handler(page):
    def _handle_dialog(dialog):
        message = dialog.message
        print(f"[DIALOG] {message}")
        try:
            dialog.accept()
        except Exception:
            pass

    try:
        page.on("dialog", _handle_dialog)
    except Exception:
        pass


def dismiss_faloo_popups(page):
    try:
        return page.evaluate(r"""() => {
            const keywords = ['去配音', '配音', 'AI配音', '立即配音'];
            const closeTexts = ['关闭', '取消', '跳过', '我知道了', '知道了', '暂不', '以后再说', '×', 'X'];
            const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            };
            const norm = (text) => (text || '').replace(/\s+/g, '').trim();
            const all = Array.from(document.querySelectorAll('body *')).filter(isVisible);
            const safePageSelectors = ['#nodeForm', '#volumeList', '#nodeList', '.nodeArea', '#formArea'];
            const isInsideSafePage = (el) => el.closest && safePageSelectors.some((selector) => el.closest(selector));
            const keywordNode = all.find((el) => {
                const text = norm(el.innerText || el.textContent || el.value);
                if (!keywords.some((word) => text.includes(word))) return false;
                if (isInsideSafePage(el)) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 120 || rect.height > 50;
            });
            if (!keywordNode) return {found: false, removed: 0, clicked: false};

            const closeNode = all.find((el) => {
                if (isInsideSafePage(el)) return false;
                const text = norm(el.innerText || el.textContent || el.value || el.getAttribute('title') || el.getAttribute('aria-label'));
                const className = String(el.className || '').toLowerCase();
                const rect = el.getBoundingClientRect();
                const nearKeyword = Math.abs(rect.top - keywordNode.getBoundingClientRect().top) < 260;
                return nearKeyword && (closeTexts.includes(text) || className.includes('close') || className.includes('cancel'));
            });
            if (closeNode) {
                closeNode.click();
                return {found: true, removed: 0, clicked: true, text: norm(closeNode.innerText || closeNode.value || closeNode.textContent)};
            }

            const containers = [];
            let current = keywordNode;
            while (current && current !== document.body) {
                const rect = current.getBoundingClientRect();
                const style = window.getComputedStyle(current);
                const zIndex = Number.parseInt(style.zIndex || '0', 10) || 0;
                if ((rect.width >= 220 && rect.height >= 120) || zIndex >= 10 || style.position === 'fixed' || style.position === 'absolute') {
                    containers.push(current);
                }
                current = current.parentElement;
            }
            const target = containers.find((el) => !isInsideSafePage(el)) || keywordNode.parentElement || keywordNode;
            let removed = 0;
            if (target && target.parentElement && !isInsideSafePage(target)) {
                target.remove();
                removed += 1;
            }

            Array.from(document.querySelectorAll('body *')).forEach((el) => {
                if (isInsideSafePage(el)) return;
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                const zIndex = Number.parseInt(style.zIndex || '0', 10) || 0;
                const opacity = Number.parseFloat(style.opacity || '1');
                const isOverlay = (style.position === 'fixed' || style.position === 'absolute')
                    && rect.width >= window.innerWidth * 0.6
                    && rect.height >= window.innerHeight * 0.6
                    && zIndex >= 10
                    && opacity >= 0.2;
                if (isOverlay) {
                    el.remove();
                    removed += 1;
                }
            });
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
            return {found: true, removed, clicked: false};
        }""")
    except Exception as exc:
        print(f"[WARN] Faloo popup cleanup failed: {exc}")
        return {"found": False, "error": str(exc)}


def dismiss_platform_popups(page, platform):
    if platform.get("key") == "faloo":
        result = dismiss_faloo_popups(page)
        if result.get("found"):
            print(f"[INFO] Faloo popup handled: {result}")
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass
        return result
    return {"found": False}



def detect_web_security_block(page):
    block_keywords = [
        "Web\u5e94\u7528\u9632\u62a4\u670d\u52a1",
        "\u60a8\u5f53\u524d\u8bbf\u95ee\u5b58\u5728Web\u5b89\u5168\u98ce\u9669",
        "\u8bbf\u95ee\u4e0d\u5408\u89c4",
        "\u5b89\u5168\u98ce\u9669",
        "\u8bbf\u95ee\u88ab\u62e6\u622a",
        "WAF",
    ]
    try:
        body_text = page.locator("body").inner_text(timeout=2000)
    except Exception:
        body_text = ""
    compact_text = ''.join(body_text.split())
    matched = [word for word in block_keywords if word in compact_text]
    if matched:
        raise RuntimeError(f"Web security protection blocked this visit: {','.join(matched)}")
