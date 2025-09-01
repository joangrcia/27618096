import questionary
import asyncio
import random
import sys
import itertools
from tasks import do_auth, run_get_free_balance_async, sanitize_filename
from extras import read_file, read_proxies, random_number, load_json, check_latest_version

async def spinner_task(line, account, state_event):
    spinner = itertools.cycle("|/-\\")
    while not state_event["done"]:
        print(f"\033[{line};0H[ {next(spinner)} ] [{account}] {state_event['msg']}", end="", flush=True)
        await asyncio.sleep(0.1)
    print(f"\033[{line};0H[✓] [{account}] {state_event['msg']}{' ' * 20}", flush=True)

proxies_result = []

total_accounts = 0

TASK_OPTIONS = [
    {"id": "register", "label": "Create Accounts"},
    {"id": "claimBonus", "label": "Claim Bonus"},
    {"id": "getFreeBalance", "label": "Get Free Balance"},
    {"id": "checkBalance", "label": "Check Balance"},
    {"id": "update", "label": "Update Script"},
]

def prompt_base_url():
    items = read_file()
    if items:
        selected = questionary.select(
            "baseUrl?",
            choices=items
        ).ask()
        return selected

def prompt_account_creation():
    return int(questionary.text(
        "How many accounts do you want to create?",
        validate=lambda val: True if val.isdigit() and int(val) > 0 else "Enter at least 1"
    ).ask())

def prompt_use_proxy():
    return questionary.confirm("Use proxy?", default=True).ask()

def prompt_thread_count(max_allowed):
    return int(questionary.text(
        f"How many threads do you want to run? (Max {max_allowed})",
        validate=lambda val: (
            True if val.isdigit() and 0 < int(val) <= max_allowed else f"Enter 1-{max_allowed}"
        )
    ).ask())

def prompt_tasks():
    selected_labels = questionary.checkbox(
        "Tasks?",
        choices=[q["label"] for q in TASK_OPTIONS],
        validate=lambda val: True if len(val) > 0 else "You must select at least one task"
    ).ask()
    selected_ids = [q["id"] for q in TASK_OPTIONS if q["label"] in selected_labels]
    return selected_ids

async def worker(semaphore, base_url, username, proxies, tasks_selected, line):
    async with semaphore:
        proxy = random.choice(proxies) if proxies else ""
        state_event = {"msg": "waiting...", "done": False}
        spinner = asyncio.create_task(spinner_task(line, username, state_event))

        results = {}

        # Loop per task yang dipilih
        for task in tasks_selected:
            if task == "register":
                state_event["msg"] = "Registering..."
                auth_result = await do_auth(base_url, username, username, "register", proxy)
                results["register"] = auth_result
                state_event["msg"] = f"createAccount: {auth_result.get('message','')}"
                await asyncio.sleep(0.2)

            elif task == "getFreeBalance":
                state_event["msg"] = "Getting Free Balance..."
                filename = sanitize_filename(base_url)
                accounts_list = load_json(filename)
                total_accounts = len(accounts_list)
                idx = line - 11
                if idx < len(accounts_list):
                    sid = accounts_list[idx]["sid"]
                    username_acc = accounts_list[idx]["username"]
                    next_roulette_str = accounts_list[idx].get("next_roulette", "")
                    run_task = True

                    if next_roulette_str:
                        try:
                            from datetime import datetime
                            next_dt = datetime.strptime(next_roulette_str, "%Y-%m-%d")
                            today = datetime.today()
                            if today < next_dt:
                                run_task = False
                                state_event["msg"] = f"FreeBalance: Next spin {next_roulette_str}"
                        except:
                            pass

                    if run_task:
                        try:
                            balance_result = await run_get_free_balance_async(sid, username_acc, base_url)
                            results["getFreeBalance"] = balance_result
                            state_event["msg"] = f"FreeBalance: {balance_result.get('message','')}"
                        except Exception as e:
                            state_event["msg"] = f"FreeBalance Error: {e}"
                else:
                    state_event["msg"] = "No SID available for FreeBalance"


            elif task == "claimBonus":
                state_event["msg"] = "Claiming Bonus..."
                # TODO: jalankan fungsi claim bonus async
                await asyncio.sleep(0.5)
                state_event["msg"] = "Bonus claimed (dummy)"

            elif task == "checkBalance":
                state_event["msg"] = "Checking Balance..."
                # TODO: jalankan fungsi check balance async
                await asyncio.sleep(0.5)
                state_event["msg"] = "Balance checked (dummy)"

            elif task == "update":
                state_event["msg"] = "Updating Script..."
                # TODO: jalankan update script
                await asyncio.sleep(0.5)
                state_event["msg"] = "Script updated (dummy)"

        state_event["done"] = True
        await spinner
        return results


async def main_limited(base_url, tasks_selected, total_accounts=10, max_concurrent=2, proxies=None):
    semaphore = asyncio.Semaphore(max_concurrent)
    print("\n" * 10)
    sys.stdout.flush()
    start_line = 11
    tasks = []
    for i in range(total_accounts):
        if "getFreeBalance" in tasks_selected and accounts_list:
            account_data = accounts_list[i]
            username = account_data["username"]
        else:
            username = random_number()
        line = start_line + i
        tasks.append(
            asyncio.create_task(
                worker(semaphore, base_url, username, r_proxies, p_tasks, line)
            )
        )

    results = await asyncio.gather(*tasks)
    total_success = sum(r.get("register", {}).get("success",0) for r in results)
    total_fail = sum(r.get("register", {}).get("fail",0) for r in results)


    info_line = start_line + total_accounts + 1
    print(f"\033[{info_line};0H==========TASK INFO===========")
    print(f"\033[{info_line+1};0HSuccess: {total_success} | Failed: {total_fail}")
    print(f"\033[{info_line+2};0H==============================")



if __name__ == "__main__":
    check_latest_version()
    base_url = prompt_base_url()
    p_tasks = prompt_tasks()
    p_proxy = prompt_use_proxy()
    r_proxies = []

    if p_proxy:
        proxies = read_proxies()
        if not proxies:
            print("No proxies found. Proceeding without proxies.")
        else:
            r_proxies.extend(proxies)
            print(f"{len(r_proxies)} proxies loaded.")

    if "register" in p_tasks:
        p_acc_creations = prompt_account_creation()
        p_thread_count = prompt_thread_count(max_allowed=p_acc_creations)
    elif "getFreeBalance" in p_tasks:
        filename = sanitize_filename(base_url)
        accounts_list = load_json(filename)
        total_accounts = len(accounts_list)
        p_acc_creations = total_accounts
        p_thread_count = prompt_thread_count(max_allowed=total_accounts)

    asyncio.run(
        main_limited(
            base_url,
            tasks_selected=p_tasks,
            total_accounts=p_acc_creations,
            max_concurrent=p_thread_count,
            proxies=r_proxies,
        )
    )
