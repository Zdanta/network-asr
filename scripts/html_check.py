"""Browser layout and interaction regression using an isolated fake native bridge."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright

from app.core.paths import browser_executable
from app.main import page_html

out = Path(__file__).resolve().parents[1] / "ui-validation"
out.mkdir(exist_ok=True)
fixtures = [
    {
        "task_id": "a" * 32,
        "source_title": "周末的创作灵感 · 第一份声音笔记",
        "source_type": "local",
        "status": "SUCCESS",
        "stage": "完成",
        "created_at": "2026-11-14T15:30:00",
        "raw_text": "这是一份界面验证用文字稿，不是真实识别结果。\n\n把声音交给小屋，把时间留给好点子。",
        "duration_seconds": 36,
    },
    {
        "task_id": "b" * 32,
        "source_title": "一条非常非常长的抖音视频标题用于测试中文换行与详情排版，避免标题溢出或者挤压操作按钮 <img src=x onerror=alert(1)>",
        "source_type": "douyin",
        "status": "FAIL",
        "stage": "处理失败",
        "error_message": "抖音解析或下载失败：视频可能不可访问、需要登录，或网络受限。",
        "created_at": "2026-11-14T15:29:00",
        "raw_text": None,
    },
]
setup = """window.testCalls=[];window.fakeTasks=TASKS;
const c={url:'https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash',resource_id:'volc.bigasr.auc_turbo',model_name:'bigmodel',timeout:180,output_dir:'C:/Users/演示/Downloads',has_key:false};
window.pywebview={api:new Proxy({}, {get:(_,name)=>async(...args)=>{
 window.testCalls.push([name,args]);let data=null;
 if(name==='bootstrap')data={config:c,version:'1.1.0',data_dir:'仅用于界面测试的临时数据'};
 if(name==='snapshot')data=window.fakeTasks;
 if(name==='detail')data=window.fakeTasks.find(t=>t.task_id===args[0]);
 if(name==='choose_file')data='C:/素材/中文 空格测试视频.mp4';
 if(name==='save_settings')data={...c,has_key:true};
 if(name==='delete_record')window.fakeTasks=window.fakeTasks.filter(t=>t.task_id!==args[0]);
 if(name==='export_text')data=true;
 return {ok:true,data};
}})};
""".replace("TASKS", json.dumps(fixtures, ensure_ascii=False))
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=browser_executable(), headless=True)
    page = browser.new_page(viewport={"width": 1260, "height": 920}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(setup)
    # file navigation ensures init scripts run, assets already inlined.
    preview = out / "preview.html"
    preview.write_text(page_html(), encoding="utf-8")
    page.goto(preview.as_uri())
    page.evaluate("window.dispatchEvent(new Event('pywebviewready'))")
    page.wait_for_selector(".recent-item")
    assert page.locator("h1").all_text_contents() == ["网络ASR"]
    assert page.evaluate("getComputedStyle(document.body).fontSize === '16px'")
    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight")
    page.screenshot(path=str(out / "desktop-test.png"), full_page=True)
    page.evaluate("window.fakeTasks=[];update()")
    page.wait_for_selector(".empty-inline")
    page.screenshot(path=str(out / "desktop.png"), full_page=True)
    page.evaluate("window.fakeTasks=" + json.dumps(fixtures, ensure_ascii=False) + ";update()")
    page.wait_for_selector(".recent-item")
    page.get_by_role("tab", name="抖音分享链接").click()
    assert page.locator("#share").is_visible()
    page.get_by_role("tab", name="抖音分享链接").press("ArrowLeft")
    assert page.locator("#local-panel").is_visible()
    page.locator("#choose-file").click()
    page.wait_for_function("document.querySelector('#file-name').textContent.includes('中文 空格')")
    page.get_by_role("button", name="转写记录").click()
    page.locator('[data-id="' + ("b" * 32) + '"]').last.click()
    page.wait_for_selector(".detail-heading")
    assert not page.locator(".detail-heading img").count()
    page.screenshot(path=str(out / "history.png"), full_page=True)
    page.get_by_role("button", name="删除记录", exact=True).click()
    page.wait_for_selector("dialog[open]")
    assert page.locator("dialog button[value=cancel]").evaluate("(el)=>el===document.activeElement")
    page.keyboard.press("Escape")
    assert not page.locator("dialog").is_visible()
    page.get_by_role("button", name="删除记录", exact=True).click()
    page.locator("#dialog-confirm").click()
    page.wait_for_function("window.fakeTasks.length===1")
    page.get_by_role("button", name="设置").click()
    page.locator("#setting-key").fill("test-only-key")
    page.locator("#toggle-key").click()
    assert page.locator("#setting-key").get_attribute("type") == "text"
    page.locator("#setting-key").fill("")
    page.screenshot(path=str(out / "settings.png"), full_page=True)
    page.get_by_role("button", name="保存配置").click()
    page.wait_for_function("document.querySelector('#key-status').textContent.includes('已保存')")
    page.get_by_role("button", name="开始转写", exact=False).first.click()
    for width in (320, 640, 900):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
    page.set_viewport_size({"width": 320, "height": 900})
    page.screenshot(path=str(out / "narrow.png"), full_page=True)
    page.set_viewport_size({"width": 1260, "height": 920})
    page.evaluate("document.documentElement.style.zoom='2'")
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    assert not errors, errors
    (out / "checks.json").write_text(
        json.dumps(
            {
                "desktop": True,
                "widths": [320, 640, 900, 1260],
                "zoom_200_percent": True,
                "tabs_keyboard": True,
                "long_title_escape": True,
                "dialog_focus_escape_delete": True,
                "settings": True,
                "page_errors": errors,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    browser.close()
print("HTML checks passed; screenshots in ui-validation")
