import argparse
import glob
import json
import os
import re
import shutil
from playwright.sync_api import sync_playwright
from platform_config import DEFAULT_PLATFORM, get_platform
from platform_utils import attach_dialog_handler, dismiss_platform_popups
from anti_detect import launch_anti_detect_browser, create_anti_detect_context
from log_utils import log_result

CHAPTERS_DIR = "chapters"
UPLOADED_DIR = "uploaded"


def resolve_existing_state_file(platform):
    candidates = [platform["state_file"], *platform.get("fallback_state_files", [])]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def natural_chapter_sort_key(file_path):
    title = os.path.splitext(os.path.basename(file_path))[0]
    match = re.search(r"\d+", title)
    return (0, int(match.group(0)), title.casefold()) if match else (1, title.casefold())


def scan_books(source_dir):
    books = []
    if not os.path.isdir(source_dir):
        return books
    for name in sorted(os.listdir(source_dir)):
        path = os.path.join(source_dir, name)
        if not os.path.isdir(path):
            continue
        txt_files = sorted(glob.glob(os.path.join(path, "*.txt")), key=natural_chapter_sort_key)
        if txt_files:
            books.append((name, path, txt_files))
    return books


def platform_source_dir(platform):
    return os.path.join(CHAPTERS_DIR, platform["key"])


def platform_archive_dir(platform):
    return os.path.join(UPLOADED_DIR, platform["key"])


def resolve_platform_source_dir(platform):
    source_dir = platform_source_dir(platform)
    if os.path.isdir(source_dir):
        return source_dir, False

    legacy_books = scan_books(CHAPTERS_DIR)
    if legacy_books:
        print(f"[WARN] Platform folder not found: {source_dir}")
        print(f"[WARN] Falling back to legacy shared folder: {CHAPTERS_DIR}")
        print(f"[WARN] Recommended: move files to {source_dir}/<book-name>/")
        return CHAPTERS_DIR, True

    return source_dir, False


def archive_uploaded_file(file_path, archive_dir):
    if not os.path.isfile(file_path):
        raise RuntimeError(f"archive target is not a file: {file_path}")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    shutil.move(file_path, os.path.join(archive_dir, os.path.basename(file_path)))


def parse_chapter(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # The first non-empty line is the chapter title (e.g. "\u7b2c12\u7ae0 \u9547\u5cb3\u9489").
    # Use it as the title and remove it from the body content.
    chapter_title = ""
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines:
        chapter_title = lines[0].strip()
        lines = lines[1:]

    # Extract chapter number from the title line
    num_match = re.search(r"\u7b2c\s*(\d+)\s*\u7ae0", chapter_title)
    chapter_num = num_match.group(1) if num_match else ""

    # Also try extracting from filename as fallback
    if not chapter_num:
        raw_title = os.path.splitext(os.path.basename(file_path))[0]
        match = re.search(r"(\d+)", raw_title)
        chapter_num = match.group(1) if match else ""

    # Strip leading empty lines from body
    while lines and not lines[0].strip():
        lines = lines[1:]

    return chapter_num, chapter_title, "".join(lines)


def first_visible_text(scope, texts, prefer_button=False, exact=True, last=False):
    for text in texts:
        locators = []
        if prefer_button:
            locators.append(scope.get_by_role("button", name=text).last if last else scope.get_by_role("button", name=text).first)
        locators.append(scope.get_by_text(text, exact=exact).last if last else scope.get_by_text(text, exact=exact).first)
        if exact:
            locators.append(scope.get_by_text(text, exact=False).last if last else scope.get_by_text(text, exact=False).first)
        for locator in locators:
            try:
                if locator.is_visible():
                    return locator
            except Exception:
                pass
    return None


def first_visible_placeholder(page, placeholders):
    for placeholder in placeholders:
        try:
            locator = page.get_by_placeholder(placeholder, exact=False).first
            if locator.is_visible():
                return locator
        except Exception:
            pass
    return None


def first_visible_selector(page, selectors):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible():
                return locator
        except Exception:
            pass
    return None


def qimao_body_editor(page):
    selectors = [
        '.q-contenteditable.book[contenteditable="true"]',
        '[contenteditable="true"].book',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible():
                return locator
        except Exception:
            pass
    return None


def is_editor_ready(page, platform):
    for selector in ["#inputTitle", *platform.get("title_selectors", [])]:
        try:
            if page.locator(selector).first.is_visible():
                return True
        except Exception:
            pass
    for selector in platform.get("tinymce_iframe_selectors", ["#mce_0_ifr"]):
        try:
            if page.locator(selector).first.is_visible():
                return True
        except Exception:
            pass
    if first_visible_selector(page, platform["body_selectors"]):
        return True
    if first_visible_placeholder(page, platform["title_placeholders"]):
        return True
    return False


def wait_for_editor_or_content(page, platform, timeout_ms=30000):
    deadline = timeout_ms // 1000
    for _ in range(max(1, deadline)):
        if is_editor_ready(page, platform):
            return True
        try:
            body_text = page.locator("body").inner_text(timeout=1000).strip()
            if any(text in body_text for text in platform["new_chapter_texts"] + platform["save_draft_texts"] + platform["next_step_texts"]):
                return True
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return False


def detect_web_security_block(page, platform=None, debug_name="web_security_block"):
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
    compact_text = re.sub(r"\s+", "", body_text)
    matched = [word for word in block_keywords if word in compact_text]
    if matched:
        raise RuntimeError(f"Web security protection blocked this visit: {','.join(matched)}")


def dismiss_popups(page, texts):
    for text in texts:
        try:
            button = first_visible_text(page, [text], prefer_button=True)
            if button:
                button.click(force=True)
                page.wait_for_timeout(500)
        except Exception:
            pass



def qimao_skip_important_notice(page, timeout_ms=15000):
    skip_texts = [
        "跳过", "跳过提醒", "我知道了", "知道了", "已知晓", "我已知晓",
        "我已阅读并知晓", "已阅读并知晓", "阅读并知晓", "继续发布", "继续", "稍后再说",
    ]
    notice_keywords = ["重要提醒", "提醒", "须知", "风险提示", "发布提示"]
    rounds = max(1, timeout_ms // 500)
    activated = False
    for _ in range(rounds):
        try:
            result = page.evaluate(r"""([skipTexts, noticeKeywords]) => {
                const isVisible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const norm = (text) => (text || '').replace(/\s+/g, '').trim();
                const bodyText = norm(document.body.innerText || document.body.textContent || '');
                const sawNotice = noticeKeywords.some((keyword) => bodyText.includes(keyword));
                if (!sawNotice) return {sawNotice: false};

                const candidates = Array.from(document.querySelectorAll('button, [role="button"], .el-button, .q-button, a, div, span'))
                    .filter(isVisible)
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const text = norm(el.innerText || el.textContent || el.value || '');
                        const disabled = el.disabled
                            || el.getAttribute('disabled') !== null
                            || el.getAttribute('aria-disabled') === 'true'
                            || /disabled|is-disabled/.test(String(el.className || ''));
                        const matches = skipTexts.some((word) => text.includes(word));
                        return {el, rect, text, disabled, matches, area: rect.width * rect.height};
                    })
                    .filter((item) => item.matches && item.rect.width >= 80 && item.rect.height >= 28)
                    .sort((a, b) => a.area - b.area);

                const button = candidates[0];
                if (!button) return {sawNotice: true, found: false};
                if (button.disabled || /\d+/.test(button.text)) {
                    return {sawNotice: true, found: true, disabled: true, text: button.text};
                }
                return {
                    sawNotice: true,
                    found: true,
                    disabled: false,
                    text: button.text,
                    x: button.rect.left + button.rect.width / 2,
                    y: button.rect.top + button.rect.height / 2,
                };
            }""", [skip_texts, notice_keywords])
            if not result.get("sawNotice"):
                return False
            if result.get("found") and not result.get("disabled"):
                if not activated:
                    page.mouse.move(result["x"], result["y"])
                    page.mouse.down()
                    page.mouse.up()
                    activated = True
                    page.wait_for_timeout(500)
                page.mouse.click(result["x"], result["y"], delay=120)
                page.wait_for_timeout(1200)
                try:
                    body_text = page.locator("body").inner_text(timeout=800)
                    compact_body = re.sub(r"\s+", "", body_text)
                    if not any(keyword in compact_body for keyword in notice_keywords):
                        print(f"[INFO] Qimao important notice handled: {result.get('text')}")
                        return True
                except Exception:
                    print(f"[INFO] Qimao important notice handled: {result.get('text')}")
                    return True
            elif result.get("found") and result.get("disabled"):
                activated = False
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False



def click_near_book_name_by_text(page, platform, book_name):
    return page.evaluate(r"""([bookName, entryTexts]) => {
        const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const norm = (text) => (text || '').replace(/\s+/g, ' ').trim();
        const scoreText = (text) => {
            if (text === '\u7ae0\u8282\u7ba1\u7406') return 0;
            if (text.includes('\u7ae0\u8282\u7ba1\u7406')) return 1;
            if (text.includes('\u7ba1\u7406\u7ae0\u8282')) return 2;
            if (text.includes('\u66f4\u65b0\u7ae0\u8282') || text.includes('\u7ae0\u8282\u66f4\u65b0')) return 3;
            if (text.includes('\u53d1\u5e03\u7ae0\u8282') || text.includes('\u4e0a\u4f20\u7ae0\u8282')) return 4;
            if (entryTexts.some((entryText) => text.includes(entryText))) return 10;
            return 999;
        };
        const cards = Array.from(document.querySelectorAll('.opus, .opusList, .book, .bookbox, .item, li, tr, .list, div'))
            .filter(isVisible)
            .filter((el) => norm(el.innerText || el.textContent).includes(bookName))
            .map((el) => ({el, text: norm(el.innerText || el.textContent), rect: el.getBoundingClientRect()}))
            .filter((item) => item.text.length <= bookName.length + 600)
            .sort((a, b) => a.text.length - b.text.length || b.rect.width * b.rect.height - a.rect.width * a.rect.height);

        for (const card of cards) {
            const buttons = Array.from(card.el.querySelectorAll('a, button, input[type=button], input[type=submit]'))
                .filter(isVisible)
                .map((el) => ({el, text: norm(el.innerText || el.value || el.textContent), rect: el.getBoundingClientRect()}))
                .map((item) => ({...item, score: scoreText(item.text)}))
                .filter((item) => item.score < 999)
                .sort((a, b) => a.score - b.score || a.rect.left - b.rect.left);
            if (buttons.length > 0) {
                const target = buttons[0];
                target.el.click();
                return {found: true, mode: 'card', text: target.text, score: target.score, x: target.rect.left + target.rect.width / 2, y: target.rect.top + target.rect.height / 2};
            }
        }

        const elements = Array.from(document.querySelectorAll('a, button, input[type=button], input[type=submit], td, span, div'))
            .filter(isVisible)
            .map(el => ({
                el,
                text: norm(el.innerText || el.value || el.textContent),
                rect: el.getBoundingClientRect(),
            }));
        const books = elements.filter(item => item.text === bookName || (item.text.includes(bookName) && item.text.length <= bookName.length + 80));
        const entries = elements
            .map((item) => ({...item, score: scoreText(item.text)}))
            .filter(item => item.score < 999);
        for (const book of books) {
            const rowEntries = entries
                .filter(item => Math.abs((item.rect.top + item.rect.height / 2) - (book.rect.top + book.rect.height / 2)) < 180)
                .filter(item => item.rect.left >= book.rect.left || item.rect.top >= book.rect.top)
                .sort((a, b) => a.score - b.score || Math.abs(a.rect.top - book.rect.top) - Math.abs(b.rect.top - book.rect.top) || a.rect.left - b.rect.left);
            const target = rowEntries[0];
            if (target) {
                target.el.click();
                return {found: true, mode: 'row', text: target.text, score: target.score, x: target.rect.left + target.rect.width / 2, y: target.rect.top + target.rect.height / 2};
            }
        }
        return {found: false, cardMatches: cards.length, bookMatches: books.length, entryMatches: entries.length};
    }""", [book_name, platform["chapter_manage_texts"] + platform["new_chapter_texts"]])


def find_entry_near_book_name(page, book_name):
    return page.evaluate(r"""([bookName]) => {
        const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const norm = (text) => (text || '').replace(/\s+/g, ' ').trim();
        const all = Array.from(document.querySelectorAll('body *')).filter(isVisible);
        const allowedEntries = [
            '\u53bb\u5199\u4f5c', '\u7ee7\u7eed\u5199\u4f5c', '\u5199\u4f5c',
            '\u7ae0\u8282\u7ba1\u7406', '\u7ba1\u7406\u7ae0\u8282', '\u66f4\u65b0\u7ae0\u8282',
            '\u7ae0\u8282\u66f4\u65b0', '\u53d1\u5e03\u7ae0\u8282', '\u4e0a\u4f20\u7ae0\u8282',
            '\u65b0\u589e\u7ae0\u8282', '\u6dfb\u52a0\u7ae0\u8282', '\u66f4\u65b0', '\u7ba1\u7406'
        ];

        const items = all.map(el => ({
            el,
            text: norm(el.innerText || el.textContent),
            rect: el.getBoundingClientRect(),
        }));

        const nameNodes = items
            .filter(item => item.text === bookName || (item.text.includes(bookName) && item.text.length <= bookName.length + 80))
            .sort((a, b) => a.text.length - b.text.length || a.rect.width - b.rect.width);

        const entryNodes = items
            .filter(item => allowedEntries.includes(item.text))
            .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);

        for (const nameItem of nameNodes) {
            const nameTop = nameItem.rect.top;
            const nameBottom = nameItem.rect.bottom;
            const nameCenterY = nameItem.rect.top + nameItem.rect.height / 2;
            const rowCandidates = entryNodes
                .filter(item => item.rect.left > nameItem.rect.left)
                .map(item => ({
                    ...item,
                    centerY: item.rect.top + item.rect.height / 2,
                    dy: Math.abs((item.rect.top + item.rect.height / 2) - nameCenterY),
                }))
                .filter(item => item.centerY >= nameTop - 20 && item.centerY <= nameBottom + 120)
                .sort((a, b) => Math.abs(a.centerY - nameCenterY) - Math.abs(b.centerY - nameCenterY) || b.rect.left - a.rect.left);
            if (rowCandidates.length > 0) {
                const target = rowCandidates[0];
                return {
                    found: true,
                    text: target.text,
                    bookText: nameItem.text,
                    dy: Math.round(target.dy),
                    x: Math.round(target.rect.left + target.rect.width / 2),
                    y: Math.round(target.rect.top + target.rect.height / 2),
                    targetX: Math.round(target.rect.left),
                    targetY: Math.round(target.rect.top),
                    bookX: Math.round(nameItem.rect.left),
                    bookY: Math.round(nameItem.rect.top),
                    bookBottom: Math.round(nameItem.rect.bottom),
                };
            }
        }

        return {
            found: false,
            names: nameNodes.map(item => ({text: item.text, x: Math.round(item.rect.left), y: Math.round(item.rect.top), h: Math.round(item.rect.height)})).slice(0, 20),
            entries: entryNodes.map(item => ({text: item.text, x: Math.round(item.rect.left), y: Math.round(item.rect.top)})).slice(0, 20),
        };
    }""", [book_name])


def choose_book(books, book_name, no_prompt):
    if book_name:
        for book in books:
            if book[0] == book_name:
                return book
        raise RuntimeError(f"Book folder not found: {book_name}")
    if no_prompt:
        return books[0]
    for idx, (name, _, txts) in enumerate(books, 1):
        print(f"[{idx}] {name} ({len(txts)} chapters)")
    choice = int(input(">>> Select book index: ").strip()) - 1
    return books[choice]


def open_chapter_manager(page, platform, book_name):
    urls = [platform["book_manage_url"]]
    for fallback_url in platform.get("book_manage_fallback_urls", []):
        if fallback_url not in urls:
            urls.append(fallback_url)

    last_error = None
    for url in urls:
        try:
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            detect_web_security_block(page, platform, "book_manage_blocked")
            dismiss_platform_popups(page, platform)
            print(f"Locating backend book card on {url}: {book_name}")
            if _try_open_chapter_manager_on_current_page(page, platform, book_name):
                return page
        except Exception as exc:
            last_error = exc
            print(f"[WARN] Failed on book manage url {url}: {exc}")
    raise RuntimeError(f"chapter manager entry not found for book: {book_name}; last_error={last_error}")


def _try_open_chapter_manager_on_current_page(page, platform, book_name):
    if platform.get("key") == "faloo":
        faloo_result = click_near_book_name_by_text(page, platform, book_name)
        if faloo_result.get("found"):
            print(f"Clicking Faloo book operation entry: {faloo_result}")
            page.wait_for_timeout(5000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            return page
        print(f"Faloo text operation lookup failed: {faloo_result}")

    if platform.get("key") == "fanqie":
        cards = page.locator('div, li, section, article').filter(has_text=book_name)
        for idx in range(cards.count() - 1, -1, -1):
            try:
                card = cards.nth(idx)
                if not card.is_visible():
                    continue
                card.hover(timeout=3000)
                page.wait_for_timeout(800)
                entry = card.get_by_text("\u7ae0\u8282\u7ba1\u7406", exact=False).first
                if not entry.is_visible():
                    entry = page.get_by_text("\u7ae0\u8282\u7ba1\u7406", exact=False).first
                if entry.is_visible():
                    entry.click(force=True)
                    page.wait_for_timeout(3000)
                    return page
            except Exception:
                pass

    if platform.get("key") == "migu":
        # Migu shows book cards on the detail/count page, each with
        # "\u66f4\u591a\u7ba1\u7406", "\u7ae0\u8282\u7ba1\u7406", "\u65b0\u589e\u7ae0\u8282" buttons.
        cards = page.locator('div, li, section, article, tr').filter(has_text=book_name)
        for idx in range(cards.count() - 1, -1, -1):
            try:
                card = cards.nth(idx)
                if not card.is_visible():
                    continue
                entry = card.get_by_text("\u7ae0\u8282\u7ba1\u7406", exact=False).first
                if entry.is_visible():
                    entry.click(force=True)
                    page.wait_for_timeout(3000)
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    return page
            except Exception:
                pass
        # Fallback: try clicking "\u7ae0\u8282\u7ba1\u7406" anywhere on the page near the book name
        for idx in range(cards.count() - 1, -1, -1):
            try:
                card = cards.nth(idx)
                if not card.is_visible():
                    continue
                card.click(force=True)
                page.wait_for_timeout(2000)
                if "\u7ae0\u8282\u7ba1\u7406" in page.content():
                    return page
            except Exception:
                pass

    dom_result = find_entry_near_book_name(page, book_name)
    if dom_result.get("found"):
        print(f"Clicking target book row entry by coordinates: {dom_result}")
        page.mouse.move(dom_result["x"], dom_result["y"])
        page.wait_for_timeout(300)
        page.mouse.down()
        page.wait_for_timeout(100)
        page.mouse.up()
        page.wait_for_timeout(5000)
        if "/dashboard/books" in page.url:
            page.mouse.click(dom_result["x"], dom_result["y"])
            page.wait_for_timeout(5000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        if not wait_for_editor_or_content(page, platform, timeout_ms=20000):
            try:
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
        return page
    print(f"DOM book entry coordinate lookup failed: {dom_result}")

    card_selectors = [
        "article", "section", "li",
        '[class*="book"]', '[class*="work"]', '[class*="novel"]', '[class*="card"]', '[class*="item"]',
        "div",
    ]
    tried_cards = 0
    for selector in card_selectors:
        cards = page.locator(selector).filter(has_text=book_name)
        count = min(cards.count(), 20)
        for idx in range(count - 1, -1, -1):
            card = cards.nth(idx)
            try:
                if not card.is_visible():
                    continue
                tried_cards += 1
                card.scroll_into_view_if_needed(timeout=3000)
                card.hover(timeout=3000)
                page.wait_for_timeout(800)
                button = first_visible_text(card, platform["chapter_manage_texts"])
                if button:
                    print(f"Matched target book card with selector: {selector}")
                    button.click(force=True)
                    page.wait_for_timeout(4000)
                    return page
            except Exception:
                pass

    # Do not click a global chapter-management button here: it can belong to the previously selected book.
    return False


def wait_for_faloo_chapter_form(page, timeout_ms=30000):
    rounds = max(1, timeout_ms // 1000)
    for round_idx in range(rounds):
        try:
            has_form = page.locator("#nodeForm").first.is_visible()
            has_title = page.locator('input[placeholder="\u8bf7\u586b\u5199\u6807\u9898"], input[placeholder*="\u6807\u9898"]').first.is_visible()
            has_body = page.locator("#txtarea_content, textarea").first.is_visible()
            if has_form and has_title and has_body:
                return True
        except Exception:
            pass
        try:
            body_html = page.locator("body").inner_html(timeout=1000)
            is_blank_faloo_shell = "NodeList.js" in page.content() and "nodeForm" not in body_html and "txtarea_content" not in body_html
            if is_blank_faloo_shell and round_idx in (3, 8, 15):
                print("[WARN] Faloo chapter page shell is blank; reloading...")
                page.reload(wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return False


def fill_editor(page, platform, chapter_num, chapter_title, content):
    dismiss_popups(page, platform["dismiss_texts"])
    full_title = chapter_title.strip()
    if chapter_num and not re.search(r"^\s*\u7b2c\s*\d+", full_title):
        full_title = f"\u7b2c{chapter_num}\u7ae0 {full_title}".strip()

    # Fanqie auto-fills the chapter number prefix; strip it to avoid duplication
    if platform.get("key") == "fanqie":
        chapter_title = re.sub(r"第\s*\d+\s*章\s*", "", chapter_title).strip()
    title_value = full_title if platform.get("key") == "faloo" else chapter_title

    if platform.get("key") == "faloo":
        if not wait_for_faloo_chapter_form(page, timeout_ms=20000):
            raise RuntimeError("Faloo chapter form is not ready before fill")
        try:
            volume_select = page.locator("select").first
            if volume_select.is_visible():
                options = volume_select.locator("option")
                selected = False
                for idx in range(options.count()):
                    option = options.nth(idx)
                    text = option.inner_text(timeout=1000)
                    value = option.get_attribute("value") or ""
                    if "\u6b63\u6587" in text or value == "200":
                        if value:
                            current_value = volume_select.input_value(timeout=1000)
                            if current_value != value:
                                volume_select.select_option(value=value)
                                page.wait_for_timeout(1500)
                                wait_for_faloo_chapter_form(page, timeout_ms=10000)
                        else:
                            volume_select.select_option(label=text)
                            page.wait_for_timeout(1500)
                            wait_for_faloo_chapter_form(page, timeout_ms=10000)
                        selected = True
                        break
                if not selected and options.count() > 1:
                    fallback_value = options.nth(1).get_attribute("value")
                    if fallback_value:
                        volume_select.select_option(value=fallback_value)
                        page.wait_for_timeout(1500)
                        wait_for_faloo_chapter_form(page, timeout_ms=10000)
        except Exception as exc:
            print(f"[WARN] Faloo volume select failed: {exc}")

    qidian_title = page.locator("#inputTitle").first
    try:
        if qidian_title.is_visible():
            qidian_title.fill(chapter_title, force=True)
        else:
            raise RuntimeError("#inputTitle not visible")
    except Exception:
        num_input = page.locator('input[type="text"]').first
        try:
            if chapter_num and num_input.is_visible():
                num_input.fill(chapter_num, force=True)
        except Exception:
            pass
        title_input = None
        for selector in platform.get("title_selectors", []):
            try:
                candidate = page.locator(selector).first
                if candidate.is_visible():
                    title_input = candidate
                    break
            except Exception:
                pass
        if not title_input:
            title_input = first_visible_placeholder(page, platform["title_placeholders"])
        if not title_input:
            fallback = page.locator('input[type="text"]').last
            if fallback.is_visible():
                title_input = fallback
        if title_input:
            title_input.fill(title_value, force=True)
            try:
                title_input.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }")
            except Exception:
                pass
        elif platform.get("key") == "faloo":
            raise RuntimeError("Faloo title input not found")

    try:
        iframe = page.locator("#mce_0_ifr").first
        if iframe.is_visible():
            body = page.frame_locator("#mce_0_ifr").locator("body").first
            paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
            body.evaluate("""(el, paragraphs) => {
                el.focus();
                el.innerHTML = '';
                for (const para of paragraphs) {
                    const p = document.createElement('p');
                    p.textContent = para;
                    el.appendChild(p);
                }
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }""", paragraphs)
            try:
                page.evaluate("""(paragraphs) => {
                    if (window.tinymce && (window.tinymce.activeEditor || window.tinymce.get('mce_0'))) {
                        const html = paragraphs.map((para) => `<p>${para.replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]))}</p>`).join('');
                        const editor = (window.tinymce.activeEditor || window.tinymce.get('mce_0'));
                        if (!editor) return;
                        editor.setContent(html);
                        editor.fire('input');
                        editor.fire('change');
                    }
                }""", paragraphs)
            except Exception:
                pass
            return
    except Exception as exc:
        print(f"[WARN] TinyMCE iframe fill failed, fallback to generic editor: {exc}")

    editor = qimao_body_editor(page) if platform.get("key") == "qimao" else first_visible_selector(page, platform["body_selectors"])
    if not editor:
        raise RuntimeError("body editor not found")
    handle = editor.element_handle()
    page.evaluate("""([el, text]) => {
        el.focus();
        if ('value' in el) el.value = text;
        else el.innerText = text;
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('blur', {bubbles: true}));
    }""", [handle, content])


def fanqie_handle_typo_dialog(page, timeout_ms=4000):
    continue_texts = [
        "\u63d0\u4ea4", "\u786e\u8ba4\u63d0\u4ea4", "\u7ee7\u7eed\u63d0\u4ea4", "\u7ee7\u7eed\u53d1\u5e03",
        "\u5ffd\u7565", "\u5ffd\u7565\u5e76\u7ee7\u7eed", "\u4e0d\u4fee\u6539", "\u6682\u4e0d\u4fee\u6539",
        "\u4ecd\u7136\u53d1\u5e03", "\u786e\u8ba4\u53d1\u5e03",
    ]
    avoid_texts = ["\u4fee\u6539", "\u53bb\u4fee\u6539", "\u7acb\u5373\u4fee\u6539", "\u4e00\u952e\u4fee\u6539"]
    keywords = ["\u9519\u522b\u5b57", "\u7591\u4f3c\u9519\u522b\u5b57", "\u662f\u5426\u4fee\u6539", "\u6821\u5bf9", "\u68c0\u6d4b\u5230"]
    rounds = max(1, timeout_ms // 500)
    for _ in range(rounds):
        try:
            result = page.evaluate(r"""([keywords, continueTexts, avoidTexts]) => {
                const isVisible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const norm = (text) => (text || '').replace(/\s+/g, '').trim();
                const bodyText = norm(document.body.innerText || document.body.textContent || '');
                if (!keywords.some((keyword) => bodyText.includes(keyword))) {
                    return {found: false};
                }
                const nodes = Array.from(document.querySelectorAll('button, [role="button"], .arco-btn, .semi-button, div, span, a'))
                    .filter(isVisible)
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const text = norm(el.innerText || el.textContent || el.value || '');
                        return {el, rect, text, area: rect.width * rect.height};
                    })
                    .filter((item) => item.text && item.rect.width >= 30 && item.rect.height >= 18);
                const candidates = nodes
                    .filter((item) => continueTexts.some((word) => item.text.includes(word)))
                    .filter((item) => !avoidTexts.some((word) => item.text === word))
                    .sort((a, b) => a.area - b.area);
                const target = candidates[0];
                if (!target) return {found: true, clicked: false, reason: 'continue button not found'};
                const x = target.rect.left + target.rect.width / 2;
                const y = target.rect.top + target.rect.height / 2;
                return {found: true, clicked: false, text: target.text, x, y};
            }""", [keywords, continue_texts, avoid_texts])
            if result.get("found") and result.get("x") is not None:
                page.mouse.click(result["x"], result["y"], delay=100)
                page.wait_for_timeout(1000)
                print(f"[INFO] Fanqie typo dialog handled: {result.get('text')}")
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False



def fanqie_select_ai_yes(page, timeout_ms=4000):
    """Click the '是' radio button in the '是否使用AI' section.

    Multiple strategies to robustly find and click the AI radio:
    1. Find '是否使用AI' label text → locate nearby radio group → click first radio (是)
    2. Find .arco-radio-text with '是' content in visible elements
    3. Find the first arco-radio label in the page (是 comes before 否 in DOM)
    4. Direct Playwright clicks on .arco-radio:first-child or input[type="radio"]:first-of-type
    5. Use page.get_by_text to find '是' and click nearby radio
    """
    label_keywords = ["是否使用AI", "是否使用AI创作", "是否AI", "使用AI"]
    rounds = max(1, timeout_ms // 500)
    for attempt in range(rounds):
        try:
            # Strategy 1: JS evaluate to find AI label and nearby radio
            result = page.evaluate(r"""(labelKeywords) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                };
                const norm = (text) => (text || '').replace(/\s+/g, '');

                // Strategy A: find "是否使用AI" label, then locate nearby arco-radio-group
                const allNodes = Array.from(document.querySelectorAll(
                    'label, span, div, .card-content-line-label, .card-content-line'
                )).filter(isVisible);

                const aiLabel = allNodes.find(el => {
                    const text = norm(el.innerText || el.textContent || '');
                    return labelKeywords.some(kw => text.includes(kw) && text.length < 200);
                });

                if (aiLabel) {
                    // Walk up the DOM to find a container with radio buttons
                    let container = aiLabel;
                    for (let i = 0; i < 10; i++) {
                        if (!container || !container.parentElement) break;
                        container = container.parentElement;
                        let radioLabels = Array.from(container.querySelectorAll(
                            'label.arco-radio, .arco-radio label, .arco-radio-group label'
                        )).filter(isVisible);
                        if (radioLabels.length >= 2) {
                            // First radio is typically '是'
                            const target = radioLabels[0];
                            const rect = target.getBoundingClientRect();
                            return {
                                found: true,
                                mode: 'ai_label_container',
                                x: rect.left + rect.width / 2,
                                y: rect.top + rect.height / 2,
                            };
                        }
                    }
                    // If we found the label but no radio in containers, try sibling walk
                    let sibling = aiLabel.nextElementSibling;
                    for (let i = 0; i < 20 && sibling; i++) {
                        let radioLabels = Array.from(sibling.querySelectorAll(
                            'label.arco-radio, .arco-radio label, .arco-radio-group label'
                        )).filter(isVisible);
                        if (radioLabels.length >= 1) {
                            const target = radioLabels[0];
                            const rect = target.getBoundingClientRect();
                            return {
                                found: true,
                                mode: 'ai_label_sibling',
                                x: rect.left + rect.width / 2,
                                y: rect.top + rect.height / 2,
                            };
                        }
                        sibling = sibling.nextElementSibling;
                    }
                    return {found: false, reason: 'ai_label_found_but_no_radio_nearby'};
                }

                // Strategy B: find .arco-radio-text with '是' content
                const radioTexts = Array.from(document.querySelectorAll('.arco-radio-text'))
                    .filter(isVisible)
                    .filter(el => (el.innerText || el.textContent || '').trim() === '是');

                if (radioTexts.length > 0) {
                    const label = radioTexts[0].closest('label') || radioTexts[0].parentElement;
                    if (label) {
                        const rect = label.getBoundingClientRect();
                        return {
                            found: true,
                            mode: 'radio_text_span',
                            x: rect.left + rect.width / 2,
                            y: rect.top + rect.height / 2,
                        };
                    }
                }

                // Strategy C: find arco-radio-group and click first radio label
                const radioGroups = Array.from(document.querySelectorAll(
                    '.arco-radio-group, [role="radiogroup"]'
                )).filter(isVisible);
                for (const group of radioGroups) {
                    const groupText = norm(group.innerText || group.textContent || '');
                    // Skip AI character radio groups (人物性别, 人物类别)
                    if (groupText.includes('人物性别') || groupText.includes('人物类别') ||
                        groupText.includes('作品分类') || groupText.includes('男性') ||
                        groupText.includes('女性') || groupText.includes('未知性别') ||
                        groupText.includes('主角') || groupText.includes('反派')) {
                        continue;
                    }
                    const labels = Array.from(group.querySelectorAll(
                        'label.arco-radio, .arco-radio label'
                    )).filter(isVisible);
                    if (labels.length >= 1) {
                        // Check if the full page has "是否使用AI" text anywhere
                        const bodyText = norm(document.body.innerText || '');
                        if (bodyText.includes('是否使用AI') || bodyText.includes('使用AI')) {
                            const target = labels[0];
                            const rect = target.getBoundingClientRect();
                            return {
                                found: true,
                                mode: 'filtered_radio_group',
                                x: rect.left + rect.width / 2,
                                y: rect.top + rect.height / 2,
                            };
                        }
                    }
                }

                return {found: false, reason: 'all_strategies_failed'};
            }""", label_keywords)

            if result.get("found") and result.get("x") is not None:
                page.mouse.click(result["x"], result["y"], delay=120)
                page.wait_for_timeout(600)
                print(f"[INFO] Fanqie AI option selected: yes ({result.get('mode')})")
                return True

            # Playwright fallback strategies (outside JS evaluate)
            if result.get("reason") == "no_ai_label":
                pass  # label not yet visible, retry after wait
            else:
                # Strategy 2: Playwright get_by_text for '是' that is inside a radio
                try:
                    yes_texts = page.locator(".arco-radio-text, .arco-radio label span").filter(has_text="是")
                    yes_count = yes_texts.count()
                    for idx in range(min(yes_count, 5)):
                        candidate = yes_texts.nth(idx)
                        if candidate.is_visible():
                            candidate.click(force=True)
                            page.wait_for_timeout(600)
                            print(f"[INFO] Fanqie AI option selected: yes (playwright text '是' locator)")
                            return True
                except Exception:
                    pass

                # Strategy 3: Click first .arco-radio input[type="radio"] on the page
                try:
                    first_radio_input = page.locator('input[type="radio"]').first
                    if first_radio_input.is_visible():
                        first_radio_input.click(force=True)
                        page.wait_for_timeout(600)
                        print("[INFO] Fanqie AI option selected: yes (input[type=radio] first)")
                        return True
                except Exception:
                    pass

                # Strategy 4: Try to find '是' text and click it directly
                try:
                    yes_button = page.get_by_text("是", exact=True).first
                    if yes_button.is_visible():
                        yes_button.click(force=True)
                        page.wait_for_timeout(600)
                        print("[INFO] Fanqie AI option selected: yes (direct text click)")
                        return True
                except Exception:
                    pass

                # Strategy 5: Click first .arco-radio element
                try:
                    radio_yes = page.locator(".arco-radio").first
                    if radio_yes.is_visible():
                        radio_yes.click(force=True)
                        page.wait_for_timeout(600)
                        print("[INFO] Fanqie AI option selected: yes (playwright arco-radio fallback)")
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def fanqie_select_ai_yes_by_publish_modal(page):
    """Click the '是' radio inside the publish confirmation modal/dialog.

    Uses DOM-based selectors to find the arco-radio '是' option within
    the publish modal, bypassing fragile coordinate heuristics.
    Also tries Playwright-based approaches as fallback.
    """
    # First, try direct Playwright approach on the page (simpler and more reliable)
    try:
        # Try to find and click the '是' radio directly using Playwright locators
        # Look for label elements containing '是' text that are inside radio groups
        yes_labels = page.locator('label').filter(has_text="是")
        yes_count = yes_labels.count()
        for idx in range(min(yes_count, 10)):
            candidate = yes_labels.nth(idx)
            try:
                if candidate.is_visible():
                    candidate.click(force=True)
                    page.wait_for_timeout(500)
                    print("[INFO] Fanqie AI option selected by direct Playwright label click")
                    return True
            except Exception:
                pass
    except Exception:
        pass

    try:
        result = page.evaluate(r"""() => {
            const visible = (el) => {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden'
                    && rect.width > 0 && rect.height > 0;
            };
            const norm = (text) => (text || '').replace(/\s+/g, '').trim();

            // Find the modal containing '发布设置' (publish settings) or '确认发布' text
            const modalSelectors = [
                '.arco-modal', '.arco-modal-content', '.arco-modal-body',
                '[class*="modal"]', '[class*="dialog"]', '[role="dialog"]',
                '.arco-drawer', '.arco-drawer-wrapper',
            ];
            const modals = Array.from(document.querySelectorAll(modalSelectors.join(',')))
                .filter(visible).filter(el => {
                    const text = norm(el.innerText || el.textContent || '');
                    return text.includes('发布设置') || text.includes('确认发布')
                        || text.includes('是否使用AI');
                });

            let searchRoot = document.body;
            if (modals.length > 0) {
                searchRoot = modals.sort((a, b) => {
                    const aRect = a.getBoundingClientRect();
                    const bRect = b.getBoundingClientRect();
                    return (bRect.width * bRect.height) - (aRect.width * aRect.height);
                })[0];
            }

            // Strategy 1: Find .arco-radio-text with '是' content
            const radioTexts = Array.from(searchRoot.querySelectorAll('.arco-radio-text'))
                .filter(visible)
                .filter(el => (el.innerText || el.textContent || '').trim() === '是');

            if (radioTexts.length > 0) {
                const label = radioTexts[0].closest('label.arco-radio') || radioTexts[0].parentElement;
                if (label && visible(label)) {
                    const rect = label.getBoundingClientRect();
                    return {
                        found: true,
                        mode: 'radio_text',
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                    };
                }
            }

            // Strategy 2: Find .arco-radio label, first one whose text contains '是'
            const radioLabels = Array.from(searchRoot.querySelectorAll(
                'label.arco-radio, .arco-radio label'
            )).filter(visible);
            for (const label of radioLabels) {
                const text = norm(label.innerText || label.textContent || '');
                if (text.startsWith('是') || text === '是') {
                    const rect = label.getBoundingClientRect();
                    return {
                        found: true,
                        mode: 'first_radio_label_with_yes',
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                    };
                }
            }
            // Fallback: first radio label
            if (radioLabels.length >= 1) {
                const target = radioLabels[0];
                const rect = target.getBoundingClientRect();
                return {
                    found: true,
                    mode: 'first_radio_label',
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2,
                };
            }

            // Strategy 3: Find '是否使用AI' and click radio nearby
            const nodes = Array.from(searchRoot.querySelectorAll('*')).filter(visible);
            const aiLabel = nodes.find(el => {
                const text = norm(el.innerText || el.textContent || '');
                return text.includes('是否使用AI') && text.length < 200;
            });
            if (aiLabel) {
                // Walk siblings and parents for radio
                let elem = aiLabel;
                for (let i = 0; i < 10 && elem; i++) {
                    const radio = elem.querySelector('.arco-radio, label.arco-radio');
                    if (radio && visible(radio)) {
                        const rect = radio.getBoundingClientRect();
                        if (rect.width > 0) {
                            return {
                                found: true,
                                mode: 'ai_label_sibling',
                                x: rect.left + rect.width / 2,
                                y: rect.top + rect.height / 2,
                            };
                        }
                    }
                    elem = elem.parentElement;
                }
            }

            // Strategy 4: Find arco-radio-group that's NOT character/gender related
            const groups = Array.from(searchRoot.querySelectorAll(
                '.arco-radio-group, [role="radiogroup"]'
            )).filter(visible);
            for (const group of groups) {
                const text = norm(group.innerText || group.textContent || '');
                if (text.includes('人物性别') || text.includes('人物类别') ||
                    text.includes('作品分类') || text.includes('男性') ||
                    text.includes('女性') || text.includes('未知性别') ||
                    text.includes('主角') || text.includes('反派') ||
                    text.includes('新建角色') || text.includes('小说角色')) {
                    continue;
                }
                const labels = Array.from(group.querySelectorAll(
                    'label.arco-radio, .arco-radio label'
                )).filter(visible);
                if (labels.length >= 2) {
                    const target = labels[0];
                    const rect = target.getBoundingClientRect();
                    return {
                        found: true,
                        mode: 'filtered_group',
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                    };
                }
            }

            return {found: false, reason: 'all_modal_strategies_failed'};
        }""")
        if result.get("found") and result.get("x") is not None:
            page.mouse.click(result["x"], result["y"], delay=120)
            page.wait_for_timeout(500)
            print(f"[INFO] Fanqie AI option selected by publish modal ({result.get('mode')})")
            return True
        else:
            print(f"[DEBUG] fanqie_select_ai_yes_by_publish_modal failed: {result.get('reason', 'unknown')}")
    except Exception as e:
        print(f"[DEBUG] fanqie_select_ai_yes_by_publish_modal exception: {e}")
    return False

def fanqie_handle_publish_modal(page):
    """Handle the Fanqie Publish Settings modal that appears after clicking '下一步'.

    This modal contains:
    - '是否使用AI' radio group (是/否) — we select '是'
    - '定时发布' toggle
    - [取消] [确认发布] buttons

    IMPORTANT: This must be called BEFORE dismiss_popups because the modal's
    '取消' button matches the dismiss_texts and dismiss_popups will close
    the entire modal, losing the AI radio forever.
    """
    # First, check if the publish settings modal is present
    modal_text = page.evaluate(r"""() => {
        const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0;
        };
        // Look for arco-modal with '发布设置' title
        const modals = Array.from(document.querySelectorAll('.arco-modal-wrapper, .arco-modal'))
            .filter(isVisible);
        for (const modal of modals) {
            const text = (modal.innerText || modal.textContent || '');
            if (text.includes('发布设置') && text.includes('是否使用AI')) {
                const title = modal.querySelector('.arco-modal-title');
                const confirmBtn = Array.from(modal.querySelectorAll('button'))
                    .find(b => (b.innerText || b.textContent || '').includes('确认发布'));
                if (confirmBtn) {
                    const confirmRect = confirmBtn.getBoundingClientRect();
                    // Find the '是' radio
                    const yesLabels = Array.from(modal.querySelectorAll('label.arco-radio'))
                        .filter(l => {
                            const t = (l.innerText || l.textContent || '').trim();
                            return t === '是' || t.startsWith('是');
                        });
                    let yesRect = null;
                    if (yesLabels.length > 0) {
                        const yr = yesLabels[0].getBoundingClientRect();
                        yesRect = { x: yr.left + yr.width/2, y: yr.top + yr.height/2, w: yr.width, h: yr.height };
                    }
                    return {
                        found: true,
                        confirmX: confirmRect.left + confirmRect.width / 2,
                        confirmY: confirmRect.top + confirmRect.height / 2,
                        yesRect: yesRect,
                    };
                }
            }
        }
        return { found: false };
    }""")

    if not modal_text.get("found"):
        return False

    print("[INFO] Fanqie publish settings modal detected. Selecting AI=是...")

    # Step 1: Select AI=是
    if not fanqie_select_ai_yes_by_publish_modal(page):
        fanqie_select_ai_yes(page)

    # Step 2: Click '确认发布' (Confirm Publish)
    try:
        page.mouse.click(modal_text["confirmX"], modal_text["confirmY"], delay=120)
        page.wait_for_timeout(2000)
        print("[INFO] Fanqie publish modal: clicked 确认发布")
        return True
    except Exception as e:
        print(f"[DEBUG] Fanqie publish modal confirm click failed: {e}")
        return True  # AI was selected, but confirm click threw — let caller handle


def fanqie_handle_content_check_dialog(page, timeout_ms=4000):
    keywords = ["\u8bf7\u9009\u62e9\u5185\u5bb9\u68c0\u6d4b\u65b9\u5f0f", "\u5168\u9762\u68c0\u6d4b", "\u57fa\u7840\u68c0\u6d4b"]
    preferred_texts = ["\u57fa\u7840\u68c0\u6d4b", "\u4e0d\u9650\u6b21\u6570"]
    continue_texts = ["\u786e\u5b9a", "\u786e\u8ba4", "\u63d0\u4ea4", "\u7ee7\u7eed", "\u4e0b\u4e00\u6b65"]
    rounds = max(1, timeout_ms // 500)
    selected = False
    for _ in range(rounds):
        try:
            result = page.evaluate(r"""([keywords, preferredTexts, continueTexts, selected]) => {
                const isVisible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const norm = (text) => (text || '').replace(/\s+/g, '').trim();
                const bodyText = norm(document.body.innerText || document.body.textContent || '');
                if (!keywords.some((keyword) => bodyText.includes(keyword))) return {found: false};
                const nodes = Array.from(document.querySelectorAll('button, [role="button"], label, div, span, a'))
                    .filter(isVisible)
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const text = norm(el.innerText || el.textContent || el.value || '');
                        return {el, rect, text, area: rect.width * rect.height};
                    })
                    .filter((item) => item.text && item.rect.width >= 20 && item.rect.height >= 16);
                const chooseTarget = nodes
                    .filter((item) => preferredTexts.some((word) => item.text.includes(word)))
                    .sort((a, b) => a.area - b.area)[0];
                if (!selected && chooseTarget) {
                    return {
                        found: true,
                        action: 'select',
                        text: chooseTarget.text,
                        x: chooseTarget.rect.left + chooseTarget.rect.width / 2,
                        y: chooseTarget.rect.top + chooseTarget.rect.height / 2,
                    };
                }
                const continueTarget = nodes
                    .filter((item) => continueTexts.some((word) => item.text === word || item.text.includes(word)))
                    .sort((a, b) => a.area - b.area)[0];
                if (continueTarget) {
                    return {
                        found: true,
                        action: 'continue',
                        text: continueTarget.text,
                        x: continueTarget.rect.left + continueTarget.rect.width / 2,
                        y: continueTarget.rect.top + continueTarget.rect.height / 2,
                    };
                }
                return {found: true, action: 'wait'};
            }""", [keywords, preferred_texts, continue_texts, selected])
            if result.get("found") and result.get("x") is not None:
                page.mouse.click(result["x"], result["y"], delay=100)
                page.wait_for_timeout(800)
                print(f"[INFO] Fanqie content check dialog handled: {result.get('action')} {result.get('text')}")
                if result.get("action") == "select":
                    selected = True
                    continue
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False

def verify_publish_result(page, platform, chapter_title=None, timeout_ms=15000):
    if platform.get("key") == "faloo":
        return verify_faloo_publish_result(page, chapter_title=chapter_title, timeout_ms=timeout_ms)

    success_keywords = [
        "\u53d1\u5e03\u6210\u529f", "\u53d1\u8868\u6210\u529f", "\u63d0\u4ea4\u6210\u529f",
        "\u5df2\u53d1\u5e03", "\u5ba1\u6838\u4e2d", "\u53d1\u5e03\u5ba1\u6838",
    ]
    failure_keywords = [
        "\u53d1\u5e03\u5931\u8d25", "\u63d0\u4ea4\u5931\u8d25", "\u4fdd\u5b58\u5931\u8d25",
        "\u4e0d\u80fd\u4e3a\u7a7a", "\u8bf7\u8f93\u5165", "\u8bf7\u586b\u5199", "\u5b57\u6570\u4e0d\u8db3",
        "\u654f\u611f\u8bcd", "\u8fdd\u89c4", "\u9519\u8bef", "\u5f02\u5e38", "\u8bf7\u5148",
    ]
    # Body-wide scan keywords: exclude words that commonly appear in
    # static page content (e.g. "\u654f\u611f\u8bcd\u68c0\u6d4b" feature sidebar, "\u8fdd\u89c4" in
    # content guidelines on Qidian).  Only include words that would
    # appear in a genuine error message visible to the user.
    body_failure_keywords = [
        "\u53d1\u5e03\u5931\u8d25", "\u63d0\u4ea4\u5931\u8d25", "\u4fdd\u5b58\u5931\u8d25",
        "\u4e0d\u80fd\u4e3a\u7a7a", "\u8bf7\u8f93\u5165", "\u8bf7\u586b\u5199", "\u5b57\u6570\u4e0d\u8db3",
        "\u9519\u8bef", "\u5f02\u5e38", "\u8bf7\u5148",
    ]
    rounds = max(1, timeout_ms // 1000)
    for _ in range(rounds):
        try:
            message_text = page.evaluate(r"""() => {
                const selectors = [
                    '.ui-dialog', '.ui-popup', '.ui-toast', '.toast', '.message', '.msg', '.tips', '.tip',
                    '.el-message', '.ant-message', '.modal', '.dialog', '[role=alert]', '[class*=toast]',
                    '[class*=message]', '[class*=notice]', '[class*=error]', '[class*=success]'
                ];
                return selectors
                    .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
                    .filter((el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    })
                    .map((el) => el.innerText || el.textContent || '')
                    .filter(Boolean)
                    .join('\n');
            }""")
        except Exception:
            message_text = ""
        detect_web_security_block(page, platform, "publish_blocked")
        compact_message = re.sub(r"\s+", "", message_text)
        matched_failures = [word for word in failure_keywords if word in compact_message]
        matched_successes = [word for word in success_keywords if word in compact_message]
        if matched_failures:
            return False, f"failure text detected: {','.join(matched_failures)}"
        if matched_successes:
            return True, f"success text detected: {','.join(matched_successes)}"
        try:
            url = page.url
            if platform.get("key") == "qimao" and "book-manage/manage" in url:
                return True, f"qimao returned to book manage page after publish: {url}"
            if platform.get("key") == "fanqie" and "book-manage" in url and "book-upload" not in url:
                return True, f"fanqie returned to book manage page after publish: {url}"
            # Qidian: after publish redirects to chapter list with "/chapter/" in the URL
            if platform.get("key") == "qidian" and ("/chapter/" in url or "/portal/book/" in url):
                return True, f"qidian returned to chapter list after publish: {url}"
            # Migu: after publish, success toast typically appears or page
            # redirects to draft/chapter list. The editor URL contains
            # /detail/draft or /detail/write; a redirect to /detail/count
            # (book manage) indicates publish success.
            if platform.get("key") == "migu":
                if "/detail/count" in url:
                    body_text = page.locator("body").inner_text(timeout=1000)
                    compact_body = re.sub(r"\s+", "", body_text)
                    if any(kw in compact_body for kw in ["已发布章节", "草稿箱", "定时发布"]):
                        return True, f"migu returned to book manage after publish: {url}"
            if any(token in url for token in ["chapter", "draft", "publish", "editor"]):
                body_text = page.locator("body").inner_text(timeout=1000)
                compact_body = re.sub(r"\s+", "", body_text)
                body_failures = [word for word in body_failure_keywords if word in compact_body]
                if body_failures:
                    return False, f"failure body text detected: {','.join(body_failures)}"
        except Exception:
            pass
        page.wait_for_timeout(1000)
    if platform.get("key") == "qimao" and "book-manage/manage" in page.url:
        return True, f"qimao returned to book manage page after publish: {page.url}"
    if platform.get("key") == "fanqie" and "book-manage" in page.url and "book-upload" not in page.url:
        return True, f"fanqie returned to book manage page after publish: {page.url}"
    if platform.get("key") == "qidian" and ("/chapter/" in page.url or "/portal/book/" in page.url):
        return True, f"qidian returned to chapter list after publish: {page.url}"
    if platform.get("key") == "migu":
        if "/detail/count" in page.url:
            try:
                body_text = page.locator("body").inner_text(timeout=1000)
                compact_body = re.sub(r"\s+", "", body_text)
                if any(kw in compact_body for kw in ["已发布章节", "草稿箱", "定时发布"]):
                    return True, f"migu returned to book manage after publish: {page.url}"
            except Exception:
                pass
    return False, f"{platform['key']} publish result was not verified"


def verify_faloo_publish_result(page, chapter_title=None, timeout_ms=12000):
    success_keywords = [
        "\u53d1\u5e03\u6210\u529f", "\u53d1\u8868\u6210\u529f", "\u63d0\u4ea4\u6210\u529f",
        "\u4fdd\u5b58\u6210\u529f", "\u66f4\u65b0\u6210\u529f", "\u7ae0\u8282\u5df2\u53d1\u5e03",
        "\u64cd\u4f5c\u6210\u529f",
    ]
    failure_keywords = [
        "\u4e0d\u80fd\u4e3a\u7a7a", "\u8bf7\u586b\u5199", "\u672a\u586b\u5199", "\u9a8c\u8bc1\u7801",
        "\u9519\u8bef", "\u5931\u8d25", "\u8bf7\u9009\u62e9", "\u8bf7\u5148",
    ]
    rounds = max(1, timeout_ms // 1000)
    for _ in range(rounds):
        if chapter_title:
            normalized_title = re.sub(r"\s+", "", chapter_title)
            try:
                chapter_items = page.locator("#volumeList dd, #nodeList dd")
                count = chapter_items.count()
                for idx in range(count):
                    item_text = re.sub(r"\s+", "", chapter_items.nth(idx).inner_text(timeout=1000))
                    if normalized_title and normalized_title in item_text:
                        return True, f"chapter appeared in Faloo list: {chapter_title}"
            except Exception:
                pass

        try:
            message_text = page.evaluate(r"""() => {
                const selectors = ['.autoSaveContentTip', '.layui-layer-content', '.dialog', '.error', '.tips', '.tip', '.msg'];
                return selectors
                    .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
                    .map((el) => el.innerText || el.textContent || '')
                    .filter(Boolean)
                    .join('\n');
            }""")
        except Exception:
            message_text = ""
        detect_web_security_block(page, platform, "publish_blocked")
        compact_message = re.sub(r"\s+", "", message_text)
        matched_failures = [word for word in failure_keywords if word in compact_message]
        matched_successes = [word for word in success_keywords if word in compact_message]
        if matched_successes and not matched_failures:
            return True, f"success text detected: {','.join(matched_successes)}"
        if matched_failures:
            return False, f"failure text detected: {','.join(matched_failures)}"
        page.wait_for_timeout(1000)
    return False, "publish result was not verified"


def _migu_handle_publish_confirm(page, timeout_ms=5000):
    """Handle Migu's confirmation dialogs after clicking the publish span.

    The publish span click opens an Element UI message-box ("本章xxx字,确定发布？")
    with buttons "取 消" and "确 定".  After confirming that, a "定时发布"
    (timed-publish) dialog may appear with "确 定" and "取 消".
    """
    deadline = timeout_ms // 500
    for _ in range(deadline):
        # 1) Main confirmation: el-message-box__wrapper with title "发布"
        try:
            mb = page.locator('.el-message-box__wrapper:not([style*="display: none"])').first
            if mb.is_visible():
                label = ""
                try:
                    label = mb.locator('.el-message-box__title').inner_text(timeout=500).strip()
                except Exception:
                    pass
                primary_btn = mb.locator('button.el-button--primary').first
                if primary_btn.is_visible() and primary_btn.is_enabled():
                    primary_btn.click(force=True)
                    print(f"[MIGU] Confirmed message-box '{label}'")
                    page.wait_for_timeout(2000)
                    continue
        except Exception:
            pass

        # 2) Timed-publish dialog: el-dialog with title "定时发布"
        try:
            td = page.locator('.el-dialog__wrapper:not([style*="display: none"])').first
            if td.is_visible():
                label = ""
                try:
                    label = td.locator('.el-dialog__title').inner_text(timeout=500).strip()
                except Exception:
                    pass
                if "定时发布" in label:
                    # Click the primary button "确 定"
                    primary_btn = td.locator('button.el-button--primary').first
                    if primary_btn.is_visible() and primary_btn.is_enabled():
                        primary_btn.click(force=True)
                        print(f"[MIGU] Confirmed timed-publish dialog")
                        page.wait_for_timeout(2000)
                        continue
                    # If primary not found, close the dialog with default
                    default_btn = td.locator('button.el-button--default').first
                    if default_btn.is_visible() and default_btn.is_enabled():
                        default_btn.click(force=True)
                        print(f"[MIGU] Closed timed-publish dialog with default button")
                        page.wait_for_timeout(1000)
                        continue
                # Other dialogs: close them
                close_btn = td.locator('.el-dialog__headerbtn').first
                if close_btn.is_visible():
                    close_btn.click(force=True)
                    page.wait_for_timeout(1000)
                    continue
        except Exception:
            pass

        # 3) Generic dialog with "确 定" button (Element UI style)
        try:
            for wrapper_sel in ['.el-dialog__wrapper', '.el-message-box__wrapper']:
                wrapper = page.locator(f'{wrapper_sel}:not([style*="display: none"])').first
                if wrapper.is_visible():
                    for btn_text in ["确 定", "确定"]:
                        btn = wrapper.get_by_text(btn_text, exact=True).first
                        try:
                            if btn.is_visible() and btn.is_enabled():
                                btn.click(force=True)
                                page.wait_for_timeout(2000)
                                break
                        except Exception:
                            pass
        except Exception:
            pass

        # No dialog found — exit loop
        break


def publish_current_editor(page, platform, no_prompt):
    if platform.get("key") == "faloo":
        button = None
        for text in ["\u6dfb\u52a0\u5c0f\u8bf4\u7ae0\u8282", "\u4fee\u6539\u5c0f\u8bf4\u7ae0\u8282", "\u53d1\u5e03\u5c0f\u8bf4\u7ae0\u8282", "\u63d0\u4ea4\u5c0f\u8bf4\u7ae0\u8282"]:
            button = first_visible_text(page, [text], prefer_button=True, exact=False, last=True)
            if button:
                break
        if not button:
            button = first_visible_text(page, platform["next_step_texts"], prefer_button=True, exact=False, last=True)
        if not button:
            button = first_visible_text(page, platform["final_publish_texts"], prefer_button=True, exact=False, last=True)
        if button:
            before_url = page.url
            button.click(force=True)
            page.wait_for_timeout(3000)
            for text in platform["final_publish_texts"] + platform["popup_continue_texts"]:
                try:
                    confirm = first_visible_text(page, [text], prefer_button=True, exact=False, last=True)
                    if confirm and confirm.is_enabled():
                        confirm.click(force=True)
                        page.wait_for_timeout(1500)
                except Exception:
                    pass
            verified, reason = verify_faloo_publish_result(page, chapter_title=platform.get("current_chapter_title"))
            print(f"[INFO] Faloo publish verification: {reason}; before_url={before_url}; after_url={page.url}")
            if verified:
                return "published"
            raise RuntimeError(f"Faloo publish was not verified: {reason}")
        if no_prompt:
            raise RuntimeError("Faloo publish/submit button not found")
        input("Manually finish Faloo publish in browser, then press Enter here: ")
        verified, reason = verify_faloo_publish_result(page, chapter_title=platform.get("current_chapter_title"))
        print(f"[INFO] Faloo manual publish verification: {reason}")
        if verified:
            return "published"
        raise RuntimeError(f"Faloo manual publish was not verified: {reason}")

    # --- Migu: click the publish span and handle confirmation dialogs ---
    if platform.get("key") == "migu":
        migu_publish_span = page.locator('span.xiugai').last
        try:
            if migu_publish_span.is_visible() and migu_publish_span.is_enabled():
                migu_publish_span.click(force=True)
                page.wait_for_timeout(2000)
                _migu_handle_publish_confirm(page)
                verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
                print(f"[INFO] migu publish verification: {reason}")
                if verified:
                    return "published"
        except Exception as exc:
            print(f"[WARN] Migu span.xiugai click failed: {exc}")
        # If the span approach didn't work, also try searching by text
        migu_btn = first_visible_text(page, ["发布"], prefer_button=False, exact=True)
        if migu_btn:
            try:
                migu_btn.click(force=True)
                page.wait_for_timeout(2000)
                _migu_handle_publish_confirm(page)
                verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
                print(f"[INFO] migu publish verification (fallback): {reason}")
                if verified:
                    return "published"
            except Exception as exc:
                print(f"[WARN] Migu text-based publish click failed: {exc}")

    next_button = None
    if platform.get("key") == "fanqie":
        for selector in ["button.auto-editor-next", ".auto-editor-next", "button.publish-button"]:
            try:
                candidate = page.locator(selector).first
                if candidate.is_visible() and candidate.is_enabled():
                    next_button = candidate
                    break
            except Exception:
                pass
    if not next_button:
        try:
            header_buttons = page.locator("#guideHeaderBtns button")
            for idx in range(header_buttons.count()):
                btn = header_buttons.nth(idx)
                try:
                    if btn.is_visible() and "??" in btn.inner_text(timeout=1000):
                        next_button = btn
                        break
                except Exception:
                    pass
        except Exception:
            pass
    if not next_button:
        next_button = first_visible_text(page, platform["next_step_texts"], prefer_button=True, last=True)
    if next_button:
        next_button.click(force=True)
        if platform.get("key") == "qimao":
            qimao_skip_important_notice(page)
        if platform.get("key") == "fanqie":
            fanqie_handle_typo_dialog(page)
            fanqie_handle_content_check_dialog(page)
        page.wait_for_timeout(2000)
        # Qidian: after clicking "发布", the page may publish and redirect
        # directly to the chapter list.  Check before entering the loop.
        if platform.get("key") == "qidian":
            url = page.url
            # Publish redirects away from the editor; URL no longer has
            # /create, /edit, or /draft segments.
            if not any(t in url for t in ["/create", "/edit", "/draft"]) and any(
                t in url for t in ["/chapter", "/portal/book"]
            ):
                verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
                if verified:
                    print(f"[INFO] qidian publish (direct to chapter list): {reason}")
                    return "published"
    else:
        draft_button = first_visible_text(page, platform["save_draft_texts"], prefer_button=True, exact=False)
        if draft_button:
            draft_button.click(force=True)
            return "draft"
        raise RuntimeError("next/publish button not found")

    loop_count = 0
    for _ in range(15):
        if platform.get("key") == "fanqie":
            fanqie_handle_typo_dialog(page, timeout_ms=1000)
            fanqie_handle_content_check_dialog(page, timeout_ms=1000)
            # Handle the "发布设置" (Publish Settings) modal BEFORE
            # dismiss_popups. The modal's "取消" (Cancel) button matches
            # dismiss_texts, and dismiss_popups would destroy the modal
            # along with the AI radio. fanqie_handle_publish_modal selects
            # AI=是 and clicks 确认发布 — which IS the final publish action.
            # After that, verify the result immediately.
            if fanqie_handle_publish_modal(page):
                fanqie_handle_typo_dialog(page, timeout_ms=1000)
                fanqie_handle_content_check_dialog(page, timeout_ms=1000)
                page.wait_for_timeout(2000)
                verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
                print(f"[INFO] fanqie publish verification: {reason}")
                if verified:
                    return "published"
                # Modal submitted but verification failed — maybe another
                # step needed; continue the main loop to handle it.
            # After modal handling (or no modal), handle follow-up dialogs
            fanqie_handle_typo_dialog(page, timeout_ms=1000)
            fanqie_handle_content_check_dialog(page, timeout_ms=1000)

        # CRITICAL: check for final publish button BEFORE dismiss_popups.
        # On Qidian and similar platforms, the confirmation dialog has a
        # "取消" button that matches dismiss_texts — if we dismiss first,
        # the dialog closes and publish is cancelled.
        if platform.get("key") != "fanqie":
            final_button = first_visible_text(page, platform["final_publish_texts"], prefer_button=True)
            if final_button and final_button.is_enabled():
                before_url = page.url
                final_button.click(force=True)
                if platform.get("key") == "qimao":
                    qimao_skip_important_notice(page)
                page.wait_for_timeout(2000)
                verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
                print(f"[INFO] {platform['key']} publish verification: {reason}; before_url={before_url}; after_url={page.url}")
                if verified:
                    return "published"
                # Verification failed but button was clicked — continue loop
                # in case another step is needed (e.g. popup to dismiss).
                page.wait_for_timeout(1000)
                continue

        dismiss_popups(page, platform["dismiss_texts"])
        for text in platform["popup_continue_texts"]:
            try:
                button = first_visible_text(page, [text], prefer_button=True)
                if button and button.is_enabled():
                    button.click(force=True)
                    page.wait_for_timeout(1000)
            except Exception:
                pass
        # For non-fanqie platforms: handle AI radio after dismiss_popups
        if platform.get("key") != "fanqie":
            try:
                ai_no = page.get_by_text("?", exact=True).first
                if ai_no.is_visible():
                    ai_no.click(force=True)
            except Exception:
                pass
        final_button = first_visible_text(page, platform["final_publish_texts"], prefer_button=True)
        if final_button and final_button.is_enabled():
            before_url = page.url
            if platform.get("key") == "fanqie":
                # Ensure "是否使用AI" is set to "是" before clicking confirm
                if not fanqie_select_ai_yes_by_publish_modal(page):
                    fanqie_select_ai_yes(page)
            final_button.click(force=True)
            if platform.get("key") == "qimao":
                qimao_skip_important_notice(page)
            page.wait_for_timeout(2000)
            verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
            print(f"[INFO] {platform['key']} publish verification: {reason}; before_url={before_url}; after_url={page.url}")
            if verified:
                return "published"
            raise RuntimeError(f"{platform['key']} publish was not verified: {reason}")
        page.wait_for_timeout(1000)
        loop_count += 1

    if no_prompt:
        raise RuntimeError("final publish button not found")
    input("Manually finish final publish in browser, then press Enter here: ")
    verified, reason = verify_publish_result(page, platform, chapter_title=platform.get("current_chapter_title"))
    print(f"[INFO] {platform['key']} manual publish verification: {reason}")
    if verified:
        return "published"
    raise RuntimeError(f"{platform['key']} manual publish was not verified: {reason}")


def _fanqie_goto_new_chapter(page, platform, button_locator):
    """For Fanqie: navigate directly to the new-chapter URL instead of clicking
    the button wrapped in <a target="_blank">, which gets blocked by the popup
    blocker when using click(force=True). Falls back to force-click for others."""
    if platform.get("key") != "fanqie":
        button_locator.click(force=True)
        return
    href = page.evaluate("""() => {
        const btn = [...document.querySelectorAll('a[target="_blank"]')].find(
            a => a.querySelector('button') && a.textContent.includes('新建章节')
        );
        return btn ? btn.getAttribute('href') : null;
    }""")
    if href:
        from urllib.parse import urljoin
        page.goto(urljoin(page.url, href), wait_until="domcontentloaded")
    else:
        button_locator.click(force=True)


def publish_chapter(context, page, platform, book_name, file_path, archive_dir, no_prompt):
    chapter_num, chapter_title, content = parse_chapter(file_path)
    print(f"Publishing: chapter {chapter_num} {chapter_title} ({os.path.basename(file_path)})")
    original_pages = len(context.pages)
    manager_page = open_chapter_manager(page, platform, book_name)
    editor_page = context.pages[-1] if len(context.pages) > original_pages else manager_page
    if not wait_for_editor_or_content(editor_page, platform, timeout_ms=30000):
        print("[WARN] Editor did not become ready within timeout")
    if platform.get("key") == "faloo" and not wait_for_faloo_chapter_form(editor_page, timeout_ms=30000):
        raise RuntimeError("Faloo chapter form did not become ready")

    # On platforms like Qidian, the editor may be "ready" because a draft
    # is already open.  If a "\u65b0\u5efa\u7ae0\u8282" button is still visible we must click
    # it first \u2014 otherwise we would fill and re-save the draft content
    # instead of publishing a new chapter.
    new_button = first_visible_text(editor_page, platform["new_chapter_texts"], prefer_button=True)
    if platform.get("key") == "fanqie":
        # Always click "新建章节" to enter a fresh editor
        if not new_button:
            new_button = first_visible_text(editor_page, platform["new_chapter_texts"], prefer_button=True)
        if not new_button:
            raise RuntimeError("new chapter entry not found")
        _fanqie_goto_new_chapter(editor_page, platform, new_button)
    elif is_editor_ready(editor_page, platform) and not new_button:
        print("Editor is already open; filling current blank editor.")
    else:
        row = editor_page.locator("tr, li, .chapter-item").filter(has_text=re.compile(r"\u7b2c\s*" + re.escape(chapter_num) + r"\s*\u7ae0")).first
        try:
            if chapter_num and row.is_visible():
                row.click(force=True)
            else:
                if not new_button:
                    new_button = first_visible_text(editor_page, platform["new_chapter_texts"], prefer_button=True)
                if not new_button:
                    raise RuntimeError("new chapter entry not found")
                _fanqie_goto_new_chapter(editor_page, platform, new_button)
        except Exception:
            if not new_button:
                new_button = first_visible_text(editor_page, platform["new_chapter_texts"], prefer_button=True)
            if not new_button:
                raise
            _fanqie_goto_new_chapter(editor_page, platform, new_button)

    editor_page.wait_for_timeout(4000)
    if len(context.pages) > original_pages:
        editor_page = context.pages[-1]
    dismiss_popups(editor_page, platform["dismiss_texts"])
    if platform.get("key") == "faloo" and not wait_for_faloo_chapter_form(editor_page, timeout_ms=20000):
        raise RuntimeError("Faloo chapter form disappeared before fill")
    fill_editor(editor_page, platform, chapter_num, chapter_title, content)
    editor_page.wait_for_timeout(1000)
    platform["current_chapter_title"] = chapter_title
    filename = os.path.basename(file_path)
    try:
        try:
            result = publish_current_editor(editor_page, platform, no_prompt)
        finally:
            platform.pop("current_chapter_title", None)
        if result not in ("published", "draft"):
            raise RuntimeError(f"publish result is not archivable: {result}")
        archive_uploaded_file(file_path, archive_dir)
        log_result(platform["key"], filename, True)
    except Exception as exc:
        log_result(platform["key"], filename, False, str(exc))
        raise
    if editor_page != page:
        try:
            editor_page.close()
        except Exception:
            pass
    return result


def main(platform_key=DEFAULT_PLATFORM, book_name=None, publish_count=None, volume_num=None, no_prompt=False, headless=False):
    platform = get_platform(platform_key)
    state_file = resolve_existing_state_file(platform)
    if not state_file:
        print(f"[ERROR] Login state not found: {platform['state_file']}. Run: py login.py {platform['key']}")
        return 1

    source_dir, using_legacy_source = resolve_platform_source_dir(platform)
    archive_root = platform_archive_dir(platform) if not using_legacy_source else UPLOADED_DIR

    root_txt = glob.glob(os.path.join(source_dir, "*.txt"))
    if root_txt:
        print(f"[ERROR] Put txt files under {source_dir}/<book-name>/ instead of {source_dir}/ root.")
        return 1

    books = scan_books(source_dir)
    if not books:
        print(f"[INFO] No pending chapter files found in {source_dir}.")
        print(f"[INFO] Expected layout: {source_dir}/<book-name>/*.txt")
        return 0

    try:
        selected_book, _, txt_files = choose_book(books, book_name, no_prompt)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    if publish_count is None and not no_prompt:
        raw_count = input(f">>> Chapters to publish (1-{len(txt_files)}, Enter for all): ").strip()
        publish_count = len(txt_files) if raw_count == "" else int(raw_count)
    if publish_count is None:
        publish_count = len(txt_files)
    publish_count = max(1, min(int(publish_count), len(txt_files)))
    txt_files = txt_files[:publish_count]

    archive_dir = os.path.join(archive_root, selected_book)
    if volume_num:
        archive_dir = os.path.join(archive_dir, f"volume_{volume_num}")

    print(f"Platform: {platform.get('product_name', platform['key'])}")
    print(f"Source: {source_dir}")
    print(f"Archive: {archive_dir}")
    print(f"Book: {selected_book}")
    print(f"Count: {len(txt_files)}")
    print(f"Headless: {headless}")
    print(f"No prompt: {no_prompt}")

    success_count = 0
    with sync_playwright() as p:
        browser = launch_anti_detect_browser(p, headless=headless)
        context = create_anti_detect_context(browser, storage_state=state_file)
        page = context.new_page()
        attach_dialog_handler(page)
        try:
            for file_path in txt_files:
                publish_chapter(context, page, platform, selected_book, file_path, archive_dir, no_prompt)
                success_count += 1
                page.wait_for_timeout(1000)
        except Exception as exc:
            print(f"[ERROR] Publish run stopped: {exc}")
            if not no_prompt:
                input("Inspect browser, then press Enter to close: ")
        finally:
            if not no_prompt:
                input(">>> Press Enter to close browser: ")
            browser.close()

    print(f"Publish run finished. Success: {success_count}/{len(txt_files)}")
    return 0 if success_count == len(txt_files) else 1


def parse_args():
    parser = argparse.ArgumentParser(description="Publish chapters to a writer backend.")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="Platform key, e.g. qidian, fanqie, faloo, or qimao.")
    parser.add_argument("--book", help="Book folder name to publish. Defaults to first book in --no-prompt mode.")
    parser.add_argument("--count", type=int, help="Number of chapters to publish. Defaults to all.")
    parser.add_argument("--volume", type=int, help="Archive volume number. Defaults to no volume subfolder.")
    parser.add_argument("--no-prompt", action="store_true", help="Never wait for console input; fail fast on manual steps.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode for scheduled tasks.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(
        platform_key=args.platform,
        book_name=args.book,
        publish_count=args.count,
        volume_num=args.volume,
        no_prompt=args.no_prompt,
        headless=args.headless,
    ))
