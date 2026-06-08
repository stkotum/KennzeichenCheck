"""One-off reconnaissance: drive the real availability checker and capture the
actual network request/response it uses, plus the form structure.

Run from a German IP (your machine) so we see the real behaviour without geo-blocks.
Saves artifacts to scout_out/ and prints a summary of the interesting XHR/fetch calls.
"""

import json
import re
import sys
import pathlib

from playwright.sync_api import sync_playwright

URL = "https://wunschkennzeichen-reservieren.jetzt/freising/reservieren"
OUT = pathlib.Path("scout_out")
OUT.mkdir(exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

INTERESTING = re.compile(r"(verf|avail|kennzeichen|plate|reserv|check|suggest|api|backend|graphql)", re.I)

network = []


def record_response(resp):
    try:
        req = resp.request
        rtype = req.resource_type
        url = resp.url
        entry = {
            "method": req.method,
            "url": url,
            "resource_type": rtype,
            "status": resp.status,
            "post_data": req.post_data,
            "body": None,
        }
        if rtype in ("xhr", "fetch") or INTERESTING.search(url):
            ct = (resp.headers or {}).get("content-type", "")
            if "json" in ct or "text" in ct:
                try:
                    txt = resp.text()
                    entry["body"] = txt[:4000]
                except Exception as e:
                    entry["body"] = f"<unreadable: {e}>"
        network.append(entry)
    except Exception as e:
        network.append({"error": str(e)})


def dump_form(page, tag):
    info = page.evaluate(
        """() => {
            const grab = (els) => Array.from(els).map(e => ({
                tag: e.tagName, type: e.type||null, name: e.name||null, id: e.id||null,
                placeholder: e.placeholder||null, value: e.value||null,
                aria: e.getAttribute('aria-label')||null,
                text: (e.innerText||'').trim().slice(0,40) || null,
                cls: (e.className||'').toString().slice(0,80) || null
            }));
            return {
                inputs: grab(document.querySelectorAll('input')),
                selects: grab(document.querySelectorAll('select')),
                buttons: grab(document.querySelectorAll('button, [role=button], a.btn')),
            };
        }"""
    )
    (OUT / f"form_{tag}.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return info


def try_dismiss_cookies(page):
    selectors = [
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button:has-text('Alle akzeptieren')",
        "button:has-text('Akzeptieren')",
        "button:has-text('Zustimmen')",
        "button:has-text('Einverstanden')",
        "[aria-label*='akzeptier' i]",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=2000)
                print(f"[scout] dismissed cookie banner via {sel}")
                page.wait_for_timeout(500)
                return True
        except Exception:
            pass
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="de-DE",
                                  viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.on("response", record_response)

        print(f"[scout] loading {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            print("[scout] networkidle timeout (continuing)")

        try_dismiss_cookies(page)
        page.wait_for_timeout(1500)

        form_before = dump_form(page, "before")
        print(f"[scout] inputs={len(form_before['inputs'])} selects={len(form_before['selects'])} buttons={len(form_before['buttons'])}")

        # Best-effort interaction: type FS / XY / 1 into plausible fields, then click a check button.
        try:
            text_inputs = page.query_selector_all("input[type=text], input:not([type])")
            sample = ["FS", "XY", "1"]
            for i, inp in enumerate(text_inputs[:3]):
                try:
                    inp.click()
                    inp.fill(sample[i] if i < len(sample) else "1")
                    print(f"[scout] filled input #{i} with {sample[i] if i < len(sample) else '1'}")
                except Exception as e:
                    print(f"[scout] could not fill input #{i}: {e}")

            # Click a button that looks like the availability check / search / reserve.
            for sel in [
                "button:has-text('prüf')", "button:has-text('Verfügbar')",
                "button:has-text('reservier')", "button:has-text('suchen')",
                "button[type=submit]", "[role=button]:has-text('prüf')",
            ]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click(timeout=3000)
                        print(f"[scout] clicked {sel}")
                        break
                except Exception:
                    continue
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"[scout] interaction error: {e}")

        dump_form(page, "after")
        page.screenshot(path=str(OUT / "page.png"), full_page=True)
        (OUT / "page.html").write_text(page.content(), encoding="utf-8")
        ctx.close()
        browser.close()

    (OUT / "network.json").write_text(json.dumps(network, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n===== INTERESTING NETWORK CALLS (xhr/fetch or matching keywords) =====")
    shown = 0
    for e in network:
        if "error" in e:
            continue
        if e["resource_type"] in ("xhr", "fetch") or INTERESTING.search(e["url"]):
            shown += 1
            print(f"\n[{e['method']}] {e['status']} {e['url']}  ({e['resource_type']})")
            if e.get("post_data"):
                print(f"   POST DATA: {e['post_data'][:600]}")
            if e.get("body"):
                print(f"   BODY: {e['body'][:800]}")
    print(f"\n[scout] {shown} interesting calls of {len(network)} total. Full dump: scout_out/network.json")


if __name__ == "__main__":
    main()
