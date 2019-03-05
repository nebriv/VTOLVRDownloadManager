import os
from tkinter.ttk import Frame, Button, Style
from tkinter import simpledialog
from tkinter import ttk
from VTOLDownloader import Syncer, auto_discover_vtol_dir
from tkinter import messagebox
import time
import queue
import webbrowser
import threading
import logging
import PIL.ImageTk, PIL.Image
import urllib, io
import taillogger

try:
    from Tkinter import *
    from ttk import *
except ImportError:  # Python 3
    from tkinter import *
    from tkinter.ttk import *

import tempfile, zlib
import check_updates
from urllib.request import urlopen
import icon_base64

logger = logging.getLogger(__name__)

tail = taillogger.tail

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

log_handler = tail.log_handler
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)

levels = [logging.INFO, logging.ERROR, logging.WARN, logging.DEBUG, logging.CRITICAL]
logger.setLevel(logging.DEBUG)


_, ICON_PATH = tempfile.mkstemp()
with open(ICON_PATH, 'wb') as icon_file:
    icon_file.write(icon_base64.ICON)

__version__ = "v1.2"
__author__ = "nebriv"
githuburl = "https://github.com/nebriv/VTOLVRDownloadManager"


def treeview_sort_column(tv, col, reverse):

    l = [(tv.set(k, col), k) for k in tv.get_children('')]

    # Hardcoding the columns for now... too lazy to detect types
    if col == "Name":
        l.sort(key=lambda t: int(t[0]), reverse=reverse)
    elif col == "Downloads":
        l.sort(key=lambda t: float(t[0]), reverse=reverse)
    else:
        l.sort(key=lambda t: t[0], reverse=reverse)

    for index, (val, k) in enumerate(l):
        tv.move(k, '', index)

    tv.heading(col,
               command=lambda: treeview_sort_column(tv, col, not reverse))

def treeview_search(treeview, comparevalue):
    children = treeview.get_children('')
    for child in children:
        values = treeview.item(child, 'values')
        print(comparevalue[0], values[0])
        if comparevalue[0]==values[0] and str(comparevalue[1])==str(values[1]):

            return True
    return False

class Window(Frame):

    def __init__(self, master=None):
        Frame.__init__(self, master)

        # Set settings
        self.show_unmanaged = BooleanVar()
        self.show_unmanaged.set(False)
        self.run_connectivity_checks = BooleanVar()
        self.run_connectivity_checks.set(True)
        self.running_threads = []

        self.steam_dir = StringVar()

        self.loading_label_text = StringVar()
        self.vtol_online_text = StringVar()

        self.about_window_opened = False
        self.recheck_running = False

        self.refresh_campaigns_running = False
        self.refresh_maps_running = False
        self.refresh_missions_running = False

        self.master = master
        self.master.wm_title("VTOLVRMissions.com Downloader")

        try:
            self.master.iconbitmap(default=ICON_PATH)
            #self.master.tk.call('wm', 'iconphoto', self.master._w, tk.PhotoImage(file=ICON_PATH))
        except Exception as err_msg:
            logger.error("Logo icon doesn't exist: %s" % err_msg)
        self.loading_label_text.set("Loading...")
        self.vtol_sync = None
        self.main_window()

        self.status_queue = queue.Queue()
        self.status_message_updater()
        #update_thread = threading.Thread(target=)
        self.master.after(10000, self.check_for_updates)

    def check_for_updates(self):
        update_available = check_updates.check_updates(__version__)
        if update_available:
            if messagebox.askyesno("VTOLVRMission Downloader Client Update Available","You are currently on version %s, %s is available for download.\nWould you like to visit the download page now?" % (__version__, update_available['version'])):
                self.open_in_browser(update_available['browse_url'])

    def close_about_window(self):
        self.about_window_opened = False
        self.about_window.destroy()

    def make_about_window(self):
        if self.about_window_opened:
            self.about_window.lift()
        else:
            self.about_window = Toplevel(self)
            self.about_window.geometry("350x200")
            self.about_frame = Frame(self.about_window)
            self.about_frame.pack(fill=BOTH, expand=1)
            self.about_frame.grid_rowconfigure(6, weight=1)
            self.about_frame.grid_columnconfigure(3, weight=1)

            about_window_header = Label(self.about_frame, text="VTOLVRMissions.com Downloader", font=(None, 12))
            about_window_header.grid(column=3, row=1)
            about_window_description = Label(self.about_frame,wraplength=300, justify=CENTER, text="A utility for downloading and updating custom "
                                                                    "resources from vtolvrmissions.com. "
                                                                    "This is a hack job of a client and"
                                                                    " meant to make life a bit easier - "
                                                                    "it is recommended that you be familiar"
                                                                    " with the folder structure of VTOL VR's custom"
                                                                    " missions and campaigns.")
            about_window_description.grid(column=3, row=2)

            about_window_version = Label(self.about_frame, text="Version: %s by %s" % (__version__, __author__))
            about_window_version.grid(column=3, row=4, pady=20)

            about_window_link = Label(self.about_frame, text="%s" % githuburl, foreground='blue', cursor="hand2")
            about_window_link.grid(column=3, row=5)
            about_window_link.bind("<Button-1>", lambda e, url=githuburl:self.open_in_browser(githuburl))

            about_window_blank = Label(self.about_frame, text="")
            about_window_blank.grid(column=3, row=6, sticky="S")

            self.about_window.protocol("WM_DELETE_WINDOW", self.close_about_window)
            self.about_window.wm_title("About")
            self.about_window_opened = True

    def steam_directory_prompt(self):
        answer = simpledialog.askstring("Steam Directory", "Steam Directory Not Found. Please manually provide the path to VTOL VR.",
                                        parent=self)
        return answer

    def online_recheck(self):
        if not self.vtol_sync.vtolvrmissions_online and self.recheck_running == False and self.run_connectivity_checks.get():
            logger.info("Checking if vtolvrmissions.com is back online...")
            self.recheck_running = True
            self.vtol_online_text.set("VTOLVRMissions.com: Checking")
            self.vtol_sync.check_vtol_vr_online()
            if self.vtol_sync.vtolvrmissions_online:
                self.vtol_online_text.set("VTOLVRMissions.com: Online")
                self.refresh_all()
            else:
                self.vtol_online_text.set("VTOLVRMissions.com: Offline")
            time.sleep(30)
            self.recheck_running = False

    def main_window(self):
        """ Main function containing main window GUI Components"""
        self.pack(fill=BOTH, expand=1)

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(3, weight=1)

        self.loading_label = Label(self, textvariable=self.loading_label_text)
        self.loading_label.grid(row=4, column=3, sticky="S")
        self.online_status_label = Label(self, textvariable=self.vtol_online_text)
        self.online_status_label.grid(row=4, column=3, sticky="SE")

        t1 = threading.Thread(target=self.load_vtol_sync_app)
        t1.start()

        nb = ttk.Notebook(self)
        campaign_page = ttk.Frame(nb)
        nb.add(campaign_page, text="Campaigns")
        mission_page = ttk.Frame(nb)
        nb.add(mission_page, text="Missions")
        map_page = ttk.Frame(nb)
        nb.add(map_page, text="Maps")

        settings_page = ttk.Frame(nb)
        nb.add(settings_page, text="Settings")
        logger_page = ttk.Frame(nb)
        nb.add(logger_page, text="Log Viewer")

        nb.grid(row=1, column=1, columnspan=3)

        # Settings Page
        settings_page.grid_rowconfigure(10)
        settings_page.grid_columnconfigure(2, weight=1)
        Checkbutton(settings_page, text="Show Unmanaged Resources", variable=self.show_unmanaged, command=self.refresh_all).grid(row=0, sticky=W, padx=5)
        Checkbutton(settings_page, text="Perform Connectivity Checks when offline", variable=self.run_connectivity_checks).grid(row=1, sticky=W, padx=5)
        #Entry(settings_page, textvariable=self.steam_dir).grid(row=2, sticky=W, padx=5)

        # Logger Page
        logger_page.grid_rowconfigure(3)
        logger_page.grid_columnconfigure(1, weight=1)

        log_vsb = Scrollbar(logger_page)
        log_hsb = Scrollbar(logger_page, orient=HORIZONTAL)
        self.log_area = Text(logger_page, height=15, width=130, yscrollcommand=log_vsb.set, xscrollcommand=log_hsb.set, wrap=NONE)
        self.log_area.grid(column=1, row=1, pady=5, sticky='we')
        self.log_area.bind("<Key>", lambda e: "break")
        log_vsb.grid(row=1, column=2, sticky='wns')
        log_hsb.grid(row=2, column=1, sticky='wes', pady=5)
        log_hsb.configure(command=self.log_area.xview)
        log_vsb.configure(command=self.log_area.yview)

        # log_buttons = Frame(logger_page)
        # log_buttons.grid(row=3, column=1, pady=5)
        # log_buttons.grid_rowconfigure(1)
        # log_buttons.grid_columnconfigure(2)
        #
        # log_clear = Button(log_buttons, text="Clear")
        # log_clear.grid(row=1,column=1)
        # log_save = Button(log_buttons, text="Save")
        # log_save.grid(row=1,column=2)


        #Checkbutton(logger_page, text="Show Unmanaged Resources", variable=self.show_unmanaged, command=self.refresh_all).grid(row=0, sticky=W, padx=5)
        #Checkbutton(logger_page, text="Perform Connectivity Checks when offline", variable=self.run_connectivity_checks).grid(row=1, sticky=W, padx=5)
        #Entry(settings_page, textvariable=self.steam_dir).grid(row=2, sticky=W, padx=5)

        # Campaign Page
        campaign_page.grid_rowconfigure(10)
        campaign_page.grid_columnconfigure(4, weight=1)

        campaign_content = Frame(campaign_page)
        campaign_content.grid(row=1, column=3, sticky="NS", pady=5)
        campaign_content.grid_rowconfigure(3)
        campaign_content.grid_columnconfigure(2)
        campaign_vsb = Scrollbar(campaign_content, orient = "vertical")
        self.campaign_tree = Treeview(campaign_content, yscrollcommand = campaign_vsb.set)
        self.campaign_tree.bind("<ButtonRelease-1>", lambda event, campaign_tree=self.campaign_tree:  self.set_campaign_details(campaign_tree) )
        campaign_vsb.configure(command=self.campaign_tree.yview)

        self.campaign_details = Frame(campaign_page)
        self.campaign_details.grid(row=1, column=4, sticky="NS", padx=5, pady=5)
        self.campaign_details.grid_rowconfigure(5)
        self.campaign_details.grid_columnconfigure(1)

        self.campaign_details_title = Label(self.campaign_details, text="")
        self.campaign_details_title.grid(row=1, column=1)
        self.campaign_image = Label(self.campaign_details, image=None, width=50)
        self.campaign_image.grid(column=1, row=2, padx=10, pady=10)
        self.campaign_details_tagline = Label(self.campaign_details, wraplength=300, text="", justify=CENTER)
        self.campaign_details_tagline.grid(row=3, column=1)

        self.campaign_details_last_updated = Label(self.campaign_details, wraplength=300, text="", justify=LEFT)
        self.campaign_details_last_updated.grid(row=4, column=1, pady=10)

        self.campaign_details_description = Label(self.campaign_details, wraplength=300, text="", justify=LEFT)
        self.campaign_details_description.grid(row=5, column=1, pady=10)


        self.campaign_tree['columns'] = ("Name", "Downloads", "Rating", "Category", "Author", "Online_Version", "Local_Version", "resource_id")
        self.campaign_tree['displaycolumns'] = ("Name","Downloads", "Rating", "Category", "Author", "Online_Version", "Local_Version")
        self.campaign_tree.heading("#0", text="Name")
        self.campaign_tree.column("#0", minwidth=200, width=250, anchor="center")

        self.campaign_tree.heading("#1", text="Downloads")
        self.campaign_tree.column("#1", minwidth=75, width=100, anchor="center")

        self.campaign_tree.heading("#2", text="Rating")
        self.campaign_tree.column("#2", minwidth=50, width=50, anchor="center")

        self.campaign_tree.heading("#3", text="Category")
        self.campaign_tree.column("#3", minwidth=75, width=100, anchor="center")

        self.campaign_tree.heading("#4", text="Author")
        self.campaign_tree.column("#4", minwidth=50, width=75, anchor="center")

        self.campaign_tree.heading("#5", text="Online Version")
        self.campaign_tree.column("#5", minwidth=50, width=100, anchor="center")

        self.campaign_tree.heading("#6", text="Local Version")
        self.campaign_tree.column("#6", minwidth=50, width=150, anchor="center")

        self.campaign_tree.heading("#7", text="")
        self.campaign_tree.column("#7", minwidth=0, width=0)

        for col in self.campaign_tree['columns']:
            self.campaign_tree.heading(col, command=lambda _col=col: \
                treeview_sort_column(self.campaign_tree, _col, False))

        self.campaign_tree.grid(row=1, column=3, sticky="W")
        campaign_vsb.grid(row=1, column=4, sticky='ns')

        campaign_buttons = Frame(campaign_content)
        campaign_buttons.grid(row=2, column=3, pady=5)
        campaign_buttons.grid_rowconfigure(1)
        campaign_buttons.grid_columnconfigure(2)

        campaign_download_button = Button(campaign_buttons, text="Open in Web Browser", command= lambda: self.open_resource_in_browser(self.campaign_tree) )
        campaign_download_button.grid(row=1, column=1)
        campaign_open_location_button = Button(campaign_buttons, text="Open Local Location", command= lambda: self.open_resource_location(self.campaign_tree, "campaign") )
        campaign_open_location_button.grid(row=1, column=2)
        campaign_download_button = Button(campaign_buttons, text="Install/Update", command= lambda: self.download_button(self.campaign_tree) )
        campaign_download_button.grid(row=1, column=3)
        campaign_remove_button = Button(campaign_buttons, text="Remove", command= lambda: self.remove_button(self.campaign_tree) )
        campaign_remove_button.grid(row=1, column=4)

        # Mission Page
        mission_page.grid_rowconfigure(10)
        mission_page.grid_columnconfigure(4, weight=1)

        mission_content = Frame(mission_page)
        mission_content.grid(row=1, column=3, sticky="NS", pady=5)
        mission_content.grid_rowconfigure(3)
        mission_content.grid_columnconfigure(2)
        mission_vsb = Scrollbar(mission_content, orient = "vertical")
        self.mission_tree = Treeview(mission_content, yscrollcommand = mission_vsb.set)
        self.mission_tree.bind("<ButtonRelease-1>",
                                lambda event, mission_tree=self.mission_tree: self.set_mission_details(
                                    mission_tree))
        mission_vsb.configure(command=self.mission_tree.yview)

        self.mission_details = Frame(mission_page)
        self.mission_details.grid(row=1, column=4, sticky="NS", padx=5, pady=5)
        self.mission_details.grid_rowconfigure(5)
        self.mission_details.grid_columnconfigure(1)

        self.mission_details_title = Label(self.mission_details, text="")
        self.mission_details_title.grid(row=1, column=1)
        self.mission_image = Label(self.mission_details, image=None, width=50)
        self.mission_image.grid(column=1, row=2, padx=10, pady=10)
        self.mission_details_tagline = Label(self.mission_details, wraplength=300, text="", justify=CENTER)
        self.mission_details_tagline.grid(row=3, column=1)

        self.mission_details_last_updated = Label(self.mission_details, wraplength=300, text="", justify=LEFT)
        self.mission_details_last_updated.grid(row=4, column=1, pady=10)

        self.mission_details_description = Label(self.mission_details, wraplength=300, text="", justify=LEFT)
        self.mission_details_description.grid(row=5, column=1, pady=10)


        self.mission_tree['columns'] = ("Name", "Downloads", "Rating", "Category", "Author", "Online_Version", "Local_Version", "resource_id")
        self.mission_tree['displaycolumns'] = ("Name","Downloads", "Rating", "Category", "Author", "Online_Version", "Local_Version")
        self.mission_tree.heading("#0", text="Name")
        self.mission_tree.column("#0", minwidth=200, width=250, anchor="center")

        self.mission_tree.heading("#1", text="Downloads")
        self.mission_tree.column("#1", minwidth=75, width=100, anchor="center")

        self.mission_tree.heading("#2", text="Rating")
        self.mission_tree.column("#2", minwidth=50, width=50, anchor="center")

        self.mission_tree.heading("#3", text="Category")
        self.mission_tree.column("#3", minwidth=75, width=100, anchor="center")

        self.mission_tree.heading("#4", text="Author")
        self.mission_tree.column("#4", minwidth=50, width=75, anchor="center")

        self.mission_tree.heading("#5", text="Online Version")
        self.mission_tree.column("#5", minwidth=50, width=100, anchor="center")

        self.mission_tree.heading("#6", text="Local Version")
        self.mission_tree.column("#6", minwidth=50, width=150, anchor="center")

        self.mission_tree.heading("#7", text="")
        self.mission_tree.column("#7", minwidth=0, width=0)


        for col in self.mission_tree['columns']:
            self.mission_tree.heading(col, command=lambda _col=col: \
                treeview_sort_column(self.mission_tree, _col, False))

        self.mission_tree.grid(row=1, column=3, sticky="NS")
        mission_vsb.grid(row=1, column=4, sticky='ns')

        mission_buttons = Frame(mission_content)
        mission_buttons.grid(row=2, column=3, pady=5)
        mission_buttons.grid_rowconfigure(1)
        mission_buttons.grid_columnconfigure(2)

        mission_download_button = Button(mission_buttons, text="Open in Web Browser", command= lambda: self.open_resource_in_browser(self.mission_tree) )
        mission_download_button.grid(row=1, column=1)

        mission_open_location_button = Button(mission_buttons, text="Open Local Location", command= lambda: self.open_resource_location(self.mission_tree, "mission") )
        mission_open_location_button.grid(row=1, column=2)

        mission_install_button = Button(mission_buttons, text="Install/Update", command= lambda: self.download_button(self.mission_tree) )
        mission_install_button.grid(row=1, column=3)

        mission_remove_button = Button(mission_buttons, text="Remove", command= lambda: self.remove_button(self.mission_tree) )
        mission_remove_button.grid(row=1, column=4)

        # Map Page
        map_page.grid_rowconfigure(10)
        map_page.grid_columnconfigure(4, weight=1)

        map_content = Frame(map_page)
        map_content.grid(row=1, column=3, sticky="NS", pady=5)
        map_content.grid_rowconfigure(3)
        map_content.grid_columnconfigure(2)
        map_vsb = Scrollbar(map_content, orient = "vertical")
        self.map_tree = Treeview(map_content, yscrollcommand = map_vsb.set)
        self.map_tree.bind("<ButtonRelease-1>",
                                lambda event, map_tree=self.map_tree: self.set_map_details(
                                    map_tree))

        map_vsb.configure(command=self.map_tree.yview)

        self.map_details = Frame(map_page)
        self.map_details.grid(row=1, column=4, sticky="NS", padx=5, pady=5)
        self.map_details.grid_rowconfigure(5)
        self.map_details.grid_columnconfigure(1)

        self.map_details_title = Label(self.map_details, text="")
        self.map_details_title.grid(row=1, column=1)
        self.map_image = Label(self.map_details, image=None, width=50)
        self.map_image.grid(column=1, row=2, padx=10, pady=10)
        self.map_details_tagline = Label(self.map_details, wraplength=300, text="", justify=CENTER)
        self.map_details_tagline.grid(row=3, column=1)

        self.map_details_last_updated = Label(self.map_details, wraplength=300, text="", justify=LEFT)
        self.map_details_last_updated.grid(row=4, column=1, pady=10)

        self.map_details_description = Label(self.map_details, wraplength=300, text="", justify=LEFT)
        self.map_details_description.grid(row=5, column=1, pady=10)


        self.map_tree['columns'] = ("Name", "Downloads", "Rating", "Author", "Online_Version", "Local_Version", "resource_id")
        self.map_tree['displaycolumns'] = ("Name", "Downloads", "Rating", "Author", "Online_Version", "Local_Version")
        self.map_tree.heading("#0", text="Name")
        self.map_tree.column("#0", minwidth=200, width=250, anchor="center")

        self.map_tree.heading("#1", text="Downloads")
        self.map_tree.column("#1", minwidth=75, width=100, anchor="center")

        self.map_tree.heading("#2", text="Rating")
        self.map_tree.column("#2", minwidth=50, width=50, anchor="center")

        self.map_tree.heading("#3", text="Author")
        self.map_tree.column("#3", minwidth=100, width=75, anchor="center")

        self.map_tree.heading("#4", text="Online Version")
        self.map_tree.column("#4", minwidth=100, width=100, anchor="center")

        self.map_tree.heading("#5", text="Local Version")
        self.map_tree.column("#5", minwidth=150, width=250, anchor="center")

        self.map_tree.heading("#6", text="")
        self.map_tree.column("#6", minwidth=0, width=0)

        for col in self.map_tree['columns']:
            self.map_tree.heading(col, command=lambda _col=col: \
                treeview_sort_column(self.map_tree, _col, False))

        self.map_tree.grid(row=1, column=3, sticky="WNS")
        map_vsb.grid(row=1, column=4, sticky='ns')

        map_buttons = Frame(map_content)
        map_buttons.grid(row=2, column=3, pady=5)
        map_buttons.grid_rowconfigure(1)
        map_buttons.grid_columnconfigure(2)

        map_browser_button = Button(map_buttons, text="Open in Web Browser", command= lambda: self.open_resource_in_browser(self.map_tree) )
        map_browser_button.grid(row=1, column=1)

        map_open_location_button = Button(map_buttons, text="Open Local Location", command= lambda: self.open_resource_location(self.map_tree, "map") )
        map_open_location_button.grid(row=1, column=2)

        map_install_button = Button(map_buttons, text="Install/Update", command= lambda: self.download_button(self.map_tree) )
        map_install_button.grid(row=1, column=3)

        map_remove_button = Button(map_buttons, text="Remove", command= lambda: self.remove_button(self.map_tree) )
        map_remove_button.grid(row=1, column=4)

        menu = Menu(self.master)
        self.master.config(menu=menu)

        file = Menu(menu, tearoff=False)
        file.add_command(label="Check for client updates", command=self.check_for_updates)
        file.add_command(label="Exit", command=self.client_exit)
        menu.add_cascade(label="File", menu=file)

        menu.add_command(label="Update All", command=self.update_all)
        menu.add_command(label="Refresh Tables", command=self.refresh_all)
        menu.add_command(label="About", command=self.make_about_window)
        t1.join()

    def set_campaign_details(self, tree):
        t = threading.Thread(target=self.set_campaign_details_thread, args=(tree,))
        t.start()

    def set_campaign_details_thread(self, tree):
        try:
            curItem = tree.focus()
            resource = tree.item(curItem)
            resource = self.vtol_sync.get_resource_by_id(resource['values'][-1])
            self.campaign_details_title.configure(text=resource['title'])

            image_url = resource['image_url']
            raw_data = urllib.request.urlopen(image_url).read()
            im = PIL.Image.open(io.BytesIO(raw_data))
            image = PIL.ImageTk.PhotoImage(im)
            self.campaign_image.configure(image=image)
            self.campaign_image.photo = image

            self.campaign_details_tagline.configure(text=resource['tag_line'])
            self.campaign_details_last_updated.config(text="Online Version Updated: %s" % resource['last_updated'])

        except IndexError as err:
            pass

    def set_mission_details(self, tree):
        t = threading.Thread(target=self.set_mission_details_thread, args=(tree,))
        t.start()

    def set_mission_details_thread(self, tree):
        try:
            curItem = tree.focus()
            resource = tree.item(curItem)
            resource = self.vtol_sync.get_resource_by_id(resource['values'][-1])
            self.mission_details_title.configure(text=resource['title'])

            image_url = resource['image_url']
            raw_data = urllib.request.urlopen(image_url).read()
            im = PIL.Image.open(io.BytesIO(raw_data))
            image = PIL.ImageTk.PhotoImage(im)
            self.mission_image.configure(image=image)
            self.mission_image.photo = image

            self.mission_details_tagline.configure(text=resource['tag_line'])
            self.mission_details_last_updated.config(text="Online Version Updated: %s" % resource['last_updated'])
        except IndexError as err:
            pass

    def set_map_details(self, tree):
        t = threading.Thread(target=self.set_map_details_thread, args=(tree,))
        t.start()

    def set_map_details_thread(self, tree):
        try:
            curItem = tree.focus()
            resource = tree.item(curItem)
            resource = self.vtol_sync.get_resource_by_id(resource['values'][-1])
            self.map_details_title.configure(text=resource['title'])

            image_url = resource['image_url']
            raw_data = urllib.request.urlopen(image_url).read()
            im = PIL.Image.open(io.BytesIO(raw_data))
            image = PIL.ImageTk.PhotoImage(im)
            self.map_image.configure(image=image)
            self.map_image.photo = image

            self.map_details_tagline.configure(text=resource['tag_line'])
            self.map_details_last_updated.config(text="Online Version Updated: %s" % resource['last_updated'])
            #self.campaign_details_description.configure(text=resource['details']['description'])
        except IndexError as err:
            pass

    def get_log_lines(self):
        #print(downloader_logs.contents())
        for line in taillogger.tail.contents():
            self.log_area.insert(END, line + "\n")

    def status_message_updater(self):
        """ Updates the little status message in the bottom of the app. """

        self.get_log_lines()

        while self.status_queue.qsize():
            msg = self.status_queue.get(0)
            self.loading_label_text.set(msg)
            if self.vtol_sync.vtolvrmissions_online:
                self.vtol_online_text.set("VTOLVRMissions.com: Online")
            else:
                self.vtol_online_text.set("VTOLVRMissions.com: Offline")


        if not self.vtol_sync.vtolvrmissions_online and not self.recheck_running and self.run_connectivity_checks.get():
            thread = threading.Thread(target=self.online_recheck)
            thread.start()
        self.master.after(250,self.status_message_updater)

    def load_vtol_sync_app(self):
        """ Loads the actual downloader component """
        try:
            steam_dir = auto_discover_vtol_dir()
        except Exception as err:
            logger.error("%s" % err)
            steam_dir = self.steam_directory_prompt()


        self.vtol_sync = Syncer(steam_dir, "https://www.vtolvrmissions.com/")

    def put_msg(self, msg):
        self.status_queue.put(msg)

    def check_and_update_log(self):
        raise NotImplementedError("Not implemented yet")
        #pass

    def error_and_exit(self, title, msg):
        messagebox.showerror(title, msg)
        self.client_exit()

    def display_error(self, title, msg):
        messagebox.showerror(title, msg)

    def display_message(self, title, msg):
        messagebox.showinfo(title, msg)

    def open_in_browser(self, link):
        webbrowser.open(link)

    def open_resource_location(self, tree_item, resource_type):
        """ Opens the selected resource in the OS's file explorer (hopefully) """
        curItem = tree_item.focus()
        if "" == curItem:
            self.display_error("Unselected Resource", "No resource selected, pick an item from the list and try again.")
        elif tree_item.item(curItem)['values'][-2] == "Not Downloaded":
            self.display_error("Resource Missing", "Resource is not downloaded, so there is no local location to open.")
        else:
            resource = self.vtol_sync.get_resource_by_vtol_id(tree_item.item(curItem)['text'], resource_type)
            print(resource)
            os.startfile(resource['local_location'])

    def open_resource_in_browser(self, tree_item):
        """Opens the selected resource in the user's default browser."""

        curItem = tree_item.focus()

        if "" == curItem:
            self.display_error("Unselected Resource", "No resource selected, pick an item from the list and try again.")

        elif tree_item.item(curItem)['values'][-1] == "Unmanaged":
            self.display_error("Unmanaged resource", "No URL associated with resource.")
        else:
            resource = self.vtol_sync.get_resource_by_id(tree_item.item(curItem)['values'][-1])
            self.open_in_browser(resource['link'])

    def remove_resource(self, resource, tree_item, curItem):
        if self.vtol_sync.remove_resource(resource):
            self.display_message("Removal Success", "Successfully removed %s" % resource['title'])
            if resource['resource_type'] == "map":
                self.refresh_maps()
            elif resource['resource_type'] == "campaign":
                self.refresh_campaigns()
            elif resource['resource_type'] == "mission":
                self.refresh_missions()
            else:
                self.refresh_all()
        else:
            self.display_error("Removal Failed", "Failed to remove %s" % (tree_item.item(curItem)['text']))

    def remove_button(self, tree_item):
        """ Handles various exceptions that may occur when removing available/unavailable resources """

        curItem = tree_item.focus()

        if "" == curItem:
            self.display_error("Unselected Resource", "No resource selected, pick an item from the list and try again.")
        elif tree_item.item(curItem)['values'][-1] == "Unmanaged":
            self.display_error("Unmanaged resource", "This resource is unmanaged, please remove it manually")
        else:
            if tree_item.item(curItem)['values'][2] == "Not Available":
                if not messagebox.askyesno("Remove?", "This resource is no longer available online, are you sure you want to remove it?"):
                    return False
            resource = self.vtol_sync.get_resource_by_id(tree_item.item(curItem)['values'][-1])
            t1 = threading.Thread(target=self.remove_resource, args=(resource, tree_item, curItem))
            t2 = threading.Thread(target=self.run_threads, args=([t1], "Removing %s" % tree_item.item(curItem)['text'], "Done!", True))
            t2.start()

    def download_resource(self, resource):
        """ The actual function calling the download function. """
        try:
            self.vtol_sync.download_resource(resource)
            if resource['resource_type'] == "map":
                self.refresh_maps()
            elif resource['resource_type'] == "campaign":
                self.refresh_campaigns()
            elif resource['resource_type'] == "mission":
                self.refresh_missions()
            else:
                self.refresh_all()
        except Exception as err:
            self.put_msg("Error downloading resource: %s" % err)
            self.display_error("Error downloading resource", err)



    def download_button(self, tree_item):
        """ Handles various exceptions that may occur when downloading available/unavailable resources """
        curItem = tree_item.focus()
        if "" == curItem:
            self.display_error("Unselected Resource", "No resource selected, pick an item from the list and try again.")
        elif tree_item.item(curItem)['values'][-1] == "Unmanaged":
            self.display_error("Unmanaged resource", "This is a local unmanaged resource, it cannot be installed")
        else:
            resource = self.vtol_sync.get_resource_by_id(tree_item.item(curItem)['values'][-1])
            t1 = threading.Thread(target=self.download_resource, args=(resource,))
            t2 = threading.Thread(target=self.run_threads, args=([t1], "Downloading %s" % tree_item.item(curItem)['text'], "Done!", True))
            t2.start()

    def update_all(self):
        """ Runs the update_all_thread in another thread. """
        if messagebox.askyesno("Update All Resources?", "Are you sure you want to update all resources?"):
            t1 = threading.Thread(target=self.update_all_thread)
            t2 = threading.Thread(target=self.run_threads, args=([t1], "Updating all resources...", "Done!", True))
            t2.start()

    def update_all_thread(self):
        """ Lazy/Hackjob way of splitting the function """
        for each in self.vtol_sync.check_all_for_updates():
            self.put_msg("Downloading %s" % each['title'])
            self.vtol_sync.download_resource(each)
        self.refresh_all()

    def refresh_maps(self):
        """ Runs the refresh_maps_thread in another thread. """
        if not self.vtol_sync.vtolvrmissions_online:
            self.display_message("VTOLVRMissions.com Offline", "VTOLVRMissions.com is currently offline, we will only show local resources. Try refreshing data later.")

        if not self.refresh_maps_running:
            t1 = threading.Thread(target=self.refresh_maps_thread())
            t2 = threading.Thread(target=self.run_threads, args=([t1], 'Refreshing map list', "Done!", True))
            t2.start()
            self.refresh_maps_running = True

    def refresh_maps_thread(self):
        """ Lazy/Hackjob way of splitting the function """
        # Clear Map Data
        for i in self.map_tree.get_children():
            self.map_tree.delete(i)
        self.populate_maps()
        self.refresh_maps_running = False

    def refresh_campaigns(self):
        """ Runs the refresh_campaigns_thread in another thread. """
        if not self.vtol_sync.vtolvrmissions_online:
            self.display_message("VTOLVRMissions.com Offline", "VTOLVRMissions.com is currently offline, we will only show local resources. Try refreshing data later.")

        if not self.refresh_campaigns_running:
            self.refresh_campaigns_running = True
            t1 = threading.Thread(target=self.refresh_campaigns_thread())
            t2 = threading.Thread(target=self.run_threads, args=([t1], 'Refreshing campaign list', "Done!", True))
            t2.start()


    def refresh_campaigns_thread(self):
        """ Lazy/Hackjob way of splitting the function """
        # Clear Campaign Data
        for i in self.campaign_tree.get_children():
            self.campaign_tree.delete(i)
        self.populate_campaigns()
        self.refresh_campaigns_running = False

    def refresh_missions(self):
        """ Runs the refresh_mission_thread in another thread. """
        if not self.vtol_sync.vtolvrmissions_online:
            self.display_message("VTOLVRMissions.com Offline", "VTOLVRMissions.com is currently offline, we will only show local resources. Try refreshing data later.")

        if not self.refresh_missions_running:
            self.refresh_missions_running = True
            t1 = threading.Thread(target=self.refresh_missions_thread())
            t2 = threading.Thread(target=self.run_threads, args=([t1], 'Refreshing mission list', "Done!", True))
            t2.start()

    def refresh_missions_thread(self):
        """ Lazy/Hackjob way of splitting the function """
        # Clear Mission Data
        for i in self.mission_tree.get_children():
            self.mission_tree.delete(i)
        self.populate_missions()
        self.refresh_missions_running = False

    def refresh_all_thread(self):
        """ Lazy/Hackjob way of splitting the function """
        self.refresh_campaigns()
        self.refresh_maps()
        self.refresh_missions()

    def refresh_all(self):
        """ Essentially the same thing a populate_all"""

        if not self.vtol_sync.vtolvrmissions_online:
            self.display_message("VTOLVRMissions.com Offline", "VTOLVRMissions.com is currently offline, we will only show local resources. Try refreshing data later.")

        t1 = threading.Thread(target=self.refresh_all_thread)
        threads = [t1]

        t4 = threading.Thread(target=self.run_threads, args=(threads, "Refreshing Resource List...", "Done!", True))
        t4.start()


    def run_threads(self, thread_list, message, done_message, start=True):
        """ Takes a list of threads, starts them, waits for them to stop and writes status messages """
        if start:
            for each in thread_list:
                each.start()

        self.put_msg(message)

        for i, each in enumerate(thread_list):
            each.join()

        self.put_msg(done_message)

    def populate_all(self):
        """Creates multiple threads and populates all the tables"""
        if not self.vtol_sync.vtolvrmissions_online:
            self.display_message("VTOLVRMissions.com Offline", "VTOLVRMissions.com is currently offline, we will only show local resources. Try refreshing data later.")

        t1 = threading.Thread(target=self.populate_campaigns)
        t2 = threading.Thread(target=self.populate_missions)
        t3 = threading.Thread(target=self.populate_maps)
        threads = [t1, t2, t3]

        t4 = threading.Thread(target=self.run_threads, args=(threads, "Loading resources...", "Done!", True))
        t4.start()

    def populate_missions(self):
        """Populates the mission table"""
        for mission in self.vtol_sync.all_missions():
            if "managed" in mission:
                if mission['managed']:

                    values = (mission['downloads'], mission['rating'], mission['details']['category'], mission['author'], mission['cur_version'], mission['local_version'], mission['resource_id'])

                    if not treeview_search(self.mission_tree, values):
                        self.mission_tree.insert("", "end", text="%s" % (mission['title']), values=values)
                else:
                    if self.show_unmanaged.get():
                        self.mission_tree.insert("", "end", text="%s" % (mission['vtol_id']), values=("Unmanaged", "Unmanaged", "Unmanaged" "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged"))
            else:
                self.mission_tree.insert("", "end", text="%s" % (mission['title']), values=(mission['downloads'], mission['rating'], mission['details']['category'], mission['author'], mission['cur_version'], "Not Downloaded", mission['resource_id']))

    def populate_campaigns(self):
        """Populates the campaign table"""
        for campaign in self.vtol_sync.all_campaigns():
            if "managed" in campaign:
                if campaign['managed']:
                    self.campaign_tree.insert("", "end", text="%s" % (campaign['title']), values=(campaign['downloads'], campaign['rating'], campaign['details']['category'], campaign['author'], campaign['cur_version'], campaign['local_version'], campaign['resource_id']))
                else:
                    if self.show_unmanaged.get():
                        self.campaign_tree.insert("", "end", text="%s" % (campaign['vtol_id']), values=("Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged"))
            else:
                self.campaign_tree.insert("", "end", text="%s" % (campaign['title']), values=(campaign['downloads'], campaign['rating'], campaign['details']['category'], campaign['author'], campaign['cur_version'], "Not Downloaded", campaign['resource_id']))

    def populate_maps(self):
        """Populates the map table"""
        for map in self.vtol_sync.all_maps():
            if "managed" in map:
                if map['managed']:
                    self.map_tree.insert("", "end", text="%s" % (map['title']), values=(int(map['downloads']), map['rating'], map['author'], map['cur_version'], map['local_version'], map['resource_id']))
                else:
                    if self.show_unmanaged.get():
                        self.map_tree.insert("", "end", text="%s" % (map['vtol_id']), values=("Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged"))
            else:
                self.map_tree.insert("", "end", text="%s" % (map['title']), values=(int(map['downloads']), map['rating'], map['author'], map['cur_version'], "Not Downloaded", map['resource_id']))


    def client_exit(self):
        try:
            if self.vtol_sync:
                self.vtol_sync.clean_up_temp_folders()
        except Exception as err:
            logger.error("Error cleaning up temp: %s" % err)
        sys.exit(0)

def main():

    root = Tk()
    root.geometry("1225x350")
    root.lift()
    os.system('''/usr/bin/osascript -e 'tell app "Finder" to set frontmost of process "Python" to true' ''')

    app = Window(root)
    root.protocol("WM_DELETE_WINDOW", app.client_exit)

    #Run it
    app.populate_all()
    root.mainloop()


if __name__ == '__main__':
    main()