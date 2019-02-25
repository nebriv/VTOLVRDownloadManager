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

            resource_id = resource_link.split("/")[1]

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
                        "resource_id": resource_id,
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

        self.maps = []
        self.campaigns = []
        self.missions = []

    def parse_vtol_map_file(self, directory):
        for each in os.listdir(directory):
            if each.endswith(".vtm"):
                with open(os.path.join(directory, each)) as map_file:
                    lines = map_file.readlines()
                    if "VTMapCustom" in lines[0]:
                        for line in lines:
                            if "mapID = " in line:
                                map_id = line.split("mapID = ")[1].strip()
                                return map_id
        return False

    def parse_vtol_scenario_file(self, directory):
        for each in os.listdir(directory):
            if each.endswith(".vts"):
                with open(os.path.join(directory, each)) as map_file:
                    lines = map_file.readlines()
                    if "CustomScenario" in lines[0]:
                        for line in lines:
                            if "scenarioID = " in line:
                                scenario_id = line.split("scenarioID = ")[1].strip()
                                return scenario_id
        return False

    def parse_vtol_campaign_file(self, directory):
        for each in os.listdir(directory):
            if each.endswith(".vtc"):
                with open(os.path.join(directory, each)) as campaign_file:
                    campaign_lines = campaign_file.readlines()
                    if "CAMPAIGN" in campaign_lines[0]:
                        for line in campaign_lines:
                            if "campaignID = " in line:
                                campaign_id = line.split("campaignID = ")[1].strip()
                                return campaign_id
        return False

    def download_resource(self, resource):
        update = False
        if "local_location" in resource:
            if not self.new_version_check(resource):
                raise Exception("No updates available")
            else:
                update = True

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

        logging.info("Done downloading")

        if os.path.exists(download_file):
            output_folder = "vtolvrmissions.com_" + ".".join(download_file.split(".")[:-1]).split(os.sep)[-1]
            if resource['resource_type'] == "map":
                zip_dir = os.path.join(self.maps_directory,output_folder)
            elif resource['resource_type'] == "mission":
                zip_dir = os.path.join(self.missions_directory, output_folder)
            elif resource['resource_type'] == "campaign":
                zip_dir = os.path.join(self.campaigns_directory, output_folder)
            else:
                zip_dir = os.path.join(self.others_directory, output_folder)

            logging.info("Unzipping %s" % download_file)
            Archive(download_file).extractall(zip_dir, auto_create_dir=True)
            logging.info("Unzipped")

            resource_metadata = resource
            resource_metadata['download_date'] = datetime.datetime.now()
            resource_metadata['local_version'] = resource['cur_version']

            # Extracting the root folder (if someone uploads a nested file or something, we only want the one containing the correct data
            if resource['resource_type'] == "map":
                root = find_vtol_map_root(zip_dir)
                root_folder_name = root.split(os.sep)[-1]
                if root:
                    vtol_id = self.parse_vtol_map_file(root)
                    if vtol_id:
                        if self.get_resource_by_vtol_id(vtol_id, resource_type=resource['resource_type']) and not update:
                            logging.error("Map with same ID already exists")
                            raise ValueError("Map with same ID already exists at %s" % self.get_resource_by_vtol_id(vtol_id, resource_type=resource['resource_type'])['local_location'])
                        if root_folder_name != vtol_id:
                            raise ValueError("Map Folder and VTOL MAP ID do not match. This is likely an error in how the author packaged the resource.")
                        
                    resource_name = root_folder_name
                    move_path = os.path.join(self.vtolvr_dir, "CustomMaps", resource_name)
                    resource_metadata['local_location'] = move_path
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))
                    copy(root, move_path)
                    logging.info("Done moving %s... cleaning up temp" % root)
                    shutil.rmtree(zip_dir)
                    os.remove(download_file)
                else:
                    logging.error("There is an error parsing the VTOL VR Map files. No map data found within download.")
            elif resource['resource_type'] == "campaign":
                root = find_vtol_campaign_root(zip_dir)
                root_folder_name = root.split(os.sep)[-1]
                if root:
                    vtol_id = self.parse_vtol_campaign_file(root)
                    if vtol_id:
                        if self.get_resource_by_vtol_id(vtol_id, resource_type=resource['resource_type']) and not update:
                            logging.error("Campaign with same ID already exists")
                            raise ValueError("Campaign with same ID already exists at %s" % self.get_resource_by_vtol_id(vtol_id, resource_type=resource['resource_type'])['local_location'])
                        if root_folder_name != vtol_id:
                            raise ValueError("Campaign Folder and VTOL Campaign ID do not match. This is likely an error in how the author packaged the resource.")

                    resource_name = root_folder_name
                    move_path = os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", resource_name)
                    resource_metadata['local_location'] = move_path

                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))

                    copy(root, move_path)
                    logging.info("Done moving %s... cleaning up temp" % root)
                    shutil.rmtree(zip_dir)
                    os.remove(download_file)

                else:
                    logging.error("There is an error parsing the VTOL VR Campaign files. No campaign data found within download.")
            elif resource['resource_type'] == "mission":
                root = find_vtol_mission_root(zip_dir)
                if root:
                    vtol_id = self.parse_vtol_scenario_file(root)
                    root_folder_name = root.split(os.sep)[-1]
                    if vtol_id:
                        if self.get_resource_by_vtol_id(vtol_id, resource_type=resource['resource_type']) and not update:
                            logging.error("Mission with same ID already exists")
                            raise ValueError("Mission with same ID already exists at %s" % self.get_resource_by_vtol_id(vtol_id, resource_type=resource['resource_type'])['local_location'])
                        if root_folder_name != vtol_id:
                            raise ValueError("Mission Folder and VTOL Mission ID do not match. This is likely an error in how the author packaged the resource.")
                        
                            
                    resource_name = root_folder_name
                    move_path = os.path.join(self.vtolvr_dir, "CustomScenarios", resource_name)
                    resource_metadata['local_location'] = move_path
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))

                    copy(root, move_path)
                    logging.info("Done moving %s... cleaning up temp" % root)
                    shutil.rmtree(zip_dir)
                    os.remove(download_file)
                else:
                    logging.error("There is an error parsing the VTOL VR Mission files. No mission data found within download.")


    def get_resource_by_vtol_id(self, id, resource_type):
        if resource_type == "map":
            for map in self.maps:
                if "vtol_id" in map:
                    if id == map['vtol_id']:
                        return map

        elif resource_type == "mission":
            for mission in self.missions:
                if "vtol_id" in mission:
                    if id == mission['vtol_id']:
                        return mission
        elif resource_type == "campaign":
            for campaign in self.campaigns:
                if "vtol_id" in campaign:
                    if id == campaign['vtol_id']:
                        return campaign
        return False

    def get_resource_by_id(self, id):
        for campaign in self.campaigns:
            if id == campaign['resource_id']:
                return campaign

        for map in self.maps:
            if id == map['resource_id']:
                return map

        for mission in self.missions:
            if id == mission['resource_id']:
                return mission
        return False


    def replace_resource_by_id(self, id, replacement):
        for i, campaign in enumerate(self.campaigns):
            if id == campaign['resource_id']:
                self.campaigns[i] = replacement
                return True

        for i, map in enumerate(self.maps):
            if id == map['resource_id']:
                self.maps[i] = replacement
                return True

        for i, mission in enumerate(self.missions):
            if id == mission['resource_id']:
                self.missions[i] = replacement
                return True
        return False


    def download_all_campaigns(self):
        for campaign in self.online_resources['campaigns']:
            self.download_resource(campaign)

    def download_all_missions(self):
        for mission in self.online_resources['missions']:
            self.download_resource(mission)

    def download_all_maps(self):
        for map in self.online_resources['maps']:
            self.download_resource(map)

    def get_local_all(self):
        self.get_local_campaigns()
        self.get_local_maps()
        self.get_local_missions()

    def validate_local_metadata(self, metadata):
        if "title" in metadata and "local_version" in metadata and "local_location" in metadata:
            return True
        return False

    def remove_resource(self, resource):
        try:
            if "local_location" in resource:
                shutil.rmtree(resource['local_location'])
                return True
            return False
        except Exception as err:
            logging.error("Error while removing %s: %s" % (resource['title'], err))
            return False

    def get_local_maps(self):
        logging.info("Looking for local VTOLVRMissions.com maps")
        maps = []
        local = []
        try:
            for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomMaps")):
                map = folder
                maps.append(map)
                self.downloaded_maps = []
            no_metadata_maps = []
            for map in maps:
                if "CustomMaps" != map:
                    vtol_id = self.parse_vtol_map_file(os.path.join(self.vtolvr_dir, "CustomMaps", map))
                    if vtol_id:
                        if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomMaps", map, "vtolvrmissions.com_metadata.json")):
                            with open(os.path.join(self.vtolvr_dir, "CustomMaps", map, "vtolvrmissions.com_metadata.json")) as json_file:
                                metadata = json.load(json_file)
                                if self.validate_local_metadata(metadata):
                                    metadata['vtol_id'] = vtol_id
                                    metadata['managed'] = True
                                    if not self.get_resource_by_id(metadata['resource_id']):
                                        self.maps.append(metadata)
                                        local.append(metadata)
                                else:
                                    logging.error("Error parsing metadata for %s" % (os.path.join(self.vtolvr_dir, "CustomMaps", map)))
                        else:
                            metadata = {"local_location":os.path.join(self.vtolvr_dir, "CustomMaps", map), "vtol_id": vtol_id, "resource_type": "map", "managed": False, "resource_id": "N/A"}
                            if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                self.maps.append(metadata)
                                local.append(metadata)


            for each in local:
                if "local_version" in each:
                    logging.info("Found downloaded map (%s): %s (ver. %s) - downloaded on %s" % (each['local_location'], each['title'], each['local_version'], each['download_date']))
                else:
                    logging.info("Found unmanaged map: %s" % each)

        except FileNotFoundError as err:
            logging.error("Unable to find CustomMaps folder - bad steam directory? %s" % err)

    def get_local_missions(self):
        logging.info("Looking for local VTOLVRMissions.com missions")
        missions = []
        local = []
        try:
            for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios")):
                mission = folder
                missions.append(mission)
            no_metadata_maps = []
            for mission in missions:
                if "Campaigns" != mission:
                    vtol_id = self.parse_vtol_scenario_file(os.path.join(self.vtolvr_dir, "CustomScenarios", mission))
                    if vtol_id:
                        if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", mission, "vtolvrmissions.com_metadata.json")):
                            with open(os.path.join(self.vtolvr_dir, "CustomScenarios", mission, "vtolvrmissions.com_metadata.json")) as json_file:
                                metadata = json.load(json_file)
                                if self.validate_local_metadata(metadata):
                                    metadata['vtol_id'] = vtol_id
                                    metadata['managed'] = True
                                    if not self.get_resource_by_id(metadata['resource_id']):
                                        self.missions.append(metadata)
                                        local.append(metadata)
                                else:
                                    logging.error("Error parsing metadata for %s" % (os.path.join(self.vtolvr_dir, "CustomScenarios", mission)))
                        else:
                            metadata = {"local_location":os.path.join(self.vtolvr_dir, "CustomScenarios", mission), "vtol_id": vtol_id, "resource_type": "mission", "managed": False, "resource_id": "N/A"}
                            if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                self.missions.append(metadata)
                                local.append(metadata)

            for each in local:
                if "local_version" in each:
                    logging.info("Found downloaded mission (%s): %s (ver. %s) - downloaded on %s" % (each['local_location'], each['title'], each['local_version'], each['download_date']))
                else:
                    logging.info("Found unmanaged mission: %s" % each)
        except FileNotFoundError as err:
            logging.error("Unable to find CustomScenarios folder - bad steam directory? %s" % err)

        # logging.info("Looking for local VTOLVRMissions.com missions")
        # missions = []
        # try:
        #     for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios")):
        #         mission = folder
        #         missions.append(mission)
        #
        #         self.downloaded_missions = []
        #     no_metadata_missions = []
        #     for mission in missions:
        #         if "CustomScenarios" != mission and "Campaigns" != mission:
        #             vtol_id = self.parse_vtol_scenario_file(os.path.join(self.vtolvr_dir, "CustomScenarios", mission))
        #             if vtol_id:
        #                 if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", mission, "vtolvrmissions.com_metadata.json")):
        #                     with open(os.path.join(self.vtolvr_dir, "CustomScenarios", mission, "vtolvrmissions.com_metadata.json")) as json_file:
        #                         metadata = json.load(json_file)
        #                         metadata['vtol_id'] = vtol_id
        #                         self.missions.append(metadata)
        #                         self.downloaded_missions.append(metadata)
        #                 else:
        #                     no_metadata_missions.append(mission)
        #
        #     for each in self.downloaded_missions:
        #         logging.info("Found downloaded mission (%s): %s (ver. %s) - downloaded on %s" % (each['location'], each['metadata']['title'], each['metadata']['local_version'], each['metadata']['download_date']))
        #
        #     for each in no_metadata_missions:
        #         logging.debug("Found unmanaged mission: %s" % each)
        # except FileNotFoundError as err:
        #     logging.error("Unable to find CustomScenarios folder - bad steam directory? %s" % err)

    def get_local_campaigns(self):
        logging.info("Looking for local VTOLVRMissions.com campaigns")
        campaigns = []
        local = []
        try:
            for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns")):
                campaign = folder
                campaigns.append(campaign)
            for campaign in campaigns:
                if "Campaigns" != campaign:
                    vtol_id = self.parse_vtol_campaign_file(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign))
                    if vtol_id:
                        if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign, "vtolvrmissions.com_metadata.json")):
                            with open(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign, "vtolvrmissions.com_metadata.json")) as json_file:
                                metadata = json.load(json_file)
                                if self.validate_local_metadata(metadata):
                                    metadata['vtol_id'] = vtol_id
                                    metadata['managed'] = True
                                    if not self.get_resource_by_id(metadata['resource_id']):
                                        self.campaigns.append(metadata)
                                        local.append(metadata)
                                else:
                                    logging.error("Error parsing metadata for %s" % (os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign)))
                        else:
                            metadata = {"local_location":os.path.join(self.vtolvr_dir, "CustomScenarios""Campaigns", campaign), "vtol_id": vtol_id, "resource_type": "mission", "managed": False, "resource_id": "N/A"}
                            if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                self.campaigns.append(metadata)
                                local.append(metadata)

            for each in local:
                if "local_version" in each:
                    logging.info("Found downloaded mission (%s): %s (ver. %s) - downloaded on %s" % (each['local_location'], each['title'], each['local_version'], each['download_date']))
                else:
                    logging.info("Found unmanaged mission: %s" % each)
        except FileNotFoundError as err:
            logging.error("Unable to find CustomScenarios folder - bad steam directory? %s" % err)


        # logging.info("Looking for local VTOLVRMissions.com Campaigns")
        # campaigns = []
        # try:
        #     for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns")):
        #         campaign = folder
        #         campaigns.append(campaign)
        #
        #     self.downloaded_campaigns = []
        #     no_metadata_campaigns = []
        #     for campaign in campaigns:
        #         if "Campaigns" != campaign:
        #             vtol_id = self.parse_vtol_campaign_file(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign))
        #             if vtol_id:
        #                 if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign, "vtolvrmissions.com_metadata.json")):
        #                     with open(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign, "vtolvrmissions.com_metadata.json")) as json_file:
        #                         metadata = json.load(json_file)
        #                         metadata['vtol_id'] = vtol_id
        #                         self.campaigns.append(metadata)
        #                         self.downloaded_campaigns.append(metadata)
        #                 else:
        #                     no_metadata_campaigns.append(campaign)
        #
        #     for each in self.downloaded_campaigns:
        #         logging.info("Found downloaded campaign (%s): %s (ver. %s) - downloaded on %s" % (each['location'], each['metadata']['title'], each['metadata']['local_version'], each['metadata']['download_date']))
        #
        #     for each in no_metadata_campaigns:
        #         logging.debug("Found unmanaged campaign: %s" % each)
        #
        # except FileNotFoundError as err:
        #     logging.error("Unable to find CustomScenarios/Campaigns folder - bad steam directory? %s" % err)

    def new_version_check(self, resource):
        if LooseVersion(resource['local_version']) < LooseVersion(resource['cur_version']):
            return True
        return False

    def check_for_updates(self):
        logging.info("Checking maps for updates...")
        for each in self.downloaded_maps:
            #print(each)
            online = next(item for item in self.online_resources['maps'] if item["resource_id"] == each['metadata']['resource_id'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    if strtobool(input("%s is out of date (current ver: %s - latest ver: %s). Update now? (y/n)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))):
                        self.download_resource(online)
                else:
                    logging.info("%s is up to date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

        logging.info("Checking campaigns for updates...")
        for each in self.downloaded_campaigns:
            online = next(item for item in self.online_resources['campaigns'] if item["resource_id"] == each['metadata']['resource_id'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    logging.info("%s is out of date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))
                else:
                    logging.info("%s is up to date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

        logging.info("Checking missions for updates...")
        for each in self.downloaded_missions:
            online = next(item for item in self.online_resources['missions'] if item["resource_id"] == each['metadata']['resource_id'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    logging.info("%s is out of date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))
                else:
                    logging.info("%s is up to date (current ver: %s - latest ver: %s)" % (each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))


    def all_campaigns(self):
        self.campaigns = []
        self.get_local_campaigns()
        self.get_online_campaigns()
        return(self.campaigns)


    def all_missions(self):
        self.missions = []
        self.get_local_missions()
        self.get_online_missions()
        return(self.missions)

    def all_maps(self):
        self.maps = []
        self.get_local_maps()
        self.get_online_maps()
        return(self.maps)

    def get_online_all(self):
        try:
            self.get_online_campaigns()
            self.get_online_missions()
            self.get_online_maps()
        except requests.ConnectionError as err:
            logging.error("Error connecting to %s: %s" % (self.vtolvrmissions_url, err))
            raise ConnectionError("Error connecting to %s: %s" % (self.vtolvrmissions_url, err))


    def get_online_missions(self):
        logging.info("Getting Available Missions from %s" % self.vtolvrmissions_url)
        results = self.xen.get_resources("resources/categories/missions.6/", resource_type="mission")
        for each in results:
            if not self.get_resource_by_id(each['resource_id']):
                self.missions.append(each)
            else:
                mission = self.get_resource_by_id(each['resource_id'])
                mission['cur_version'] = each['cur_version']
                self.replace_resource_by_id(each['resource_id'], mission)

    def get_online_campaigns(self):
        logging.info("Getting Available Campaigns from %s" % self.vtolvrmissions_url)
        results = self.xen.get_resources("resources/categories/campaigns.3/", resource_type="campaign")
        for each in results:
            if not self.get_resource_by_id(each['resource_id']):
                self.campaigns.append(each)
            else:
                campaign = self.get_resource_by_id(each['resource_id'])
                campaign['cur_version'] = each['cur_version']
                self.replace_resource_by_id(each['resource_id'], campaign)

    def get_online_maps(self):
        logging.info("Getting Available Maps from %s" % self.vtolvrmissions_url)
        results = self.xen.get_resources("resources/categories/maps.10", resource_type="map")
        for each in results:
            if not self.get_resource_by_id(each['resource_id']):
                self.maps.append(each)
            else:
                map = self.get_resource_by_id(each['resource_id'])
                map['cur_version'] = each['cur_version']
                self.replace_resource_by_id(each['resource_id'], map)



        # if results:
        #     self.online_resources['maps'] = results

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

def main():

    try:
        steam_dir = auto_discover_vtol_dir()
    except ModuleNotFoundError as err:
        logging.error("%s" % err)
        steam_dir = "/Users/bvirgilio-domain/VTOLVRDownloadManager/steam_dir"

    vtol_sync = Syncer(steam_dir, "https://www.vtolvrmissions.com/")
    vtol_sync.get_local_maps()

    #
    #
    # vtol_sync.all_campaigns()
    #
    # #vtol_sync.check_for_updates()
    # #exit()
    # vtol_sync.print_online_all()
    #vtol_sync.download_all_campaigns()
    #vtol_sync.all_campaigns()

    # vtol_sync.download_all_maps()

if __name__ == '__main__':
    main()
