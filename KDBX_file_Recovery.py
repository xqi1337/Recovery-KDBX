import os
import sys
from tqdm import tqdm
from prettytable import PrettyTable
import threading
import queue
import uuid

KDBX_SIGNATURE = b'\x03\xd9\xa2\x9a\x67\xfb\x4b\xb5'
SIGNATURE_SIZE = len(KDBX_SIGNATURE)
BLOCK_SIZE = 4096
CACHE_SIZE = 30 * 1024 * 1024

def generate_unique_filename(save_path, index):
    unique_id = uuid.uuid4()
    filename = f"recovered_{index}_{unique_id}.kdbx"
    return os.path.join(save_path, filename)

def save_kdbx_file(data, save_path, file_index, position):
    try:
        max_size = 30 * 1024 * 1024
        data = data[:max_size]
        file_save_path = generate_unique_filename(save_path, file_index)
        with open(file_save_path, "wb") as output_file:
            output_file.write(data)
        return file_save_path
    except Exception as e:
        print(f"Fehler beim Speichern der KDBX-Datei an Position {position}: {e}")
        return None

def worker(task_queue, result_list, save_path, results_lock, save_pbar):
    while True:
        try:
            file_index, position, data = task_queue.get(timeout=3)
        except queue.Empty:
            break
        file_save_path = save_kdbx_file(data, save_path, file_index, position)
        if file_save_path:
            with results_lock:
                result_list.append((file_index, position, file_save_path))
            print(f"KDBX-Datei gespeichert: {file_save_path}")
        task_queue.task_done()
        save_pbar.update(1)

def search_kdbx_on_disk(disk_path, save_path, result_list, task_queue, save_pbar, results_lock):
    try:
        disk_size = os.path.getsize(disk_path)
    except Exception as e:
        print(f"Fehler beim Abrufen der Festplattengröße: {e}")
        return

    try:
        with open(disk_path, 'rb') as disk, tqdm(total=disk_size, unit='B', unit_scale=True, desc='Scanning disk') as scan_pbar:
            buffer = b''
            file_index = 0
            while True:
                block = disk.read(BLOCK_SIZE)
                if not block:
                    break
                scan_pbar.update(len(block))
                buffer += block
                pos = 0
                while True:
                    signature_pos = buffer.find(KDBX_SIGNATURE, pos)
                    if signature_pos == -1:
                        break
                    absolute_position = disk.tell() - len(buffer) + signature_pos
                    print(f"\nKDBX-Signatur gefunden an Position {absolute_position} auf {disk_path}")
                    disk.seek(absolute_position)
                    data = disk.read(CACHE_SIZE)
                    if not data:
                        print(f"Keine Daten gelesen nach Position {absolute_position}.")
                        pos = signature_pos + SIGNATURE_SIZE
                        continue
                    task_queue.put((file_index, absolute_position, data))
                    print(f"Enqueued KDBX file {file_index} from position {absolute_position}")
                    file_index += 1
                    pos = signature_pos + SIGNATURE_SIZE
                if len(buffer) > SIGNATURE_SIZE:
                    buffer = buffer[-SIGNATURE_SIZE:]
    except Exception as e:
        print(f"Fehler beim Lesen der Festplatte {disk_path}: {e}")

def main():
    default_disk_path = "/dev/mapper/luks-1337"
    user_input = input(f"Bitte geben Sie den Pfad zur Festplatte ein (Standard: {default_disk_path}): ").strip()
    disk_path = user_input if user_input else default_disk_path
    save_path = "/root/dokumente"

    if not os.path.exists(save_path):
        try:
            os.makedirs(save_path)
            print(f"Verzeichnis erstellt: {save_path}")
        except Exception as e:
            print(f"Fehler beim Erstellen des Verzeichnisses {save_path}: {e}")
            sys.exit(1)

    result_list = []
    results_lock = threading.Lock()
    task_queue = queue.Queue()
    save_pbar = tqdm(total=0, desc="Saved KDBX Files", unit='files')
    pbar_lock = threading.Lock()

    num_workers = 4
    workers = []
    for _ in range(num_workers):
        t = threading.Thread(target=worker, args=(task_queue, result_list, save_path, results_lock, save_pbar))
        t.daemon = True
        t.start()
        workers.append(t)

    search_kdbx_on_disk(disk_path, save_path, result_list, task_queue, save_pbar, results_lock)
    task_queue.join()

    for t in workers:
        t.join()

    save_pbar.close()

    if result_list:
        table = PrettyTable()
        table.field_names = ["File Index", "Position", "Saved Path"]
        for res in result_list:
            table.add_row(res)
        print("\nErgebnisse:")
        print(table)
    else:
        print("Keine KDBX-Dateien erfolgreich wiederhergestellt.")

if __name__ == "__main__":
    main()