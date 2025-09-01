import asyncio
import httpx
from playwright.async_api import async_playwright
from extras import append_json, sanitize_filename, time_format, update_next_roulette

async def do_auth(baseUrl, username, password, mode="login", proxy=""):
    done_event = asyncio.Event()

    async def task():
        async with async_playwright() as p:
            if proxy != "":
                proxy_parts = proxy.split("@")
                creds, server = proxy_parts[0], proxy_parts[1]
                username_proxy, password_proxy = creds.split(":")
                browser = await p.chromium.launch(
                    headless=False, 
                    args=["--disable-blink-features=AutomationControlled"],
                    proxy={
                        "server": f"http://{server}",
                        "username": username_proxy,
                        "password": password_proxy,
                    }, 
                )
            else:
                browser = await p.chromium.launch(
                headless=False, 
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context()
            page = await context.new_page()

            result = {"sid": None, "uuid": None}
            counters = {"success": 0, "fail": 0}

            async def handle_response(response):
                url = response.url
                if "passport/login.html" in url and response.request.method == "POST":
                    headers = response.headers
                    data = await response.json()
                    login_message = data.get("message")
                    result["sid"] = headers.get("sid")
                    result["uuid"] = headers.get("uuid")
                    results = {"username": username, "sid": result["sid"], "uuid": result["uuid"], "next_roulette": ""}
                    filename = sanitize_filename(baseUrl)
                    append_json(results, filename)
                    if login_message is None:
                        login_message = "Login successful"
                    else:
                        counters["message"] = login_message 
                    if data.get("code") == "200":
                        counters["success"] += 1
                    else:
                        counters["fail"] += 1

                elif "/player-api/register" in url and response.request.method == "POST":
                    try:
                        data = await response.json()
                        register_message = data.get("message")
                        counters["message"] = register_message
                        if data.get("code") == "200":
                            counters["success"] += 0
                        else:
                            counters["fail"] += 1
                    except:
                        None

            page.on("response", handle_response)

            await page.goto(f"{baseUrl}/account", timeout=60000, wait_until="load")
            await page.wait_for_timeout(3000)

            if mode == "login":
                await page.click("div.button-un-highlight:has-text('Login')")
                await page.wait_for_selector("input[type='text']", timeout=10000)
                await page.fill("input[type='text']", username)
                await page.fill("input[type='password']", password)
                login_btn = page.locator("div.button-un-highlight.bg-gradient-to-b:has-text('Login')")
                await login_btn.wait_for(state="visible", timeout=10000)
                await login_btn.click()

            elif mode == "register":
                await page.click("div.button-un-highlight:has-text('Daftar')")
                await page.wait_for_selector("input[type='text']", timeout=10000)
                await page.fill("input[type='text']", username)
                await page.locator("input[type=password]").nth(0).fill(password)
                await page.locator("input[type=password]").nth(1).fill(password)
                register_btn = page.locator("div.button-un-highlight.bg-gradient-to-b:has-text('Daftar')").nth(1)
                await register_btn.wait_for(state="visible", timeout=10000)
                await register_btn.click()

            # Tunggu response datang
            await page.wait_for_timeout(3000)
            await browser.close()
            done_event.set()  # spinner selesai
            return counters

    auth_result = await task()
    return auth_result

async def run_get_free_balance_async(sid: str, account: str, base_url: str):
    result = {"account": 11111, "message": "", "roulette": None}

    if not sid:
        result["message"] = "SID tidak tersedia"
        return result

    headers = {"sid": sid}
    detail_url = f"{base_url}/activity-api/activity/detail"
    detail_payload = {"activityId": "1335ce1c-26c7-4635-8ab3-c6b52c1419b2::vip_wheel"}
    detail_headers = headers.copy()
    detail_headers["referer"] = f"{base_url}/sales-promotion/turntable/1335ce1c-26c7-4635-8ab3-c6b52c1419b2::vip_wheel"

    async with httpx.AsyncClient(timeout=10) as client:
        # Ambil roulette detail
        roulette_detail = None
        for attempt in range(3):
            try:
                resp = await client.post(detail_url, json=detail_payload, headers=detail_headers)
                resp.raise_for_status()
                roulette_detail = resp.json()
                break
            except Exception as e:
                result["message"] = f"Attempt {attempt+1} failed: {e}"
                await asyncio.sleep(2)
        if roulette_detail is None:
            result["message"] = "Fetching Roulette Details failed"
            return result

        try:
            wheel = roulette_detail.get("data", {}).get("wheel", {})
            roulette_prize_vo = wheel.get("roulettePrizeVo", {})
            current_vip_grade = roulette_prize_vo.get("currentVipGrade")
            current_medal_grade = roulette_prize_vo.get("currentMedalGrade")
            prize_info = roulette_prize_vo.get("prize", {}).get(current_medal_grade, {})
            number_of_draws = prize_info.get("numberOfDraws")

            if not number_of_draws:
                result["message"] = "No draws available for current medal grade"
                return result

            prizes = []
            times = number_of_draws.get("times", 0)
            result["roulette"] = number_of_draws.get("nextTime")

            if times > 0:
                draw_url = f"{base_url}/activity-api/roulette/luckyDraw"
                for i in range(times):
                    draw_payload = {
                        "activityMessageId": "1335ce1c-26c7-4635-8ab3-c6b52c1419b2",
                        "vipLevel": current_vip_grade,
                        "medalId": current_medal_grade,
                    }
                    draw_headers = headers.copy()
                    draw_headers["referer"] = detail_headers["referer"]

                    draw_data = None
                    for attempt in range(3):
                        try:
                            draw_resp = await client.post(draw_url, json=draw_payload, headers=draw_headers)
                            draw_resp.raise_for_status()
                            draw_data = draw_resp.json()
                            break
                        except Exception as e:
                            result["message"] = f"Spin #{i+1} attempt {attempt+1} failed: {e}"
                            await asyncio.sleep(2)

                    if draw_data is None:
                        result["message"] = f"Spin #{i+1} failed"
                        return result

                    prize_type = draw_data.get("data", {}).get("type")
                    prize_amount = draw_data.get("data", {}).get("prizeAmount")
                    prizes.append({prize_type: prize_amount})

                    if i < times - 1:
                        await asyncio.sleep(3)

                result["message"] = f"Claimed x{times} spins and got {{ " + ", ".join(
                    [f"{k}: {v}" for p in prizes for k, v in p.items()]
                ) + " }}"
            else:
                update_next_roulette(sanitize_filename(base_url), account, result["roulette"])
                result["message"] = f"Next spin { time_format(result["roulette"])}"

        except Exception as e:
            result["message"] = f"Unexpected error: {e}"

    return result
