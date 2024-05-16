import requests
from bs4 import BeautifulSoup
from datetime import date
import re


class GiornalettiereDownloader:

    def __init__(self, loggingHandler, downloadConfig):
        self.logging = loggingHandler
        self.name = downloadConfig['name']
        self.urls = self.compose_urls(downloadConfig['domains'], downloadConfig["query"])
        self.listConfig = downloadConfig["List"]
        self.downloadConfig = downloadConfig["Download"]
        self.relevantContent = downloadConfig['relevantContent']

    def compose_urls(self, domains, query):
        """Creates the urls"""
        urls = []
        for domain in domains:
            urls.append("{}{}".format(domain, query))
        return urls

    def extractRelevantLinks(self):
        """Extracts the relevant links"""
        regex = re.compile('[^a-zA-Z0-9]')
        myLink = {}
        for key in self.relevantContent:
            myLink[key] = []

        # Extract a valid url
        url = self.getUrl()
        if not url:
            self.logging.error("No url found")
            return []

        for info in self.extractPostList(url):
            self.logging.info(f"extractRelevantLinks - Extracting download links from: {info['title']} [{info['url']}]")
            for link in self.extractAllDownloadLinks(info['url']):
                for key in self.relevantContent:
                    cleanKey = regex.sub('', key).lower()
                    cleanTitle = regex.sub('', link['title']).lower()
                    if cleanKey in cleanTitle:
                        myLink[key].append(link)
                        self.logging.info(f"{self.name} - extractRelevantLinks - Found: {link['title']} [{link['url']}]")
        results = []
        for key in list(myLink.keys()):
            # More than 1 result obtained - Get shortest
            if len(myLink[key]) > 1:
                shortest = myLink[key][0]
                for x in myLink[key]:
                    if len(x['title']) < len(shortest):
                        shortest = x
                results.append(shortest)
            # Get the only result
            elif len(myLink[key]) == 1:
                results.append(myLink[key][0])
            # Notify a possible problem
            else:
                self.logging.error(f"{self.name} - extractRelevantLinks - No result found for key {key}")
        return results

    def validUrl(self, url):
        """Check if the site has something useful"""
        try:
            return len(list(self.extractPostList(url)))
        except Exception as e:
            self.logging.info(f"{self.name} - validUrl - Error: {str(e)}")
            return False

    def getUrl(self):
        for url in self.urls:
            if self.validUrl(url):
                return url
        return None

    def extractPostList(self, url):
        if self.listConfig.get('relevant_date') == "today":
            reference_date = date.today().strftime("%d.%m.%Y")
        else:
            self.logging.warning(f"{self.name} - extractPostList - Relevant date not yet supported")
            reference_date = date.today().strftime("%d.%m.%Y")

        page = requests.get(url)
        start_soup = BeautifulSoup(page.content, 'html.parser')
        mainSection = self.executeSearchSteps(start_soup, self.listConfig.get("search_steps", []))
        posts = self.extractInfo(mainSection, self.listConfig.get("search_element"))
        for post in posts:
            if reference_date in post[self.listConfig.get("key_containing_date", "title")]:
                yield post

    def executeSearchSteps(self, soup, search_steps):
        """Execute the search steps to reach the section with relevant information"""
        for search_step in search_steps:
            attributes = self.elaboratesAttributes(search_step)
            html_type = search_step.get('type', None)
            soup = soup.find(name=html_type, attrs=attributes)
        return soup

    def elaboratesAttributes(self, search_step):
        """Elabelates the attributes for beautifulsoup"""
        attr = {}
        attribute = search_step.get('attribute', None)
        name = search_step.get('name', None)
        if attribute == "class" and name:
            attr['class'] = name
        elif attribute == "id" and name:
            attr['id'] = name
        else:
            self.logging.debug(f"{self.name} - elaboratesAttributes - No attributes requested")
        return attr

    def extractInfo(self, mainSection, search_element):
        info = []
        elements_attribute = search_element.get('element', None)
        if elements_attribute is None:
            self.logging.warning("extractInfo - Missing search element")
        else:
            # Iterates over the given search element
            attributes = self.elaboratesAttributes(elements_attribute)
            html_type = elements_attribute.get('type', None)
            extractions = search_element.get('extract', [])
            for html_element in mainSection.find_all(name=html_type, attrs=attributes):
                info_element = {}
                for extraction_info in extractions:
                    info_element[extraction_info["key"]] = self.extractData(html_element, extraction_info)
                if info_element:
                    info.append(info_element)
        return info

    def extractData(self, html_element, extraction_info):
        searched_value = extraction_info.get('value')
        further_steps = extraction_info.get("steps", [])
        soup = self.executeSearchSteps(html_element, further_steps)
        if not soup:
            self.logging.warning(f"extractData - Cannot execute the following steps: {str(further_steps)}")
            return None
        if searched_value == "href":
            return soup["href"]
        elif searched_value == "text":
            return soup.text
        else:
            self.logging.warning(f"{self.name} - extractData - Invalid value to extract [{searched_value}]")
            return None

    def extractAllDownloadLinks(self, url):
        page = requests.get(url)
        start_soup = BeautifulSoup(page.content, 'html.parser', from_encoding=self.downloadConfig["page_encoding"])
        mainSection = self.executeSearchSteps(start_soup, self.downloadConfig.get("search_steps", []))
        links = self.extractInfo(mainSection, self.downloadConfig.get("search_element"))
        for link in links:
            for host in self.downloadConfig["host"]:
                if str(host).lower() in str(link).lower():
                    yield link