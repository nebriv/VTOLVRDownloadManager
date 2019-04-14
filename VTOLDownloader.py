import requests
from bs4 import BeautifulSoup
import logging
import os
import re
from pyunpack import Archive
import datetime
import json
from distutils.util import strtobool
import shutil
import vdf
# noinspection PyUnresolvedReferences
from distutils.version import LooseVersion, StrictVersion
import check_updates
from dateutil import parser as date_parser
from XenForo import XenForo
import tempfile
import patoolib
import zipfile
import taillogger
import sys
#logger = logging.getLogger(__name__)

# noinspection SpellCheckingInspection,SpellCheckingInspection
#logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

tail = taillogger.tail

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

log_handler = tail.log_handler
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)

levels = [logging.INFO, logging.ERROR, logging.WARN, logging.DEBUG, logging.CRITICAL]
logger.setLevel(logging.DEBUG)





try:
    import winreg

    # noinspection SpellCheckingInspection
    proc_arch = os.environ['PROCESSOR_ARCHITECTURE'].lower()
    # noinspection SpellCheckingInspection,SpellCheckingInspection
    proc_arch64 = os.environ['PROCESSOR_ARCHITEW6432'].lower()

    if proc_arch == 'x86' and not proc_arch64:
        arch_keys = {0}
    elif proc_arch == 'x86' or proc_arch == 'amd64':
        arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
    else:
        raise Exception("Unhandled arch: %s" % proc_arch)
except ImportError as err:
    winreg = False
    logger.error("Unable to import winreg, will not be able to auto detect steam location")

def winapi_path(dos_path, encoding=None):
    path = os.path.abspath(dos_path)
    if "\\\\?\\UNC\\" not in path or "\\\\?\\" not in path:
        if path.startswith("\\\\"):
            path = "\\\\?\\UNC\\" + path[2:]
        else:
            path = "\\\\?\\" + path
        return path
    else:
        return dos_path


class ZipfileLongPaths(zipfile.ZipFile):
    def _extract_member(self, member, targetpath, pwd):
        targetpath = winapi_path(targetpath)
        return zipfile.ZipFile._extract_member(self, member, targetpath, pwd)

def exists_or_make(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def find_vtol_map_root(directory):
    locations = []
    map_extensions = ['.vtm']
    bad_extensions = ['.vts', '.vtc']
    for each_dir in os.walk(directory):
        for file in each_dir[2]:
            if any(extension in file for extension in map_extensions):
                locations.append(each_dir[0])
            if any(extension in file for extension in bad_extensions):
                logger.error("Unexpected extension while looking for map resources: %s" % file)
                raise FileExistsError("Unexpected extension while looking for map resources: %s" % file)
    if len(locations) > 1:
        logger.error("More than one (%s) map resource found in download. \n This is currently unsupported by this client." % len(locations))
        raise FileExistsError("More than one (%s) map resource found in download. \n This is currently unsupported by this client." % len(locations))
    elif len(locations) == 1:
        return locations[0]
    else:
        return False

def find_vtol_campaign_root(directory):
    locations = []
    campaign_extensions = ['.vtc']
    bad_extensions = []
    for each_dir in os.walk(directory):
        for file in each_dir[2]:
            if any(extension in file for extension in campaign_extensions):
                locations.append(each_dir[0])
            if any(extension in file for extension in bad_extensions):
                logger.error("Unexpected extension while looking for campaign resources: %s" % file)
                raise FileExistsError("Unexpected extension while looking for campaign resources: %s" % file)
    if len(locations) > 1:
        logger.error("More than one (%s) campaign resource found in download. \n This is currently unsupported by this client." % len(locations))
        raise FileExistsError("More than one (%s) campaign resource found in download. \n This is currently unsupported by this client." % len(locations))
    elif len(locations) == 1:
        return locations[0]
    else:
        return False

def find_vtol_mission_root(directory):
    locations = []
    mission_extensions = ['.vts']
    bad_extensions = ['.vtm']
    for each_dir in os.walk(directory):
        for file in each_dir[2]:
            if any(extension in file for extension in mission_extensions):
                return each_dir[0]
            if any(extension in file for extension in bad_extensions):
                logger.error("Unexpected extension while looking for mission resources: %s" % file)
                raise FileExistsError("Unexpected extension while looking for mission resources: %s" % file)
    if len(locations) > 1:
        logger.error("More than one (%s) campaign resource found in download. \n This is currently unsupported by this client." % len(locations))
        raise FileExistsError("More than one (%s) campaign resource found in download. \n This is currently unsupported by this client." % len(locations))
    elif len(locations) == 1:
        return locations[0]
    else:
        return False

def auto_discover_vtol_dir():
    try:
        logger.info("Autodetecting VTOL VR directory...")
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
                        logger.info("Found VTOL VR HERE: %s" % folder[0])
                        return folder[0]
        else:
            raise ModuleNotFoundError("WinReg is missing, unable to autodetect steam install location")
    except Exception as err_msg:
        raise ValueError("An error occurred while identifying the steam directory: %s" % err_msg)


def copy(src, dst):
    import os
    import shutil
    shutil.copytree(src, dst)

class Syncer:
    def __init__(self, vtolvr_dir, url, download_directory="vtolvrmissions_temp"):
        self.vtolvr_dir = vtolvr_dir
        self.vtolvrmissions_url = url
        self.xen = XenForo(self.vtolvrmissions_url)
        self.online_resources = {"campaigns": [], "missions": [], "maps": []}
        self.download_dir = download_directory

        self.vtolvrmissions_online = True

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

        self.online_maps = []
        self.online_campaigns = []
        self.online_missions = []

    def clean_up_temp_folders(self):
        try:
            shutil.rmtree(self.download_dir)
        except Exception as err:
            logger.error("Error cleaning up temp folders: %s" % err)

    @staticmethod
    def parse_vtol_map_file(directory):
        for each in os.listdir(directory):
            if each.endswith(".vtm"):
                with open(winapi_path(os.path.join(directory, each))) as map_file:
                    lines = map_file.readlines()
                    if "VTMapCustom" in lines[0]:
                        for line in lines:
                            if "mapID = " in line:
                                map_id = line.split("mapID = ")[1].strip()
                                return map_id
        return False

    @staticmethod
    def parse_vtol_scenario_file(directory):
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

    @staticmethod
    def parse_vtol_campaign_file(directory):
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
        if resource['cur_version'] == "Not Available":
            raise Exception("This resource is no longer available online")

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

        logger.info("Done downloading")

        if os.path.exists(download_file):
            output_folder = "vtolvrmissions.com_" + ".".join(download_file.split(".")[:-1]).split(os.sep)[-1]

            #exists_or_make(output_folder)

            if resource['resource_type'] == "map":
                zip_dir = os.path.join(self.maps_directory, output_folder)
            elif resource['resource_type'] == "mission":
                zip_dir = os.path.join(self.missions_directory, output_folder)
            elif resource['resource_type'] == "campaign":
                zip_dir = os.path.join(self.campaigns_directory, output_folder)
            else:
                zip_dir = os.path.join(self.others_directory, output_folder)

            logger.info("Unzipping %s" % download_file)


            if zipfile.is_zipfile(download_file):
                logger.debug("It's a zip file!")
                try:
                    with zipfile.ZipFile(download_file, 'r') as zip_ref:
                        zip_ref.extractall(winapi_path(zip_dir))
                except Exception as zip_error:
                    logger.error("Error extracting zip: %s" % zip_error)
            else:
                try:
                    patoolib.extract_archive(download_file, outdir=zip_dir)
                except Exception as extract_error:
                    logger.error("Error extracting: %s" % extract_error)
                    if "could not find an executable program to extract format 7z" in str(extract_error):
                        raise RuntimeError("Missing 7z Executable! You must have 7z installed to extract resources compressed with 7z.")


            # if hasattr(sys, '_MEIPASS'):
            #     patool_path = os.path.join(sys._MEIPASS, "patool", "patool")
            #     print(patool_path)
            #
            #     # Archive(download_file).extractall(zip_dir, auto_create_dir=True, patool_path=patool_path)
            # else:
            #     Archive(download_file).extractall(zip_dir, auto_create_dir=True)
            logger.info("Unzipped")

            resource_metadata = resource
            resource_metadata['download_date'] = datetime.datetime.now()
            resource_metadata['local_version'] = resource['cur_version']
            resource_metadata['metadata_version'] = "1.0"

            # Extracting the root folder (if someone uploads a nested file or something,
            #  we only want the one containing the correct data
            if resource['resource_type'] == "map":
                root = find_vtol_map_root(winapi_path(zip_dir))
                root_folder_name = root.split(os.sep)[-1]
                if root:
                    vtol_id = self.parse_vtol_map_file(root)
                    if vtol_id:
                        if self.get_resource_by_vtol_id(vtol_id,
                                                        resource_type=resource['resource_type']) and not update:
                            logger.error("Map with same ID already exists")
                            raise ValueError("Map with same ID already exists at %s" %
                                             self.get_resource_by_vtol_id(vtol_id,
                                                                          resource_type=resource['resource_type'])[
                                                 'local_location'])
                        if root_folder_name != vtol_id:
                            logger.warning(
                                "Map Folder and VTOL MAP ID do not match. "
                                "This is likely an error in how the author packaged the resource.")

                    resource_name = root_folder_name
                    move_path = os.path.join(self.vtolvr_dir, "CustomMaps", resource_name)
                    resource_metadata['local_location'] = move_path
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))
                    copy(root, move_path)
                    logger.info("Done moving %s... cleaning up temp" % root)
                    shutil.rmtree(winapi_path(zip_dir), ignore_errors=True)
                    os.remove(download_file)
                else:
                    logger.error("There is an error parsing the VTOL VR Map files. No map data found within download.")
            elif resource['resource_type'] == "campaign":
                root = find_vtol_campaign_root(winapi_path(zip_dir))
                root_folder_name = root.split(os.sep)[-1]
                if root:
                    vtol_id = self.parse_vtol_campaign_file(root)
                    if vtol_id:
                        if self.get_resource_by_vtol_id(vtol_id,
                                                        resource_type=resource['resource_type']) and not update:
                            logger.error("Campaign with same ID already exists")
                            raise ValueError("Campaign with same ID already exists at %s" %
                                             self.get_resource_by_vtol_id(vtol_id,
                                                                          resource_type=resource['resource_type'])[
                                                 'local_location'])
                        if root_folder_name != vtol_id:
                            logger.warning(
                                "Campaign Folder and VTOL Campaign ID do not match."
                                " This is likely an error in how the author packaged the resource.")

                    resource_name = root_folder_name
                    move_path = os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", resource_name)
                    resource_metadata['local_location'] = move_path

                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))

                    copy(root, move_path)
                    logger.info("Done moving %s... cleaning up temp" % root)
                    shutil.rmtree(winapi_path(zip_dir), ignore_errors=True)
                    os.remove(download_file)

                else:
                    logger.error(
                        "There is an error parsing the VTOL VR Campaign files. No campaign data found within download.")
            elif resource['resource_type'] == "mission":
                root = find_vtol_mission_root(winapi_path(zip_dir))
                if root:
                    vtol_id = self.parse_vtol_scenario_file(root)
                    root_folder_name = root.split(os.sep)[-1]
                    if vtol_id:
                        if self.get_resource_by_vtol_id(vtol_id,
                                                        resource_type=resource['resource_type']) and not update:
                            logger.error("Mission with same ID already exists")
                            raise ValueError("Mission with same ID already exists at %s" %
                                             self.get_resource_by_vtol_id(vtol_id,
                                                                          resource_type=resource['resource_type'])[
                                                 'local_location'])
                        if root_folder_name != vtol_id:
                            logger.warning(
                                "Mission Folder and VTOL Mission ID do not match, "
                                "it is possible this mission may not work as expected. "
                                "This is likely an error in how the author packaged the resource.")

                    resource_name = root_folder_name
                    move_path = os.path.join(self.vtolvr_dir, "CustomScenarios", resource_name)
                    resource_metadata['local_location'] = move_path
                    with open(os.path.join(root, "vtolvrmissions.com_metadata.json"), 'w') as metadata_file:
                        metadata_file.write(json.dumps(resource_metadata, default=str))

                    copy(root, move_path)
                    logger.info("Done moving %s... cleaning up temp" % root)
                    shutil.rmtree(winapi_path(zip_dir), ignore_errors=True)
                    os.remove(download_file)
                else:
                    logger.error(
                        "There is an error parsing the VTOL VR Mission files. No mission data found within download.")

    def get_resource_by_vtol_id(self, vtol_id, resource_type):
        #print(self.maps)
        #print(self.missions)
        #print(self.campaigns)
        if resource_type == "map":
            for each_map in self.maps:
                if "vtol_id" in each_map:
                    if vtol_id == each_map['vtol_id']:
                        return each_map

        elif resource_type == "mission":
            for mission in self.missions:
                if "vtol_id" in mission:
                    if vtol_id == mission['vtol_id']:
                        return mission
        elif resource_type == "campaign":
            for campaign in self.campaigns:
                if "vtol_id" in campaign:
                    if vtol_id == campaign['vtol_id']:
                        return campaign
        return False

    def get_resource_by_id(self, vtol_id):
        vtol_id = str(vtol_id)
        for campaign in self.campaigns:
            if vtol_id == campaign['resource_id']:
                return campaign

        for each_map in self.maps:
            if vtol_id == each_map['resource_id']:
                return each_map

        for mission in self.missions:
            if vtol_id == mission['resource_id']:
                return mission
        return False

    def replace_resource_by_id(self, vtol_id, replacement):
        for i, campaign in enumerate(self.campaigns):
            if vtol_id == campaign['resource_id']:
                self.campaigns[i] = replacement
                return True

        for i, each_map in enumerate(self.maps):
            if vtol_id == each_map['resource_id']:
                self.maps[i] = replacement
                return True

        for i, mission in enumerate(self.missions):
            if vtol_id == mission['resource_id']:
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
        for each_map in self.online_resources['maps']:
            self.download_resource(each_map)

    def get_local_all(self):
        self.get_local_campaigns()
        self.get_local_maps()
        self.get_local_missions()


    @staticmethod
    def validate_local_metadata(metadata):
        if "title" in metadata and "local_version" in metadata and "local_location" in metadata and "metadata_version" in metadata:
            return True
        return False

    @staticmethod
    def remove_resource(resource):
        try:
            if "local_location" in resource:
                shutil.rmtree(resource['local_location'])
                return True
            return False
        except Exception as err_msg:
            logger.error("Error while removing %s: %s" % (resource['title'], err_msg))
            return False

    def get_local_maps(self):
        logger.info("Looking for local VTOLVRMissions.com maps")
        maps = []
        local = []
        try:
            for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomMaps")):
                each_map = folder
                maps.append(each_map)
            for each_map in maps:
                if "CustomMaps" != each_map:
                    vtol_id = self.parse_vtol_map_file(os.path.join(self.vtolvr_dir, "CustomMaps", each_map))
                    if vtol_id:
                        if os.path.isfile(
                                os.path.join(self.vtolvr_dir,
                                             "CustomMaps",
                                             each_map,
                                             "vtolvrmissions.com_metadata.json")):
                            with open(os.path.join(self.vtolvr_dir, "CustomMaps", each_map,
                                                   "vtolvrmissions.com_metadata.json")) as json_file:
                                metadata = json.load(json_file)
                                if self.validate_local_metadata(metadata):
                                    metadata['vtol_id'] = vtol_id
                                    metadata['managed'] = True
                                    if not self.get_resource_by_id(metadata['resource_id']):
                                        self.maps.append(metadata)
                                        local.append(metadata)
                                else:
                                    logger.error("Error parsing metadata for map: %s" % (
                                        os.path.join(self.vtolvr_dir, "CustomMaps", each_map)))
                                    metadata = {"local_location": os.path.join(self.vtolvr_dir, "CustomMaps", each_map),
                                                "vtol_id": vtol_id, "resource_type": "map", "managed": False,
                                                "resource_id": "N/A"}
                                    if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                        self.maps.append(metadata)
                                        local.append(metadata)

                        else:
                            metadata = {"local_location": os.path.join(self.vtolvr_dir, "CustomMaps", each_map),
                                        "vtol_id": vtol_id, "resource_type": "map", "managed": False,
                                        "resource_id": "N/A"}
                            if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                self.maps.append(metadata)
                                local.append(metadata)

            for each in local:
                if "local_version" in each:
                    logger.debug("Found downloaded map (%s): %s (ver. %s) - downloaded on %s" % (
                        each['local_location'], each['title'], each['local_version'], each['download_date']))
                else:
                    logger.debug("Found unmanaged map: %s" % each)

        except FileNotFoundError as err_msg:
            logger.error("Unable to find CustomMaps folder - bad steam directory? %s" % err_msg)
            raise NotADirectoryError("Unable to find CustomMaps folder - bad steam directory? %s" % err_msg)

    def get_local_missions(self):
        logger.info("Looking for local VTOLVRMissions.com missions")
        missions = []
        local = []
        try:
            for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios")):
                mission = folder
                missions.append(mission)
            for mission in missions:
                if "Campaigns" != mission:
                    vtol_id = self.parse_vtol_scenario_file(os.path.join(self.vtolvr_dir, "CustomScenarios", mission))
                    if vtol_id:
                        if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", mission,
                                                       "vtolvrmissions.com_metadata.json")):
                            with open(os.path.join(self.vtolvr_dir, "CustomScenarios", mission,
                                                   "vtolvrmissions.com_metadata.json")) as json_file:
                                metadata = json.load(json_file)
                                if self.validate_local_metadata(metadata):
                                    metadata['vtol_id'] = vtol_id
                                    metadata['managed'] = True
                                    if not self.get_resource_by_id(metadata['resource_id']):
                                        self.missions.append(metadata)
                                        local.append(metadata)
                                else:
                                    logger.error("Error parsing metadata for mission: %s" % (
                                        os.path.join(self.vtolvr_dir, "CustomScenarios", mission)))
                                    metadata = {
                                        "local_location": os.path.join(self.vtolvr_dir, "CustomScenarios",
                                                                       mission),
                                        "vtol_id": vtol_id, "resource_type": "mission", "managed": False,
                                        "resource_id": "N/A"}
                                    if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                        self.missions.append(metadata)
                                        local.append(metadata)
                        else:
                            metadata = {"local_location": os.path.join(self.vtolvr_dir, "CustomScenarios", mission),
                                        "vtol_id": vtol_id, "resource_type": "mission", "managed": False,
                                        "resource_id": "N/A"}
                            if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                self.missions.append(metadata)
                                local.append(metadata)

            for each in local:
                if "local_version" in each:
                    logger.debug("Found downloaded mission (%s): %s (ver. %s) - downloaded on %s" % (
                        each['local_location'], each['title'], each['local_version'], each['download_date']))
                else:
                    logger.debug("Found unmanaged mission: %s" % each)
        except FileNotFoundError as err_msg:
            logger.error("Unable to find CustomScenarios folder - bad steam directory? %s" % err_msg)
            raise NotADirectoryError("Unable to find CustomScenarios folder - bad steam directory? %s" % err_msg)

    def get_local_campaigns(self):
        logger.info("Looking for local VTOLVRMissions.com campaigns")
        campaigns = []
        local = []
        try:
            for folder in os.listdir(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns")):
                campaign = folder
                campaigns.append(campaign)
            for campaign in campaigns:
                if "Campaigns" != campaign:
                    vtol_id = self.parse_vtol_campaign_file(
                        os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign))
                    if vtol_id:
                        if os.path.isfile(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign,
                                                       "vtolvrmissions.com_metadata.json")):
                            with open(os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign,
                                                   "vtolvrmissions.com_metadata.json")) as json_file:
                                metadata = json.load(json_file)
                                if self.validate_local_metadata(metadata):
                                    metadata['vtol_id'] = vtol_id
                                    metadata['managed'] = True
                                    if not self.get_resource_by_id(metadata['resource_id']):
                                        self.campaigns.append(metadata)
                                        local.append(metadata)
                                else:
                                    logger.error("Error parsing metadata for campaign: %s" % (
                                        os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign)))
                                    metadata = {
                                        "local_location": os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns",
                                                                       campaign),
                                        "vtol_id": vtol_id, "resource_type": "campaign", "managed": False,
                                        "resource_id": "N/A"}
                                    if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                        self.campaigns.append(metadata)
                                        local.append(metadata)
                        else:
                            metadata = {
                                "local_location": os.path.join(self.vtolvr_dir, "CustomScenarios", "Campaigns", campaign),
                                "vtol_id": vtol_id, "resource_type": "campaign", "managed": False, "resource_id": "N/A"}
                            if not self.get_resource_by_vtol_id(vtol_id, metadata['resource_type']):
                                self.campaigns.append(metadata)
                                local.append(metadata)

            for each in local:
                if "local_version" in each:
                    logger.debug("Found downloaded mission (%s): %s (ver. %s) - downloaded on %s" % (
                        each['local_location'], each['title'], each['local_version'], each['download_date']))
                else:
                    logger.debug("Found unmanaged mission: %s" % each)
        except FileNotFoundError as err_msg:
            logger.error("Unable to find CustomScenarios folder - bad steam directory? %s" % err_msg)
            raise NotADirectoryError("Unable to find CustomScenarios folder - bad steam directory? %s" % err_msg)

    @staticmethod
    def new_version_check(resource):
        if "local_version" in resource and resource['cur_version'] != "Not Available":
            if LooseVersion(resource['local_version']) < LooseVersion(resource['cur_version']):
                return True
        return False

    def check_vtol_vr_online(self):
        if self.xen.is_online():
            self.vtolvrmissions_online = True
        else:
            self.vtolvrmissions_online = False

        return self.vtolvrmissions_online

    def check_for_updates(self):
        logger.info("Checking maps for updates...")
        for each in self.maps:
            # print(each)
            online = next(item for item in self.online_maps if item["resource_id"] == each['resource_id'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    if strtobool(input("%s is out of date (current ver: %s - latest ver: %s). Update now? (y/n)" % (
                            each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))):
                        self.download_resource(online)
                else:
                    logger.info("%s is up to date (current ver: %s - latest ver: %s)" % (
                        each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

        logger.info("Checking campaigns for updates...")
        for each in self.campaigns:
            online = next(item for item in self.online_campaigns if item["resource_id"] == each['resource_id'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    logger.info("%s is out of date (current ver: %s - latest ver: %s)" % (
                        each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))
                else:
                    logger.info("%s is up to date (current ver: %s - latest ver: %s)" % (
                        each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

        logger.info("Checking missions for updates...")
        for each in self.missions:
            online = next(item for item in self.online_missions if item["resource_id"] == each['resource_id'])
            if online:
                if LooseVersion(each['metadata']['version']) < LooseVersion(online['cur_version']):
                    logger.info("%s is out of date (current ver: %s - latest ver: %s)" % (
                        each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))
                else:
                    logger.info("%s is up to date (current ver: %s - latest ver: %s)" % (
                        each['metadata']['resource_name'], each['metadata']['version'], online['cur_version']))

    def all_campaigns(self):
        self.campaigns = []
        self.get_local_campaigns()
        self.get_online_campaigns()
        self.check_missing_online_campaigns()
        return self.campaigns

    def all_missions(self):
        self.missions = []
        self.get_local_missions()
        self.get_online_missions()
        self.check_missing_online_missions()
        return self.missions

    def all_maps(self):
        self.maps = []
        self.get_local_maps()
        self.get_online_maps()
        self.check_missing_online_maps()
        return self.maps

    def all_resources(self):
        return self.maps + self.missions + self.campaigns

    def check_all_for_updates(self):
        updates_required = []
        for each in self.all_resources():
            if self.new_version_check(each):
                updates_required.append(each)

        return updates_required

    def check_missing_online_campaigns(self):
        for each in self.campaigns:
            if each['resource_id'] != "N/A":
                if not any(item for item in self.online_campaigns if item["resource_id"] == each['resource_id']):
                    each['cur_version'] = "Not Available"
                    self.replace_resource_by_id(each['resource_id'], each)


    def check_missing_online_missions(self):
        for each in self.missions:
            if each['resource_id'] != "N/A":
                if not any(item for item in self.online_missions if item["resource_id"] == each['resource_id']):
                    each['cur_version'] = "Not Available"
                    self.replace_resource_by_id(each['resource_id'], each)

    def check_missing_online_maps(self):
        for each in self.maps:
            if each['resource_id'] != "N/A":
                if not any(item for item in self.online_maps if item["resource_id"] == each['resource_id']):
                    each['cur_version'] = "Not Available"
                    self.replace_resource_by_id(each['resource_id'], each)

    def get_online_all(self):
        try:
            self.get_online_campaigns()
            self.get_online_missions()
            self.get_online_maps()
        except requests.ConnectionError as err_msg:
            logger.error("Error connecting to %s: %s" % (self.vtolvrmissions_url, err_msg))
            raise ConnectionError("Error connecting to %s: %s" % (self.vtolvrmissions_url, err_msg))

    def get_online_missions(self):
        try:
            logger.info("Getting Available Missions from %s" % self.vtolvrmissions_url)
            results = self.xen.get_resources("resources/categories/missions.6/", resource_type="mission")
            for each in results:
                if not self.get_resource_by_id(each['resource_id']):
                    self.missions.append(each)
                else:
                    mission = self.get_resource_by_id(each['resource_id'])
                    mission['cur_version'] = each['cur_version']
                    self.replace_resource_by_id(each['resource_id'], mission)
                self.online_missions.append(each)
        except ConnectionError as err:
            self.vtolvrmissions_online = False
            #raise ConnectionError("VTOLVRMissions.com unreachable")

    def get_online_campaigns(self):
        try:
            logger.info("Getting Available Campaigns from %s" % self.vtolvrmissions_url)
            results = self.xen.get_resources("resources/categories/campaigns.3/", resource_type="campaign")
            for each in results:
                if not self.get_resource_by_id(each['resource_id']):
                    self.campaigns.append(each)
                else:
                    campaign = self.get_resource_by_id(each['resource_id'])
                    campaign = {**campaign, **each}
                    #campaign['cur_version'] = each['cur_version']
                    self.replace_resource_by_id(each['resource_id'], campaign)
                self.online_campaigns.append(each)
        except ConnectionError as err:
            self.vtolvrmissions_online = False
            #raise ConnectionError("VTOLVRMissions.com unreachable")

    def get_online_maps(self):
        try:
            logger.info("Getting Available Maps from %s" % self.vtolvrmissions_url)
            results = self.xen.get_resources("resources/categories/maps.10", resource_type="map")
            for each in results:
                if not self.get_resource_by_id(each['resource_id']):
                    self.maps.append(each)
                else:
                    each_map = self.get_resource_by_id(each['resource_id'])
                    each_map['cur_version'] = each['cur_version']
                    each_map['tag_line'] = each['tag_line']
                    self.replace_resource_by_id(each['resource_id'], each_map)
                self.online_maps.append(each)
        except ConnectionError as err:
            self.vtolvrmissions_online = False
            #raise ConnectionError("VTOLVRMissions.com unreachable")

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
    except ModuleNotFoundError as err_msg:
        logger.error("%s" % err_msg)
        steam_dir = ""

    vtol_sync = Syncer(steam_dir, "https://www.vtolvrmissions.com/")
    vtol_sync.get_local_maps()

    #
    #
    # vtol_sync.all_campaigns()
    #
    # #vtol_sync.check_for_updates()
    # #exit()
    # vtol_sync.print_online_all()
    # vtol_sync.download_all_campaigns()
    # vtol_sync.all_campaigns()

    # vtol_sync.download_all_maps()


if __name__ == '__main__':
    main()
