import asyncio
import httpx
from httpx_socks import AsyncProxyTransport
from playwright.async_api import async_playwright
from extras import append_json, sanitize_filename, time_format, update_next_roulette

MAX_RETRIES = 3

# ---------------- SAFE GOTO ----------------
async def safe_goto(page, username, url, retries=3, delay=2, update_state=None, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            response = await page.goto(url, **kwargs)
            if response and response.ok:
                return response
            if response and response.status == 309:
                loc = response.headers.get("Location")
                if loc:
                    await update_state(f"[{username}] createAccount: [INFO] Redirect 309 ke {loc}....")
                    return await page.goto(loc, **kwargs)

            await update_state(f"[{username}] createAccount: [WARN] Attempt {attempt} gagal (status={getattr(response, 'status', None)}), retrying....")
        except Exception as e:
            await update_state(f"[{username}] createAccount: [ERROR] Attempt {attempt} error: {e}....")
            None

        await asyncio.sleep(delay)

    await update_state(f"[{username}] createAccount: [FAIL] Gagal load {url} setelah {retries} percobaan....")
    return None

# ---------------- DO AUTH ----------------
async def do_auth(baseUrl, username, password, mode="login", proxy="", update_state=None, file_name=None):
    done_event = asyncio.Event()

    async def task():
        async with async_playwright() as p:
            if proxy != "":
                proxy_parts = proxy.split("@")
                creds, server = proxy_parts[0], proxy_parts[1]
                username_proxy, password_proxy = creds.split(":")
                await update_state(f"[{username}] createAccount: Starting Browser....")
                browser = await p.chromium.launch(
                    headless=True, 
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                    proxy={
                        "server": f"http://{server}",
                        "username": username_proxy,
                        "password": password_proxy,
                    }, 
                )
            else:
                browser = await p.chromium.launch(
                    headless=True, 
                    args=["--disable-blink-features=AutomationControlled"],
                )
            context = await browser.new_context()

            await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image","font","media"] else route.continue_())

            page = await context.new_page()

            result = {"sid": None, "uuid": None}
            counters = {"success": 0, "fail": 0}

            async def handle_response(response):
                url = response.url
                try:
                    if response.status < 300 or response.status >= 400:
                        data = await response.json()
                    else:
                        data = {}
                except:
                    data = {}

                # Login handler
                if "passport/login.html" in url and response.request.method == "POST":
                    headers = response.headers
                    login_message = data.get("message") if data else None
                    result["sid"] = headers.get("sid")
                    result["uuid"] = headers.get("uuid")
                    results = {"username": username, "sid": result["sid"], "uuid": result["uuid"], "next_roulette": ""}
                    if file_name:
                        append_json(results, file_name)
                    else:
                        fileName = sanitize_filename(baseUrl)
                        append_json(results, fileName)

                    if not login_message:
                        await update_state(f"[{username}] createAccount: Login Successful.....")
                    else:
                        await update_state(f"[{username}] createAccount: {login_message}")

                    if data.get("code") == "200":
                        counters["success"] += 1
                    else:
                        counters["fail"] += 1

                # Register handler
                elif "/player-api/register" in url and response.request.method == "POST":
                    register_message = data.get("message") if data else None
                    if register_message:
                        await update_state(f"[{username}] createAccount: {register_message}")
                    if data.get("code") == "200":
                        await update_state(f"[{username}] createAccount: Register Successful....")
                        counters["success"] += 0
                    else:
                        counters["fail"] += 1

            page.on("response", handle_response)

            resp = await safe_goto(page, username, f"{baseUrl}/account", timeout=60000, wait_until="load", update_state=update_state)
            if not resp:
                counters["fail"] += 1
                await browser.close()
                done_event.set()
                return counters
            
            await page.wait_for_timeout(3000)

            if mode == "login":
                await update_state(f"[{username}] createAccount: Login....")
                await page.click("div.button-un-highlight:has-text('Login')")
                await page.wait_for_selector("input[type='text']", timeout=10000)
                await page.fill("input[type='text']", username)
                await page.fill("input[type='password']", password)
                login_btn = page.locator("div.button-un-highlight.bg-gradient-to-b:has-text('Login')")
                await login_btn.wait_for(state="visible", timeout=10000)
                await login_btn.click()

            elif mode == "register":
                await update_state(f"[{username}] createAccount: Register....")
                await page.click("div.button-un-highlight:has-text('Daftar')")
                await page.wait_for_selector("input[type='text']", timeout=10000)
                await page.fill("input[type='text']", username)
                await page.locator("input[type=password]").nth(0).fill(password)
                await page.locator("input[type=password]").nth(1).fill(password)
                register_btn = page.locator("div.button-un-highlight.bg-gradient-to-b:has-text('Daftar')").nth(1)
                await register_btn.wait_for(state="visible", timeout=10000)
                await register_btn.click()

            await page.wait_for_timeout(3000)
            await browser.close()
            done_event.set()
            return counters

    auth_result = await task()
    return auth_result

# ---------------- GET FREE BALANCE ----------------
async def run_get_free_balance_async(sid: str, account: str, base_url: str, update_state=None, proxy_url: str = None):
    result = {"account": account, "message": "", "roulette": None}

    if not sid:
        if update_state:
            await update_state(f"[{account}] getFreeBalance: SID tidak tersedia, login dulu...")
        return result

    transport = AsyncProxyTransport.from_url(proxy_url) if proxy_url else None

    async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=True) as client:
        # Ambil detail roulette
        roulette_detail = None
        detail_url = f"{base_url}/activity-api/activity/detail"
        detail_payload = {"activityId": "1335ce1c-26c7-4635-8ab3-c6b52c1419b2::vip_wheel"}
        detail_headers = {"sid": sid, "referer": f"{base_url}/sales-promotion/turntable/1335ce1c-26c7-4635-8ab3-c6b52c1419b2::vip_wheel"}

        for attempt in range(3):
            try:
                if update_state:
                    await update_state(f"[{account}] getFreeBalance: Fetching roulette details attempt {attempt+1}...")
                resp = await client.post(detail_url, json=detail_payload, headers=detail_headers)
                resp.raise_for_status()
                roulette_detail = resp.json()
                if update_state:
                    await update_state(f"[{account}] getFreeBalance: Fetched roulette details successfully")
                break
            except Exception as e:
                if update_state:
                    await update_state(f"[{account}] getFreeBalance: Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)

        if roulette_detail is None:
            if update_state:
                await update_state(f"[{account}] getFreeBalance: Failed to fetch roulette details")
            return result

        try:
            wheel = roulette_detail.get("data", {}).get("wheel", {})
            roulette_prize_vo = wheel.get("roulettePrizeVo", {})
            current_vip_grade = roulette_prize_vo.get("currentVipGrade")
            current_medal_grade = roulette_prize_vo.get("currentMedalGrade")
            prize_info = roulette_prize_vo.get("prize", {}).get(current_medal_grade, {})
            number_of_draws = prize_info.get("numberOfDraws")

            if not number_of_draws:
                if update_state:
                    await update_state(f"[{account}] getFreeBalance: No draws available")
                return result

            times = number_of_draws.get("times", 0)
            result["roulette"] = number_of_draws.get("nextTime")

            if times > 0:
                draw_url = f"{base_url}/activity-api/roulette/luckyDraw"
                prizes = []
                for i in range(times):
                    draw_payload = {
                        "activityMessageId": "1335ce1c-26c7-4635-8ab3-c6b52c1419b2",
                        "vipLevel": current_vip_grade,
                        "medalId": current_medal_grade,
                    }
                    draw_headers = {"sid": sid, "referer": detail_headers["referer"]}

                    draw_data = None
                    for attempt in range(3):
                        try:
                            if update_state:
                                await update_state(f"[{account}] getFreeBalance: Spinning #{i+1} attempt {attempt+1}...")
                            resp = await client.post(draw_url, json=draw_payload, headers=draw_headers)
                            resp.raise_for_status()
                            draw_data = resp.json()
                            if update_state:
                                await update_state(f"[{account}] getFreeBalance: Spin #{i+1} success")
                            break
                        except Exception as e:
                            if update_state:
                                await update_state(f"[{account}] getFreeBalance: Spin #{i+1} attempt {attempt+1} failed: {e}")
                            await asyncio.sleep(2)

                    if draw_data is None:
                        if update_state:
                            await update_state(f"[{account}] getFreeBalance: Spin #{i+1} failed")
                        return result

                    prize_type = draw_data.get("data", {}).get("type")
                    prize_amount = draw_data.get("data", {}).get("prizeAmount")
                    prizes.append({prize_type: prize_amount})
                    if update_state:
                        await update_state(f"[{account}] getFreeBalance: Spin #{i+1} got {prize_type}: {prize_amount}")

                    if i < times - 1:
                        await asyncio.sleep(2)

                if update_state:
                    prize_summary = ", ".join([f"{k}: {v}" for p in prizes for k, v in p.items()])
                    await update_state(f"[{account}] getFreeBalance: Claimed x{times} spins -> {prize_summary}")
            else:
                update_next_roulette(sanitize_filename(base_url), account, result["roulette"])
                if update_state:
                    await update_state(f"[{account}] getFreeBalance: Next spin at {time_format(result['roulette'])}")

        except Exception as e:
            if update_state:
                await update_state(f"[{account}] getFreeBalance: Unexpected error: {e}")

    return result

# ---------------- CLAIM BONUS ----------------
async def run_claim_bonus_async(sid: str, account: str, base_url: str, update_state=None, proxy_url: str = None):
    result = {"account": account, "message": "", "claimed": 0}

    if not sid:
        if update_state:
            await update_state(f"[{account}] claimBonus: SID tidak tersedia, login dulu...")
        return result

    transport = AsyncProxyTransport.from_url(proxy_url) if proxy_url else None

    async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=True) as client:
        # Ambil bonus cards
        bonus_cards = []
        for attempt in range(3):
            try:
                if update_state:
                    await update_state(f"[{account}] claimBonus: Fetching bonus cards attempt {attempt+1}...")
                resp = await client.post(
                    f"{base_url}/activity-api/auditBonus/bonusCards",
                    json={"pageNumber": 1, "pageSize": 40, "status": "process", "order": {"easy": "ASC"}},
                    headers={"sid": sid, "referer": f"{base_url}/referral-bonus", "origin": base_url},
                )
                resp.raise_for_status()
                bonus_cards = resp.json().get("data", {}).get("model", [])
                break
            except Exception as e:
                if update_state:
                    await update_state(f"[{account}] claimBonus: Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)

        if not bonus_cards:
            if update_state:
                await update_state(f"[{account}] claimBonus: No bonus cards available")
            return result

        total_claimed = 0
        for card in bonus_cards:
            card_id = card.get("id")
            card_point = card.get("auditPoint")
            claim_data = None
            for attempt in range(3):
                try:
                    if update_state:
                        await update_state(f"[{account}] claimBonus: Claiming card {card_id} attempt {attempt+1}...")
                    resp = await client.post(
                        f"{base_url}/activity-api/auditBonus/pointRedeem",
                        json={"id": card_id, "type": "bet", "point": card_point},
                        headers={"sid": sid, "referer": f"{base_url}/referral-bonus", "origin": base_url},
                    )
                    resp.raise_for_status()
                    claim_data = resp.json()
                    break
                except Exception as e:
                    if update_state:
                        await update_state(f"[{account}] claimBonus: Attempt {attempt+1} failed: {e}")
                    await asyncio.sleep(2)

            if claim_data and claim_data.get("data", {}).get("code") != "PLAYER_BONUS_POINT_NOT_ENOUGH":
                total_claimed += 1

        result["claimed"] = total_claimed
        if total_claimed > 0:
            result["message"] = f"Claimed {total_claimed} Bonus"
            if update_state:
                await update_state(f"[{account}] claimBonus: {total_claimed} bonus cards claimed successfully")

    return result

# ---------------- CHECK BALANCE ----------------
async def run_check_balance_async(sid: str, account: str, base_url: str, balance_threshold: float = 0, update_state=None, proxy_url: str = None):
    result = {"account": account, "message": "", "balance": None}

    if not sid:
        if update_state:
            await update_state(f"[{account}] checkBalance: SID tidak tersedia, login dulu...")
        return result

    transport = AsyncProxyTransport.from_url(proxy_url) if proxy_url else None

    async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=True) as client:
        balance_data = None
        for attempt in range(3):
            try:
                if update_state:
                    await update_state(f"[{account}] checkBalance: Fetching balance attempt {attempt+1}...")
                resp = await client.get(
                    f"{base_url}/activity-api/activity/getAmountInfo",
                    headers={"sid": sid, "referer": f"{base_url}/account"},
                )
                resp.raise_for_status()
                balance_data = resp.json().get("data", {}).get("availableBalanceResult", {})
                break
            except Exception as e:
                if update_state:
                    await update_state(f"[{account}] checkBalance: Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)

        if balance_data is None:
            if update_state:
                await update_state(f"[{account}] checkBalance: Failed to retrieve balance")
            return result

        balance = balance_data.get("balance")
        result["balance"] = balance
        if isinstance(balance, (int, float)) and balance >= balance_threshold:
            result["message"] = f"Balance: {balance:.2f}"
            if update_state:
                await update_state(f"[{account}] checkBalance: Balance is sufficient: {balance:.2f}")
        else:
            result["message"] = f"Balance below threshold: {balance:.2f}" if balance is not None else "Balance not found"
            if update_state:
                await update_state(f"[{account}] checkBalance: Balance {balance} below threshold {balance_threshold}")

    return result