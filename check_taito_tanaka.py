import requests
import os
import re
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright
import jpholiday

WEBHOOK_URL = "https://discord.com/api/webhooks/1534362105258709146/uh9oEuUErxdt6CB0j_rODf8MycHNvh4DIh7mcoPWljPQ7uzQNnEBRwMLogSTxsi2_cLE"

BASE_URL = "https://shisetsu.city.taito.lg.jp/Wg_ModeSelect.aspx"

VERSION = "v1.0"

WEEKS = ["月", "火", "水", "木", "金", "土", "日"]

DEBUG = True


# =========================================
# util
# =========================================

def log(msg):

    if DEBUG:
        print(msg, flush=True)


def info(msg):

    print(msg, flush=True)


def send(msg):

    if DEBUG:
        print("\n=== SEND ===")
        print(msg)

    if not WEBHOOK_URL:
        return

    try:

        requests.post(
            WEBHOOK_URL,
            json={"content": msg},
            timeout=20
        )

    except Exception as e:

        info(f"⚠️ Discord送信失敗: {e}")


# =========================================
# block heavy resources
# =========================================

def block_resources(page):

    def handler(route):

        rtype = route.request.resource_type

        if rtype in [
            "image",
            "media",
            "font",
            "stylesheet"
        ]:
            route.abort()

        else:
            route.continue_()

    page.route("**/*", handler)


# =========================================
# parse
# =========================================

def parse(page, label):

    results = []

    try:

        table = page.locator("table").nth(24)

        if table.count() == 0:

            log(f"[{label}] table not found")

            return None

        cells = table.locator(
            "a[id*='lnkKoma'], span"
        ).all()

    except Exception as e:

        log(f"[{label}] parse error: {e}")

        return None

    log(f"[たなか {label}] cell数: {len(cells)}")

    for c in cells:

        try:

            txt = (
                c.inner_text()
                .replace("\xa0", "")
                .replace(" ", "")
                .strip()
            )

            m = re.search(
                r"(\d+)\s*(○|△|×|抽選|－)",
                txt
            )

            if m:

                results.append({
                    "day": int(m.group(1)),
                    "status": m.group(2)
                })

        except:
            pass

    unique = {}

    for r_item in results:

        key = (
            f"{r_item['day']}_"
            f"{r_item['status']}"
        )

        unique[key] = r_item

    results = sorted(
        unique.values(),
        key=lambda x: x["day"]
    )

    log(f"[たなか {label}] 件数: {len(results)}")

    return results


# =========================================
# click helper
# =========================================

def click(page, selector, wait_selector=None):

    page.locator(selector).first.click(
        timeout=5000
    )

    if wait_selector:

        page.wait_for_selector(
            wait_selector,
            timeout=5000
        )


# =========================================
# open calendar
# =========================================

def open_calendar(page):

    page.goto(
        BASE_URL,
        wait_until="domcontentloaded",
        timeout=15000
    )

    click(
        page,
        "input[value='公共施設予約メニュー']"
    )

    click(
        page,
        "input[value*='空き照会']"
    )

    click(
        page,
        "input[value='次頁']"
    )

    click(
        page,
        "input[value='次頁']"
    )

    click(
        page,
        "input[value*='たなか']"
    )

    info("===== たなか選択後 =====")
    info(page.inner_text("body")[:2000])

    click(
        page,
        "input[name='ucPCFooter$btnForward']"
    )

    info("===== 次へ後 =====")
    info(page.inner_text("body")[:2000])

    click(
        page,
        "input[value='カレンダー']"
    )

    # 今月1日スタート
    now = datetime.now(
        ZoneInfo("Asia/Tokyo")
    )

    page.locator("#txtYear").fill(
        str(now.year)
    )

    page.locator("#txtMonth").fill(
        str(now.month)
    )

    page.locator("#txtDay").fill("1")

    log(f"開始日: {now.year}/{now.month}/1")

    click(
        page,
        "input[value='1ヶ月']"
    )

    click(
        page,
        "input[name='ucPCFooter$btnForward']"
    )

    info("===== カレンダー後 =====")
    info(page.inner_text("body")[:1000])

    page.wait_for_timeout(1500)


# =========================================
# next month
# =========================================

def go_next(page):

    before_html = page.locator(
        "body"
    ).inner_html()

    page.locator(
        "#btnNextPeriod"
    ).click(
        force=True,
        timeout=5000
    )

    page.wait_for_function(
        """
        (before) => {
            return document.body.innerHTML !== before
        }
        """,
        arg=before_html,
        timeout=7000
    )

    page.wait_for_timeout(1500)

    body = page.inner_text("body")

    if "お探しのページを表示できません" in body:

        info(f"NEXT URL: {page.url}")

        info(
            f"NEXT TABLE COUNT: "
            f"{page.locator('table').count()}"
        )

        info(
            f"NEXT BODY:\n"
            f"{body[:5000]}"
        )

        info("❌ たなか NEXT: お探しのページを表示できません")

        return None

    result = parse(page, "NEXT")

    if result is None:

        info(f"NEXT URL: {page.url}")

        info(
            f"NEXT TABLE COUNT: "
            f"{page.locator('table').count()}"
        )

        info(
            f"NEXT BODY:\n"
            f"{body[:5000]}"
        )

        info("❌ たなか NEXT parse失敗")

    return result


# =========================================
# format
# =========================================

def format_month(data, year, month):

    rows = []

    for item in data:

        if item["status"] == "－":
            continue

        dt = datetime(
            year,
            month,
            item["day"]
        ).date()

        holiday_name = (
            jpholiday.is_holiday_name(dt)
        )

        is_weekend_or_holiday = (
            dt.weekday() >= 5
            or holiday_name
        )

        # 平日は ○ △ のみ表示
        if (
            not is_weekend_or_holiday
            and item["status"] not in ["○", "△"]
        ):
            continue

        w = WEEKS[dt.weekday()]

        line = (
            f"{month}/{item['day']}({w}) "
            f"{item['status']}"
        )

        if holiday_name:
            line += (
                f" ★({holiday_name})"
            )

        # 土日祝の ○ △ を強調
        if (
            is_weekend_or_holiday
            and item["status"] in ["○", "△"]
        ):
            line = f"**🌠 {line} 🌠**"

        rows.append(
            (item["day"], line)
        )

    rows = sorted(
        rows,
        key=lambda x: x[0]
    )

    seen = set()

    final = []

    for _, line in rows:

        if line not in seen:

            seen.add(line)

            final.append(line)

    return final


# =========================================
# mention
# =========================================

def has_weekend_or_holiday(
    data,
    year,
    month
):

    for item in data:

        # ○△だけ通知対象
        if item["status"] not in [
            "○",
            "△"
        ]:
            continue

        dt = datetime(
            year,
            month,
            item["day"]
        ).date()

        if (
            dt.weekday() >= 5
            or jpholiday.is_holiday(dt)
        ):
            return True

    return False


# =========================================
# main
# =========================================

def run_check():

    should_mention = False

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate"
            ]
        )

        context = browser.new_context()

        page = context.new_page()

        block_resources(page)

        try:

            open_calendar(page)

            current = parse(
                page,
                "CURRENT"
            )

            if current is None:

                send("⚠️ CURRENT parse失敗")

                return

            now_dt = datetime.now(
                ZoneInfo("Asia/Tokyo")
            )

            reservation_open = (
                now_dt.day > 18
                or (
                    now_dt.day == 18
                    and now_dt.hour >= 6
                )
            )

            if reservation_open:

                next_data = go_next(page)

                if next_data is None:

                    send("⚠️ NEXT parse失敗")

                    return

                next_month_mode = True

            else:

                next_data = []

                next_month_mode = False

            now = datetime.now(
                ZoneInfo("Asia/Tokyo")
            )

            current_month = now.month

            next_month = (
                1 if now.month == 12
                else now.month + 1
            )

            next_year = (
                now.year + 1
                if now.month == 12
                else now.year
            )

            is_changed = True

            # =========================================
            # format
            # =========================================

            current_lines = format_month(
                current,
                now.year,
                current_month
            )

            if next_month_mode:

                next_lines = format_month(
                    next_data,
                    next_year,
                    next_month
                )

            # =========================================
            # mention
            # =========================================

            if next_month_mode:

                should_mention = (
                    (
                        has_weekend_or_holiday(
                            current,
                            now.year,
                            current_month
                        )
                        or
                        has_weekend_or_holiday(
                            next_data,
                            next_year,
                            next_month
                        )
                    )
                    and
                    is_changed
                )

            else:

                should_mention = (
                    has_weekend_or_holiday(
                        current,
                        now.year,
                        current_month
                    )
                    and
                    is_changed
                )

            # =========================================
            # メンション制御 & モード判定
            # =========================================

            suppress_mention = (
                now_dt.day == 18
                and now_dt.hour == 6
                and now_dt.minute <= 20
            )

            mention = (
                "@everyone\n"
                if should_mention and not suppress_mention
                else ""
            )

            title = (
                f"🏸 **たなかスポーツプラザ** "
                f"[{VERSION}]"
            )

            if not is_changed:

                title += (
                    "\n（前回から変更なし）"
                )

            # モード表示の判定
            if not reservation_open:

                mode_text = "🎲 当月のみ空き予約可能期間"

            elif suppress_mention:

                mode_text = "🏃‍♂️💨 来月空き予約ラッシュアワー"

            else:

                mode_text = "📅 当月来月空き予約可能期間"

            # 指定ロジックの組み込み
            if next_month_mode:

                month_sections = []

                if current_lines:
                    month_sections.append(
                        f"【{current_month}月】\n"
                        + "\n".join(current_lines)
                    )

                if next_lines:
                    month_sections.append(
                        f"【{next_month}月】\n"
                        + "\n".join(next_lines)
                    )

                month_text = "\n\n".join(month_sections)

                msg = (
                    f"{mention}{title}\n\n"
                    f"{mode_text}\n\n"
                    f"{month_text}\n\n\u200b\n"
                )

            else:

                month_text = ""

                if current_lines:
                    month_text = (
                        f"【{current_month}月】\n"
                        + "\n".join(current_lines)
                    )

                msg = (
                    f"{mention}{title}\n\n"
                    f"{mode_text}\n\n"
                    f"{month_text}\n\n\u200b\n"
                )

            send(msg)

            info(
                f"✅ 台東区たなか完了 "
                f"(is_changed: {is_changed}, "
                f"mention: {should_mention})"
            )

        except Exception as e:

            info(f"⚠️ 台東区たなか ERROR: {e}")

            send(f"⚠️ 台東区たなか ERROR\n{e}")

        finally:

            context.close()
            browser.close()


if __name__ == "__main__":
    run_check()
