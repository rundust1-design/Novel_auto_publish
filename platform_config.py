DEFAULT_PLATFORM = "qidian"

COMMON_TEXTS = {
    "chapter_manage_texts": [
        "章节管理", "管理章节", "作品管理",
        "管理作品", "目录管理", "章节目录",
        "进入作品", "继续写作", "去写作",
        "写作", "管理", "编辑",
    ],
    "new_chapter_texts": [
        "新建章节", "新增章节", "创建章节",
        "写新章节", "发布新章节", "新建",
    ],
    "next_step_texts": ["下一步", "发布", "提交", "保存并发布"],
    "final_publish_texts": [
        "确认发布", "立即发布", "发布章节",
        "提交发布", "确定发布", "发布",
    ],
    "save_draft_texts": ["存草稿", "保存草稿", "保存", "暂存"],
    "dismiss_texts": ["我知道了", "知道了", "关闭", "跳过", "完成", "取消"],
    "popup_continue_texts": ["提交", "继续发布", "我知道了", "确认", "确定", "继续", "发布"],
    "title_placeholders": ["请输入标题", "请输入章节名", "章节标题", "标题"],
    "body_selectors": [".ql-editor", ".ProseMirror", '[contenteditable="true"]', "textarea"],
}

PLATFORMS = {
    "migu": {
        "key": "migu",
        "name": "咪咕文学",
        "short_name": "咪咕",
        "product_name": "Migu Auto Publish",
        "home_url": "https://www.cmread.com/wenxuenew/",
        "login_url": "https://www.cmread.com/wenxuenew/",
        "book_manage_url": "https://www.cmread.com/wenxuenew/detail/count?defaults=1",
        "state_file": "state_migu.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
        "chapter_manage_texts": [
            "章节管理", "管理章节", "作品管理",
            "管理作品", "目录管理", "章节目录",
            "更多管理", "管理", "编辑", "写作",
        ],
    },
    "qidian": {
        "key": "qidian",
        "name": "起点中文网",
        "short_name": "起点",
        "product_name": "Qidian Auto Publish",
        "home_url": "https://write.qq.com/",
        "login_url": "https://write.qq.com/",
        "book_manage_url": "https://write.qq.com/portal/dashboard/books",
        "state_file": "state_qidian.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
    },
    "faloo": {
        "key": "faloo",
        "name": "飞卢小说网",
        "short_name": "飞卢",
        "product_name": "Faloo Auto Publish",
        "home_url": "https://www.faloo.com/",
        "login_url": "https://u.faloo.com/regist/login.aspx",
        "book_manage_url": "https://author.faloo.com/OpusList2020.aspx",
        "state_file": "state_faloo.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
        "chapter_manage_texts": [
            "章节管理", "管理章节", "更新章节",
            "章节更新", "发布章节", "上传章节",
            "新增章节", "添加章节",
        ],
        "new_chapter_texts": [
            "新增章节", "添加章节", "发布章节",
            "上传章节", "更新章节", "章节更新",
            "写新章节", "发表章节", "增加章节",
        ],
        "next_step_texts": ["发布", "提交", "保存", "确认提交", "立即发布"],
        "final_publish_texts": ["确定", "确认", "确认发布", "立即发布", "发布", "提交"],
        "title_placeholders": ["请填写标题", "章节标题", "章节名称", "请输入章节名", "标题"],
        "title_selectors": [
            "#txtTitle", "#txttitle", "#Title", "#title", "#chapterName", "#chapterTitle",
            'input[placeholder="请填写标题"]', 'input[placeholder*="标题"]',
            'input[name="txtTitle"]', 'input[name="Title"]', 'input[name="title"]',
            'input[name*="Title" i]', 'input[id*="Title" i]', 'input[name*="chapter" i]',
        ],
        "body_selectors": [
            "#txtContent", "#Content", "#content", "#chapterContent", "#txtChapterContent",
            'textarea[name="txtContent"]', 'textarea[name="Content"]', 'textarea[name="content"]',
            'textarea[name*="Content" i]', 'textarea[id*="Content" i]',
            ".ql-editor", ".ProseMirror", '[contenteditable="true"]', "textarea",
        ],
        "tinymce_iframe_selectors": ["#mce_0_ifr", "#elm1_ifr", 'iframe[id*="_ifr"]'],
    },
    "qimao": {
        "key": "qimao",
        "name": "七猫小说",
        "short_name": "七猫",
        "product_name": "Qimao Auto Publish",
        "home_url": "https://zuozhe.qimao.com/",
        "login_url": "https://zuozhe.qimao.com/",
        "book_manage_url": "https://zuozhe.qimao.com/",
        "state_file": "state_qimao.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
        "chapter_manage_texts": [
            "章节管理", "管理章节", "作品管理",
            "管理作品", "目录管理", "章节目录",
            "内容管理", "去写作", "继续写作", "写作",
            "管理", "编辑",
        ],
        "new_chapter_texts": [
            "新建章节", "新增章节", "添加章节",
            "创建章节", "写新章节", "发布新章节",
            "新建", "添加",
        ],
        "next_step_texts": ["下一步", "发布", "提交", "保存并发布", "保存"],
        "final_publish_texts": [
            "确认发布", "立即发布", "发布章节",
            "提交发布", "确定发布", "发布", "确定", "提交",
        ],
        "title_placeholders": [
            "请输入章节名称", "请输入章节名",
            "请输入标题", "章节标题", "标题",
        ],
        "title_selectors": [
            'input[placeholder*="章节"]', 'input[placeholder*="标题"]', 'input[name*="chapter" i]',
            'input[name*="title" i]', 'input[id*="chapter" i]', 'input[id*="title" i]',
        ],
        "body_selectors": [
            ".q-contenteditable.book", '[contenteditable="true"].book',
            '.q-contenteditable[contenteditable="true"]',
            ".ProseMirror", '.ql-editor:not(.ql-blank)',
            'textarea[name*="content" i]', 'textarea[id*="content" i]', "textarea",

        ],
    },
    "fanqie": {
        "key": "fanqie",
        "name": "番茄小说",
        "short_name": "番茄",
        "product_name": "Fanqie Auto Publish",
        "home_url": "https://fanqienovel.com/",
        "login_url": "https://fanqienovel.com/main/writer/?enter_from=author_zone",
        "book_manage_url": "https://fanqienovel.com/main/writer/book-manage",
        "state_file": "state_fanqie.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
        "chapter_manage_texts": [
            "章节管理", "管理章节", "去写作",
            "继续写作", "写作", "管理",
        ],
        "new_chapter_texts": [
            "新建章节", "写新章节", "新增章节",
            "发布新章节", "新建",
        ],
        "next_step_texts": ["下一步"],
        "final_publish_texts": ["确认发布", "立即发布", "发布"],
        "popup_continue_texts": ["提交", "继续发布", "确认", "确定", "继续"],
        "title_placeholders": ["请输入标题", "请输入章节名", "请输入章节标题", "章节名"],
        "title_selectors": [
            'input[placeholder*="请输入标题"]',
            'input[placeholder*="请输入章节名"]',
            'input[placeholder*="章节"]',
            'input[type="text"]',
        ],
        "body_selectors": [".ql-editor", ".ProseMirror", '[contenteditable="true"]', "textarea"],
    },
    "ciweimao": {
        "key": "ciweimao",
        "name": "刺猬猫",
        "short_name": "刺猬猫",
        "product_name": "Ciweimao Auto Publish",
        "home_url": "https://www.ciweimao.com/",
        "login_url": "https://author.ciweimao.com/",
        "book_manage_url": "https://author.ciweimao.com/homepage",
        "state_file": "state_ciweimao.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
        "chapter_manage_texts": [
            "章节管理", "管理章节", "作品管理",
            "管理作品", "目录管理", "章节目录",
            "继续写作", "去写作", "写作",
            "管理", "编辑", "查看目录",
            "上传章节",
        ],
        "new_chapter_texts": [
            "新建章节", "新增章节", "添加章节",
            "创建章节", "写新章节", "发布新章节",
            "新建", "添加",
        ],
        "next_step_texts": ["下一步", "发布", "提交", "保存并发布"],
        "final_publish_texts": [
            "确认发布", "立即发布", "发布章节",
            "提交发布", "确定发布", "发布", "确定",
        ],
        "save_draft_texts": ["存草稿", "保存草稿", "保存", "暂存", "存为草稿"],
        "popup_continue_texts": ["提交", "继续发布", "我知道了", "确认", "确定", "继续", "发布"],
        "title_placeholders": ["请输入章节标题", "章节标题", "章节名称", "标题"],
        "title_selectors": [
            'input[placeholder*="章节"]',
            'input[placeholder*="标题"]',
            'input[name*="chapter" i]',
            'input[name*="title" i]',
            'input[id*="chapter" i]',
            'input[id*="title" i]',
        ],
        "body_selectors": [
            ".ql-editor",
            ".ProseMirror",
            '[contenteditable="true"]',
            "#chapter_content",
            "#content",
            "textarea",
        ],
    },
    "haiduxiaoshuo": {
        "key": "haiduxiaoshuo",
        "name": "海读小说",
        "short_name": "海读",
        "product_name": "Haidu Auto Publish",
        "home_url": "https://www.haiduxiaoshuo.com/",
        "login_url": "https://author.haiduxiaoshuo.com/",
        "book_manage_url": "https://author.haiduxiaoshuo.com/home/booklist",
        "state_file": "state_haiduxiaoshuo.json",
        "fallback_state_files": ["state.json"],
        **COMMON_TEXTS,
        "chapter_manage_texts": [
            "章节管理", "管理章节", "作品管理",
            "管理作品", "目录管理", "章节目录",
            "继续写作", "去写作", "写作",
            "管理", "编辑", "查看目录",
            "上传章节", "写新章",
        ],
        "new_chapter_texts": [
            "新建章节", "新增章节", "添加章节",
            "创建章节", "写新章节", "发布新章节",
            "新建", "添加", "写新章",
        ],
        "next_step_texts": ["下一步", "发布", "提交", "保存并发布"],
        "final_publish_texts": [
            "确认发布", "立即发布", "发布章节",
            "提交发布", "确定发布", "发布", "确定",
        ],
        "save_draft_texts": ["存草稿", "保存草稿", "保存", "暂存", "存为草稿"],
        "popup_continue_texts": ["提交", "继续发布", "我知道了", "确认", "确定", "继续", "发布"],
        "title_placeholders": ["请输入章节标题", "章节标题", "章节名称", "标题"],
        "title_selectors": [
            'input[placeholder*="章节"]',
            'input[placeholder*="标题"]',
            'input[name*="chapter" i]',
            'input[name*="title" i]',
            'input[id*="chapter" i]',
            'input[id*="title" i]',
        ],
        "body_selectors": [
            ".ql-editor",
            ".ProseMirror",
            '[contenteditable="true"]',
            "#chapter_content",
            "#content",
            "textarea",
        ],
    },
}


def list_platforms():
    return list(PLATFORMS.values())


def get_platform(platform_key=None):
    key = platform_key or DEFAULT_PLATFORM
    if key not in PLATFORMS:
        available = ", ".join(sorted(PLATFORMS))
        raise ValueError(f"Unknown platform '{key}'. Available: {available}")
    return PLATFORMS[key]


_DEFAULT = get_platform(DEFAULT_PLATFORM)
PLATFORM_NAME = _DEFAULT["name"]
PLATFORM_SHORT_NAME = _DEFAULT["short_name"]
PLATFORM_PRODUCT_NAME = _DEFAULT["product_name"]
PLATFORM_HOME_URL = _DEFAULT["home_url"]
PLATFORM_LOGIN_URL = _DEFAULT["login_url"]
PLATFORM_BOOK_MANAGE_URL = _DEFAULT["book_manage_url"]
PLATFORM_STATE_FILE = _DEFAULT["state_file"]
CHAPTER_MANAGE_TEXTS = _DEFAULT["chapter_manage_texts"]
NEW_CHAPTER_TEXTS = _DEFAULT["new_chapter_texts"]
NEXT_STEP_TEXTS = _DEFAULT["next_step_texts"]
FINAL_PUBLISH_TEXTS = _DEFAULT["final_publish_texts"]
SAVE_DRAFT_TEXTS = _DEFAULT["save_draft_texts"]
DISMISS_TEXTS = _DEFAULT["dismiss_texts"]
POPUP_CONTINUE_TEXTS = _DEFAULT["popup_continue_texts"]
TITLE_PLACEHOLDERS = _DEFAULT["title_placeholders"]
BODY_SELECTORS = _DEFAULT["body_selectors"]
