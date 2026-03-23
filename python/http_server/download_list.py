import hashlib
from pathlib import Path
from typing import List, Dict

FOLDER_PATH = Path("/home/alex/Prj/2_dev/python/autotest_lbosse/http_server_with_rate_limit/static")
BASE_URL = "http://192.168.208.199:62000/download"
RATE = 100*1024*1024

def file_md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    md5 = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            md5.update(chunk)
    return md5.hexdigest()

def build_download_list(folder: Path) -> List[Dict[str, str]]:
    result = []

    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file():
            continue

        md5 = file_md5(file_path)

        url = f"{BASE_URL}/{file_path.name}?rate={RATE}"

        result.append({
            "url": url,
            "md5": md5,
        })

    return result


if __name__ == "__main__":
    download_list = build_download_list(FOLDER_PATH)

    print("\nDOWNLOAD_LIST = [")
    for item in download_list:
        print("    {")
        print(f'        "url": "{item["url"]}",')
        print(f'        "md5": "{item["md5"]}",')
        print("    },")
    print("]")