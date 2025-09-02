import questionary
import asyncio
import random
import itertools
import subprocess
from pathlib import Path
from tasks import do_auth, run_get_free_balance_async, run_check_balance_async, run_claim_bonus_async
from extras import read_file, read_proxies, random_number, load_json, check_latest_version, txt_to_json_accounts
from rich.console import Console
from rich.live import Live
from rich.text import Text
import json

console = Console(color_system="auto")
task_results = {"success": 0, "fail": 0}
all_states = {}
spinner_chars = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

# ---------------- SPINNER ----------------
async def spinner_task(states: dict, refresh_rate: float = 0.2):
    spinners = {}
    with Live(console=console, refresh_per_second=int(1/refresh_rate)) as live:
        try:
            while True:
                lines = []
                for username, state in states.items():
                    if username not in spinners:
                        spinners[username] = itertools.cycle(spinner_chars)
                    spinner_char = next(spinners[username])
                    if state["done"]:
                        lines.append(f"[{username}] {state['msg']}")
                    else:
                        lines.append(f"{spinner_char} [{username}] {state['msg']}")
                lines.append("")
                lines.append("==========TASK INFO==========")
                lines.append(f"Success: {task_results['success']} | Failed: {task_results['fail']}")
                lines.append("=============================")
                live.update(Text("\n".join(lines)))

                if states and all(state["done"] for state in states.values()):
                    break
                await asyncio.sleep(refresh_rate)
        except asyncio.CancelledError:
            pass

# ---------------- WORKER ----------------
async def worker(semaphore, base_url, username, proxies, tasks_selected, file_name, balance_threshold=300):
    async with semaphore:
        proxy = random.choice(proxies) if proxies else ""
        results = {}

        for task in tasks_selected:
            task_key = f"{username}-{task}"
            all_states[task_key] = {"msg": f"{task}: Starting...", "done": False}

            async def update_state(msg, key=task_key):
                all_states[key]["msg"] = msg

            try:
                if task == "register":
                    all_states[task_key]["msg"] = f"{task}: Registering..."
                    auth_result = await do_auth(base_url, username, username, "register", proxy, update_state, file_name)
                    results["register"] = auth_result
                    task_results["success"] += auth_result.get("success", 0)
                    task_results["fail"] += auth_result.get("fail", 0)

                elif task == "getFreeBalance":
                    all_states[task_key]["msg"] = f"{task}: Preparing Free Balance..."
                    idx = next((i for i, a in enumerate(accounts_list) if a["username"] == username), None)
                    if idx is None:
                        all_states[task_key]["msg"] = f"{task}: Username tidak ditemukan..."
                        continue

                    sid = accounts_list[idx].get("sid")
                    if not sid:
                        all_states[task_key]["msg"] = f"{task}: SID kosong, login dulu..."
                        auth_result = await do_auth(base_url, username, username, "login", proxy, update_state, file_name)
                        sid = None
                        if auth_result.get("success", 0) > 0 and file_name:
                            accounts_json = load_json(file_name)
                            for acc in accounts_json:
                                if acc["username"] == username:
                                    sid = acc.get("sid")
                                    accounts_list[idx]["sid"] = sid
                                    break
                        else:
                            all_states[task_key]["msg"] = f"{task}: Login gagal, skip Free Balance"
                            task_results["fail"] += 1
                            continue

                    proxy_url = f"http://{proxy}" if proxy else None
                    balance_result = await run_get_free_balance_async(sid, username, base_url, update_state, proxy_url)
                    results["getFreeBalance"] = balance_result

                elif task == "claimBonus":
                    all_states[task_key]["msg"] = f"{task}: Claiming bonus..."
                    # Cari akun
                    idx = next((i for i, a in enumerate(accounts_list) if a["username"] == username), None)
                    if idx is None:
                        all_states[task_key]["msg"] = f"{task}: Username tidak ditemukan..."
                        task_results["fail"] += 1
                        continue

                    sid = accounts_list[idx].get("sid")
                    # Kalau SID kosong, login dulu
                    if not sid:
                        all_states[task_key]["msg"] = f"{task}: SID kosong, login dulu..."
                        auth_result = await do_auth(base_url, username, username, "login", proxy, update_state, file_name)
                        sid = None
                        if auth_result.get("success", 0) > 0:
                            if file_name:
                                accounts_json = load_json(file_name)
                                for acc in accounts_json:
                                    if acc["username"] == username:
                                        sid = acc.get("sid")
                                        accounts_list[idx]["sid"] = sid
                                        break
                        else:
                            all_states[task_key]["msg"] = f"{task}: Login gagal, skip claimBonus"
                            task_results["fail"] += 1
                            continue

                    proxy_url = f"http://{proxy}" if proxy else None
                    claim_result = await run_claim_bonus_async(sid, username, base_url, update_state=update_state, proxy_url=proxy_url)
                    results["claimBonus"] = claim_result

                elif task == "checkBalance":
                    all_states[task_key]["msg"] = f"{task}: Checking balance..."
                    idx = next((i for i, a in enumerate(accounts_list) if a["username"] == username), None)
                    if idx is None:
                        all_states[task_key]["msg"] = f"{task}: Username tidak ditemukan..."
                        task_results["fail"] += 1
                        continue

                    sid = accounts_list[idx].get("sid")
                    if not sid:
                        all_states[task_key]["msg"] = f"{task}: SID kosong, login dulu..."
                        auth_result = await do_auth(base_url, username, username, "login", proxy, update_state, file_name)
                        sid = None
                        if auth_result.get("success", 0) > 0 and file_name:
                            accounts_json = load_json(file_name)
                            for acc in accounts_json:
                                if acc["username"] == username:
                                    sid = acc.get("sid")
                                    accounts_list[idx]["sid"] = sid
                                    break
                        else:
                            all_states[task_key]["msg"] = f"{task}: Login gagal, skip checkBalance"
                            task_results["fail"] += 1
                            continue

                    proxy_url = f"http://{proxy}" if proxy else None
                    balance_result = await run_check_balance_async(
                        sid, username, base_url,
                        balance_threshold=balance_threshold,
                        update_state=update_state,
                        proxy_url=proxy_url
                    )
                    results["checkBalance"] = balance_result

                elif task == "update":
                    try:
                        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
                        local_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
                        subprocess.run(["git", "fetch", "origin"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        remote_commit = subprocess.check_output(["git", "rev-parse", f"origin/{branch}"]).decode().strip()
                        if local_commit != remote_commit:
                            subprocess.run(["git", "pull", "origin", branch], check=True)
                    except:
                        pass

            except Exception as e:
                all_states[task_key]["msg"] = f"{task}: ERROR {e}"
                task_results["fail"] += 1
            finally:
                all_states[task_key]["done"] = True

        return results

# ---------------- MAIN ----------------
async def main_limited(base_url, tasks_selected, accounts_list=None, num_accounts=None, max_concurrent=1, proxies=None, file_name=None, balance_threshold=300):
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = []

    if accounts_list:
        usernames = [acc["username"] for acc in accounts_list[:num_accounts]]
    else:
        usernames = [random_number() for _ in range(num_accounts)]

    for username in usernames:
        tasks.append(asyncio.create_task(worker(semaphore, base_url, username, proxies, tasks_selected, file_name, balance_threshold)))

    spinner_coro = asyncio.create_task(spinner_task(all_states))
    try:
        results = await asyncio.gather(*tasks)
    finally:
        if not spinner_coro.done():
            spinner_coro.cancel()
            try:
                await spinner_coro
            except asyncio.CancelledError:
                pass

    return results

# ---------------- PROMPT ----------------
def prompt_file(folder_path="./data/accounts", extensions=None):
    extensions = extensions or [".txt", ".json"]
    folder = Path(folder_path)
    files = [f.name for f in folder.iterdir() if f.is_file() and f.suffix in extensions]
    if not files: return None
    selected = questionary.select("Pilih file:", choices=files).ask()
    return folder / selected

def prompt_base_url():
    items = read_file()
    if items:
        return questionary.select("baseUrl?", choices=items).ask()

def prompt_use_proxy():
    return questionary.confirm("Use proxy?", default=True).ask()

def prompt_tasks():
    selected_labels = questionary.checkbox(
        "Tasks?",
        choices=[q["label"] for q in [
            {"id": "register", "label": "Create Accounts"},
            {"id": "claimBonus", "label": "Claim Bonus"},
            {"id": "getFreeBalance", "label": "Get Free Balance"},
            {"id": "checkBalance", "label": "Check Balance"},
            {"id": "update", "label": "Update Script"},
        ]],
        validate=lambda val: True if len(val) > 0 else "Select at least one task"
    ).ask()
    mapping = {"Create Accounts":"register","Claim Bonus":"claimBonus","Get Free Balance":"getFreeBalance","Check Balance":"checkBalance","Update Script":"update"}
    return [mapping[l] for l in selected_labels]

def prompt_num_accounts(max_allowed):
    return int(questionary.text(
        f"How many accounts? (1-{max_allowed})",
        validate=lambda val: True if val.isdigit() and 1 <= int(val) <= max_allowed else f"Enter 1-{max_allowed}"
    ).ask())

def prompt_max_concurrent(max_allowed):
    return int(questionary.text(
        f"How many concurrent workers? (1-{max_allowed})",
        validate=lambda val: True if val.isdigit() and 1 <= int(val) <= max_allowed else f"Enter 1-{max_allowed}"
    ).ask())

def prompt_balance_threshold(default=300):
    return float(questionary.text(
        f"Set balance threshold (default {default}):",
        default=str(default),
        validate=lambda val: True if val.replace(".","",1).isdigit() else "Masukkan angka valid"
    ).ask())

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    check_latest_version()
    base_url = prompt_base_url()
    tasks_selected = prompt_tasks()
    use_proxy = prompt_use_proxy()
    proxies = read_proxies() if use_proxy else []

    accounts_list = None
    max_allowed = None
    file_path = None
    balance_threshold = 300

    # Jika update saja
    if tasks_selected == ["update"]:
        asyncio.run(main_limited(
            base_url, tasks_selected,
            accounts_list, num_accounts=1,
            max_concurrent=1,
            proxies=proxies, file_name=None,
            balance_threshold=1
        ))
        exit(0)

    # Jika task getFreeBalance atau claimBonus dipilih, minta user pilih file
    if any(t in tasks_selected for t in ["getFreeBalance", "claimBonus", "checkBalance"]):
        file_path = prompt_file("./data/accounts", extensions=[".json", ".txt"])
        if file_path is None:
            print("Tidak ada file tersedia, keluar...")
            exit(1)

        # Load accounts dari file
        if file_path.suffix == ".json":
            accounts_list = load_json(file_path)
        else:
            # txt -> konversi ke json & simpan permanen
            accounts_list = txt_to_json_accounts(file_path)
            json_file = file_path.with_suffix(".json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(accounts_list, f, indent=4)
            print(f"File TXT dikonversi ke JSON dan disimpan: {json_file}")

        max_allowed = len(accounts_list)
    else:
        max_allowed = 1000000  # practically unlimited jika tidak ada akun list

    if "checkBalance" in tasks_selected:
        balance_threshold = prompt_balance_threshold(300)

    if max_allowed is None:
        max_allowed = 1000000

    num_accounts = prompt_num_accounts(max_allowed)
    max_concurrent = prompt_max_concurrent(num_accounts)

    asyncio.run(main_limited(
        base_url, tasks_selected,
        accounts_list, num_accounts=num_accounts,
        max_concurrent=max_concurrent,
        proxies=proxies, file_name=file_path,
        balance_threshold=balance_threshold
    ))
