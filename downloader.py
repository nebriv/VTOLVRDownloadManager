import requests
from bs4 import BeautifulSoup
import logging
import os
import re
import fleep
from pyunpack import Archive
import datetime
import json
from distutils.util import strtobool
import shutil
import vdf
from distutils.version import LooseVersion, StrictVersion

logger = logging.getLogger(__name__)

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

try:
    import winreg

    proc_arch = os.environ['PROCESSOR_ARCHITECTURE'].lower()
    proc_arch64 = os.environ['PROCESSOR_ARCHITEW6432'].lower()

    if proc_arch == 'x86' and not proc_arch64:
        arch_keys = {0}
    elif proc_arch == 'x86' or proc_arch == 'amd64':
        arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
    else:
        raise Exception("Unhandled arch: %s" % proc_arch)
except ImportError as err:
    winreg = False
    logging.error("Unable to import winreg, will not be able to auto detect steam location")

def exists_or_make(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_file_type(file):
    with open(file, "rb") as file:
        info = fleep.get(file.read(128))
        print(info.mime)

def find_vtol_map_root(directory):
    map_extensions = ['.vtm']
    for dir in os.walk(directory):
        for file in dir[2]:
            if any(extension in file for extension in map_extensions):
                return dir[0]
    return False

def find_vtol_campaign_root(directory):
    campaign_extensions = ['.vtc']
    for dir in os.walk(directory):
        for file in dir[2]:
            if any(extension in file for extension in campaign_extensions):
                return dir[0]
    return False

def find_vtol_mission_root(directory):
    mission_extensions = ['.vts']
    for dir in os.walk(directory):
        for file in dir[2]:
            if any(extension in file for extension in mission_extensions):
                return dir[0]
    return False

def auto_discover_vtol_dir():
    logging.info("Autodetecting VTOL VR directory...")
    if winreg:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Valve\\Steam")
        value = winreg.QueryValueEx(key, "SteamPath")[0]

        steam_config = os.path.join(value, "config", "config.vdf")

        json_data = open(steam_config).read()
        data = vdf.loads(json_data)

        steam_libraries = []

        for each in data['InstallConfigStore']['Software']['Valve']['Steam']:
            if "BaseInstallFolder" in each:
                steam_libraries.append(data['InstallConfigStore']['Software']['Valve']['Steam'][each])

        for each in steam_libraries:
            for folder in os.walk(os.path.join(each, "steamapps", "common")):
                if "VTOL VR" in folder[0]:
                    logging.info("Found VTOL VR HERE: %s" % folder[0])
                    return folder[0]
    else:
        raise ModuleNotFoundError("WinReg is missing, unable to autodetect steam install location")

def copy(src, dst):
    import os
    import shutil

    for src_dir, dirs, files in os.walk(src):
        dst_dir = src_dir.replace(src, dst, 1)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        for file_ in files:
            src_file = os.path.join(src_dir, file_)
            dst_file = os.path.join(dst_dir, file_)
            if os.path.exists(dst_file):
                # in case of the src and dst are the same file
                if os.path.samefile(src_file, dst_file):
                    continue
                os.remove(dst_file)
            shutil.move(src_file, dst_dir)

class XenForo:
    def __init__(self, url):
        self.url = url

    def _get_page(self, url):
        logging.debug("Fetching URL: %s" % url)
        data = requests.get(url)
        if data.ok:
            return data.content
        else:
            logging.error("Error downloading data from %s" % url)
            raise ConnectionError("Error downloading data from %s" % url)

    def _get_resource_details(self, resource_page):
        details_page = self._get_page(resource_page)
        soup = BeautifulSoup(details_page, 'html.parser')

        download_link = soup.find("label", {"class":"downloadButton"}).find("a")['href']

        download_link = self.url + download_link

        description = soup.find("li", {"class":"primaryContent"}).find("article").text.strip()

        category = soup.find("dl", {"class":"resourceCategory"}).text.split("Category:")[1].strip()

        details = {"download_link": download_link, "description": description, "category": category}

        return details

    def _parse_resources_list(self, data, resource_type, get_details=True):
        soup = BeautifulSoup(data, 'html.parser')
        resources = soup.find_all("li", {"class": "resourceListItem"})
        parsed_resources = []
        for each in resources:
            resource_image = each.find("div", {"class": "resourceImage"})
            resource_main = each.find("div", {"class": "main"})
            resource_stats = each.find("div", {"class": "resourceStats"})

            resource_type = resource_type

            title_block = resource_main.find("h3", {"class":"title"})
            title = title_block.find("a").text
            resource_link = title_block.find("a")['href']
            version = title_block.find("span", {"class":"version"}).text
            author = resource_main.find("a", {"class":"username"}).text
            tag_line = resource_main.find("div",{"class":"tagLine"}).text.replace("\t","").replace("\n","")

            image_url = resource_image.find("a", {"class":"resourceIcon"})['href']

            rating = resource_stats.find("span", {"class":"ratings"})['title']
            downloads = resource_stats.find("dl", {"class": "resourceDownloads"}).text.split("Downloads: ")[1]
            last_updated = resource_stats.find("dl", {"class": "resourceUpdated"}).text.split("Updated: ")[1]

            logging.debug("Getting resource details page: %s" % resource_link)
            details = self._get_resource_details(self.url + resource_link)

            resource = {"resource_type": resource_type,
                        "title": title,
                        "image_url": image_url,
                        "author": author,
                        "tag_line": tag_line,
                        "cur_version": version,
                        "link": self.url + "%s" % resource_link,
                        "rating": rating,
                        "downloads": downloads,
                        "last_updated": last_updated,
                        "details": details}
            parsed_resources.append(resource)

        return parsed_resources

    def get_resources(self, page, resource_type="Not Specified"):
        results = self._get_page(self.url + page)
        parsed = self._parse_resources_list(results, resource_type)
        return parsed

class Syncer:
    def __init__(self, vtolvr_dir, url, download_directory="temp"):
        self.vtolvr_dir = vtolvr_dir
        self.vtolvrmissions_url = url
        self.xen = XenForo(self.vtolvrmissions_url)
        self.online_resources = {"campaigns": [], "missions": [], "maps": []}
        self.download_dir = download_directory

        self.campaigns_directory = os.path.join(self.download_dir, "campaigns")
        self.missions_directory = os.path.join(self.download_dir, "missions")
        self.maps_directory = os.path.join(self.download_dir, "maps")
        self.others_directory = os.path.join(self.download_dir, "others")

        exists_or_make(self.campaigns_directory)
        exists_or_make(self.missions_directory)
        exists_or_make(self.maps_directory)
        exists_or_make(self.others_directory)

    def download_resource(self, resource):
        #print(resource['resource_type'])

        r = requests.get(resource['details']['download_link'], stream=True)
        d = r.headers['content-disposition']
        fname = re.findall("filename=(.+)", d)[0].strip("\"")

        if resource['resource_type'] == "map":
            download_file = os.path.join(self.maps_directory, fname)
        elif resource['resource_type'] == "mission":
            download_file = os.path.join(self.missions_directory, fname)
        elif resource['resource_type'] == "campaign":
            download_file = os.path.join(self.campaigns_directory, fname)
        else:
            download_file = os.path.join(self.others_directory, fname)

        if r.status_code == 200:
            with open(download_file, 'wb') as f:
                for chunk in r:
                    f.write(chunk)

        if os.path.exists(download_file):

            output_folder = ".".join(download_file.split(".")[:-1]).split(os.sep)[-1]
            if resource['resource_type'] == "map":
                zip_dir = os.path.join(self.maps_directory,output_folder)
            elif resource['resource_type'] == "mission":
                zip_dir = os.path.join(self.missions_directory, output_folder)
            elif resource['resource_type'] == "campaign":
                zip_dir = os.path.join(self.campaigns_directory, output_folder)
            else:
                zip_dir = os.path.join(self.others_directory, output_folder)


            logging.info("Downloading and unzipping %s" % download_file)
            Archive(download_file).extractall(zip_dir, auto_create_dir=True)

            resource_metadata = {"resource_name": resource['title'],
                                 "resource_type": resource['resource_type'],
                                 "resource_source": resource['link'],
                                 "version": resource['cur_version'],
                                 "download_date": datetime.datetime.now(),
                                 "download_source": resource['details']['download_link'],
                                 }

            # Extracting the root folder (if someone uploads a nested file or something, we only want the one containing the correct data
            if resource['resource_type'] == "map":
                root = find_vtol_map_root(zip_dir)
                if root:
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))

                    resource_name = root.split(os.sep)[-1]
                    move_path = os.path.join(self.vtolvr_dir, "CustomMaps", resource_name)
                    if strtobool(input("Move %s to VTOL VR Directory (%s)? This will overwrite current data. (Y/N) " % (root, move_path))):
                        copy(root, move_path)
                        logging.info("Done moving %s... cleaning up temp" % root)
                        shutil.rmtree(zip_dir)
                        os.remove(download_file)
                else:
                    logging.error("There is an error parsing the VTOL VR Map files. No map data found within download.")
            elif resource['resource_type'] == "campaign":
                root = find_vtol_campaign_root(zip_dir)
                if root:
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))

                    resource_name = root.split(os.sep)[-1]
                    move_path = os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", resource_name)
                    if strtobool(input("Move %s to VTOL VR Directory (%s)? This will overwrite current data. (Y/N) " % (root, move_path))):
                        copy(root, move_path)
                        logging.info("Done moving %s... cleaning up temp" % root)
                        shutil.rmtree(zip_dir)
                        os.remove(download_file)

                else:
                    logging.error("There is an error parsing the VTOL VR Campaign files. No campaign data found within download.")
            elif resource['resource_type'] == "mission":
                root = find_vtol_mission_root(zip_dir)



                if root:
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))
                    resource_name = root.split(os.sep)[-1]
                    move_path = os.path.join(self.vtolvr_dir, "CustomScenarios", resource_name)
                    if strtobool(input("Move %s to VTOL VR Directory (%s)? This will overwrite current data. (Y/N) " % (root, move_path))):
                        copy(root, move_path)
                        logging.info("Done moving %s... cleaning up temp" % root)
                        shutil.rmtree(zip_dir)
                        os.remove(download_file)
                else:
                    logging.error("There is an error parsing the VTOL VR Mission files. No mission data found within download.")

    def download_all_campaigns(self):
        for campaign in self.online_resources['campaigns']:
            self.download_resource(campaign)

    def download_all_missions(self):
        for mission in self.online_resources['missions']:
            self.download_resource(mission)

    def download_all_maps(self):
        for map in self.online_resources['maps']:
            self.download_resource(map)

    def get_local_maps(self):
        logging.info("Looking for local VTOLVRMissions.com maps")
        maps = []
        for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomMaps")):
            map = folder
            maps.append(map)

            self.downloaded_maps = []
        no_metadata_maps = []
        for map in maps:
            if "CustomMaps" != map:
                if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomMaps", map, "vtolvrmissions.com_metadata.json")):
                    with open(os.path.join(self.vtolvr_dir, "CustomMaps", map, "vtolvrmissions.com_metadata.json")) as json_file:
                        metadata = json.load(json_file)
                        self.downloaded_maps.append({"location":map, "metadata":metadata})
                else:
                    no_metadata_maps.append(map)

        for each in self.downloaded_maps:
            logging.info("Found downloaded map (%s): %s (ver. %s) - downloaded on %s" % (each['location'], each['metadata']['resource_name'], each['metadata']['version'], each['metadata']['download_date']))

        for each in no_metadata_maps:
            logging.debug("Found unmanaged map: %s" % each)

    def get_local_missions(self):
        logging.info("Looking for local VTOLVRMissions.com missions")
        missions = []
        for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios")):
            mission = folder
            missions.append(mission)

            self.downloaded_missions = []
        no_metadata_missions = []
        for mission in missions:
            if "CustomScenarios" != mission and "Campaigns" != mission:
                if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", mission, "vtolvrmissions.com_metadata.json")):
                    with open(os.path.join(self.vtolvr_dir, "CustomScenarios", mission, "vtolvrmissions.com_metadata.json")) as json_file:
                        metadata = json.load(json_file)
                        self.downloaded_missions.append({"location":mission, "metadata":metadata})
                else:
                    no_metadata_missions.append(mission)

        for each in self.downloaded_missions:
            logging.info("Found downloaded mission (%s): %s (ver. %s) - downloaded on %s" % (each['location'], each['metadata']['resource_name'], each['metadata']['version'], each['metadata']['download_date']))

        for each in no_metadata_missions:
            logging.debug("Found unmanaged mission: %s" % each)

    def get_local_campaigns(self):
        logging.info("Looking for local VTOLVRMissions.com Campaigns")
        campaigns = []
        for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns")):
            campaign = folder
            campaigns.append(campaign)

        self.downloaded_campaigns = []
        no_metadata_campaigns = []
        for campaign in campaigns:
            if "Campaigns" != campaign:
                if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign, "vtolvrmissions.com_metadata.json")):
                    with open(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign, "vtolvrmissions.com_metadata.json")) as json_file:
                        metadata = json.load(json_file)
                        self.downloaded_campaigns.append({"location":campaign, "metadata":metadata})
                else:
                    no_metadata_campaigns.append(campaign)

        for each in self.downloaded_campaigns:
            logging.info("Found downloaded campaign (%s): %s (ver. %s) - downloaded on %s" % (each['location'], each['metadata']['resource_name'], each['metadata']['version'], each['metadata']['download_date']))

        for each in no_metadata_campaigns:
            logging.debug("Found unmanaged campaign: %s" % each)

    def check_for_updates(self):
        logging.info("Checking maps for updates...")
        for each in self.downloaded_maps:
            #print(each)
            online = next(item for item in self.online_resources['maps'] if item["title"] == each['metadata']['resource_name'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    if strtobool(input("%s is out of date (current ver: %s - latest ver: %s). Update now? (y/n)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))):
                        self.download_resource(online)
                else:
                    logging.info("%s is up to date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

        logging.info("Checking campaigns for updates...")
        for each in self.downloaded_campaigns:
            online = next(item for item in self.online_resources['campaigns'] if item["title"] == each['metadata']['resource_name'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    logging.info("%s is out of date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))
                else:
                    logging.info("%s is up to date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

        logging.info("Checking missions for updates...")
        for each in self.downloaded_missions:
            online = next(item for item in self.online_resources['missions'] if item["title"] == each['metadata']['resource_name'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    logging.info("%s is out of date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))
                else:
                    logging.info("%s is up to date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))


    def get_online_all(self):
        self.get_online_campaigns()
        self.get_online_missions()
        self.get_online_maps()

    def get_online_missions(self):
        logging.info("Getting Available Missions from %s" % self.vtolvrmissions_url)
        results = self.xen.get_resources("resources/categories/missions.6/", resource_type="mission")
        if results:
            self.online_resources['missions'] = results

    def get_online_campaigns(self):
        logging.info("Getting Available Campaigns from %s" % self.vtolvrmissions_url)
        results = self.xen.get_resources("resources/categories/campaigns.3/", resource_type="campaign")
        if results:
            self.online_resources['campaigns'] = results

    def get_online_maps(self):
        logging.info("Getting Available Maps from %s" % self.vtolvrmissions_url)
        results = self.xen.get_resources("resources/categories/maps.10", resource_type="map")
        if results:
            self.online_resources['maps'] = results

    def print_online_maps(self):
        print("vtolvrmissions.com - Maps")
        if len(self.online_resources['maps']) > 0:
            for each in self.online_resources['maps']:
                print(each['title'])

    def print_online_missions(self):
        print("vtolvrmissions.com - Missions")
        if len(self.online_resources['missions']) > 0:
            for each in self.online_resources['missions']:
                print(each['title'])

    def print_online_campaigns(self):
        print("vtolvrmissions.com - Campaigns")
        if len(self.online_resources['campaigns']) > 0:
            for each in self.online_resources['campaigns']:
                print(each['title'])

    def print_online_all(self):
        self.print_online_campaigns()
        self.print_online_maps()
        self.print_online_missions()

steam_dir = auto_discover_vtol_dir()

vtol_sync = Syncer(steam_dir, "https://www.vtolvrmissions.com/")

vtol_sync.get_local_maps()
vtol_sync.get_local_campaigns()
vtol_sync.get_local_missions()
#
vtol_sync.get_online_all()

vtol_sync.check_for_updates()
exit()
# vtol_sync.print_online_all()
vtol_sync.download_all_campaigns()
vtol_sync.download_all_maps()