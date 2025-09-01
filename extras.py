import questionary
import os
import json
import random
import re
from pathlib import Path
from datetime import datetime

import subprocess

FILENAME = "baseurl.txt"

# --- Fungsi CRUD ---
def read_file():
    if not os.path.exists(FILENAME):
        return []
    with open(FILENAME, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()]

def write_file(lines):
    with open(FILENAME, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def create_item(item):
    lines = read_file()
    lines.append(item)
    write_file(lines)

def update_item(index, new_item):
    lines = read_file()
    if 0 <= index < len(lines):
        lines[index] = new_item
        write_file(lines)
        return True
    return False

def delete_item(index):
    lines = read_file()
    if 0 <= index < len(lines):
        removed = lines.pop(index)
        write_file(lines)
        return removed
    return None

def read_proxies(file_path="proxies.txt"):
    with open(file_path, "r") as f:
        return [line.strip() for line in f if line.strip()]
    
def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

def append_json(new_data, filename="accounts.json"):
    file_path = Path(filename)
    if file_path.exists():
        with file_path.open("r+", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except:
                data = []
            data.append(new_data)
            f.seek(0)
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.truncate()
    else:
        with file_path.open("w", encoding="utf-8") as f:
            json.dump([new_data], f, ensure_ascii=False, indent=4)

def update_next_roulette(filename, username, next_time_ms):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return False

    updated = False
    for account in data:
        if account.get("username") == username:
            # konversi ke format YYYY-MM-DD
            from datetime import datetime
            try:
                ts_s = int(next_time_ms) / 1000
                dt = datetime.fromtimestamp(ts_s)
                account["next_roulette"] = dt.strftime("%Y-%m-%d")
            except:
                account["next_roulette"] = "-"
            updated = True
            break

    if updated:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    return updated

def random_number():
    prefixes = [
        "811","812","813","821","822","823",
        "814","815","816","855","856",
        "817","818","819","877","878","879"
    ]
    prefix = random.choice(prefixes)
    suffix = "".join(str(random.randint(0, 9)) for _ in range(8))
    return prefix + suffix

def sanitize_filename(s):
    domain = re.sub(r'^https?://(www\.)?', '', s)  # hilang https:// dan www.
    domain = domain.split(".")[0]  # ambil bagian sebelum titik pertama
    return f"account({domain}).json"

def time_format(next_time_ms):
    try:
        ts_s = int(next_time_ms) / 1000
        dt = datetime.fromtimestamp(ts_s)
        return dt.strftime("%Y-%m-%d")  # cuma tahun-bulan-tanggal
    except Exception:
        return "-"
    
def check_latest_version():
    try:
        subprocess.run(["git", "fetch", "origin"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        local_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        remote_commit = subprocess.check_output(["git", "rev-parse", f"origin/{branch}"]).decode().strip()
        remote_msg = subprocess.check_output(["git", "log", "-1", "--pretty=%B", f"origin/{branch}"]).decode().strip()

        if local_commit == remote_commit:
            print(f"✅ Script sudah yang terbaru (Branch: {branch}, Commit: {local_commit[:7]})\n")
        else:
            print(f"⚠️ Update tersedia! (Branch: {branch})\n")
            print(f"   Commit terakhir di remote: {remote_commit[:7]} - {remote_msg}\n")

    except Exception as e:
        print(f"⚠️ Tidak bisa cek versi: {e}")
        

# --- Prompt interaktif ---
def crud_prompt():
    while True:
        action = questionary.select(
            "Pilih aksi:",
            choices=["Lihat", "Tambah", "Update", "Hapus", "Keluar"]
        ).ask()

        items = read_file()
        if action == "Lihat":
            if items:
                selected = questionary.select(
                    "Pilih item untuk lihat:",
                    choices=items
                ).ask()
                print(f"\nItem yang dipilih: {selected}")
            else:
                print("Data kosong.")
        elif action == "Tambah":
            new_item = questionary.text("Masukkan data baru:").ask()
            create_item(new_item)
            print("Berhasil ditambahkan.")
        elif action == "Update":
            if not items:
                print("Data kosong, tidak bisa update.")
                continue
            selected = questionary.select(
                "Pilih item untuk update:",
                choices=[f"{i}: {item}" for i, item in enumerate(items)]
            ).ask()
            index = int(selected.split(":")[0])
            new_value = questionary.text("Masukkan data baru:").ask()
            if update_item(index, new_value):
                print("Berhasil diupdate.")
            else:
                print("Index tidak valid.")
        elif action == "Hapus":
            if not items:
                print("Data kosong, tidak bisa hapus.")
                continue
            selected = questionary.select(
                "Pilih item untuk hapus:",
                choices=[f"{i}: {item}" for i, item in enumerate(items)]
            ).ask()
            index = int(selected.split(":")[0])
            removed = delete_item(index)
            if removed:
                print(f"Berhasil menghapus: {removed}")
            else:
                print("Index tidak valid.")
        elif action == "Keluar":
            break
        print("-" * 30)

if __name__ == "__main__":
    crud_prompt()
