import requests
from distutils.version import LooseVersion, StrictVersion
import logging


update_url = "https://api.github.com/repos/nebriv/VTOLVRDownloadManager/releases/latest"
def check_updates(cur_version, url=update_url):
    logging.info("Checking for updates...")
    r = requests.get(url)
    if r.ok:
        release_info = r.json()
        if "tag_name" in release_info:
            if LooseVersion(cur_version) < LooseVersion(release_info['tag_name']):
                for each in release_info['assets']:
                    if each['name'] == "VTOLVRMissionDownloader.exe":
                        return {"version": release_info['tag_name'], "browse_url": release_info['html_url'], "download_url": each['browser_download_url']}
    return False



def main():
    print(check_updates("v1.0"))





if __name__ == '__main__':
    main()
