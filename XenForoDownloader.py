import requests
from bs4 import BeautifulSoup
import logging
from dateutil import parser as date_parser


class XenForo:
    def __init__(self, url):
        self.url = url

    @staticmethod
    def _get_page(url):

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

        download_link = soup.find("label", {"class": "downloadButton"}).find("a")['href']

        download_link = self.url + download_link

        description = soup.find("li", {"class": "primaryContent"}).find("article").text.strip()

        category = soup.find("dl", {"class": "resourceCategory"}).text.split("Category:")[1].strip()

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

            title_block = resource_main.find("h3", {"class": "title"})
            title = title_block.find("a").text
            resource_link = title_block.find("a")['href']

            resource_id = str(resource_link.split("/")[1].split(".")[1])

            version = title_block.find("span", {"class": "version"}).text
            author = resource_main.find("a", {"class": "username"}).text
            tag_line = resource_main.find("div", {"class": "tagLine"}).text.replace("\t", "").replace("\n", "")

            image_url = resource_image.find("img")['src']
            rating = resource_stats.find("span", {"class": "ratings"})['title']
            downloads = resource_stats.find("dl", {"class": "resourceDownloads"}).text.split("Downloads: ")[1]
            last_updated = date_parser.parse(resource_stats.find("dl", {"class": "resourceUpdated"}).text.split("Updated: ")[1]).strftime("%Y-%m-%d")

            logging.debug("Getting resource details page: %s" % resource_link)
            if get_details:
                details = self._get_resource_details(self.url + resource_link)
            else:
                details = {}

            resource = {"resource_type": resource_type,
                        "resource_id": resource_id,
                        "title": title,
                        "image_url": self.url + "%s" % image_url,
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

    def get_resource_by_url(self, url, resource_type="Not Specified"):
        results = self._get_page(url)
        parsed = self._parse_resources_list(results, resource_type)
        return parsed

    def get_resources(self, page, resource_type="Not Specified"):
        try:
            results = self._get_page(self.url + page)
            parsed = self._parse_resources_list(results, resource_type)
            return parsed
        except ConnectionError as err:
            raise ConnectionError("Unable to connect to %s (%s)" % (page, err))
        except requests.exceptions.ConnectionError as err:
            raise ConnectionError("Unable to connect to %s (%s)" % (page, err))

    def is_online(self):
        try:
            result = requests.get(self.url)
            if result.ok:
                return True
            else:
                return False
        except Exception as err:
            logging.error(err)
            return False