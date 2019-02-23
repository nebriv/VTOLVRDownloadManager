from tkinter import *

from tkinter import *

from tkinter import ttk
import os
from tkinter import scrolledtext

from tkinter import Tk, RIGHT, BOTH, RAISED
from tkinter.ttk import Frame, Button, Style
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from downloader import Syncer, auto_discover_vtol_dir
from tkinter import messagebox

import threading

import logging
try:
    from Tkinter import *
    from ttk import *
except ImportError:  # Python 3
    from tkinter import *
    from tkinter.ttk import *

class Window(Frame):

    def __init__(self, master=None):
        Frame.__init__(self, master)

        try:
            steam_dir = auto_discover_vtol_dir()
        except ModuleNotFoundError as err:
            logging.error("%s" % err)
            steam_dir = "/Users/bvirgilio-domain/VTOLVRDownloadManager/steam_dir"

        self.vtol_sync = Syncer(steam_dir, "https://www.vtolvrmissions.com/")
        self.show_unmanaged = IntVar()
        self.show_unmanaged.set(False)

        self.master = master
        self.main_window()

    def main_window(self):
        self.master.title("GUI")
        self.pack(fill=BOTH, expand=1)

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(3, weight=1)

        nb = ttk.Notebook(self)
        campaign_page = ttk.Frame(nb)
        nb.add(campaign_page, text="Campaigns")
        mission_page = ttk.Frame(nb)
        nb.add(mission_page, text="Missions")
        map_page = ttk.Frame(nb)
        nb.add(map_page, text="Maps")

        settings_page = ttk.Frame(nb)
        nb.add(settings_page, text="Settings")

        nb.grid(row=1, column=1, columnspan=3)

        # Settings Page
        settings_page.grid_rowconfigure(10)
        settings_page.grid_columnconfigure(2, weight=1)
        Checkbutton(settings_page, text="Show Unmanaged Resources", variable=self.show_unmanaged, command=self.refresh_all).grid(row=0, sticky=W, padx=5)

        # Campaign Page
        campaign_page.grid_rowconfigure(10)
        campaign_page.grid_columnconfigure(3, weight=1)

        campaign_content = Frame(campaign_page)
        campaign_content.grid(row=1, column=3, sticky="NS")
        campaign_content.grid_rowconfigure(3)
        campaign_content.grid_columnconfigure(2)
        campaign_vsb = Scrollbar(campaign_content, orient = "vertical")
        self.campaign_tree = Treeview(campaign_content, yscrollcommand = campaign_vsb.set)
        campaign_vsb.configure(command=self.campaign_tree.yview)

        self.campaign_tree['columns'] = ("Name", "Tag Line", "Author", "Online_Version", "Local_Version", "resource_id")
        self.campaign_tree['displaycolumns'] = ("Name", "Tag Line", "Author", "Online_Version", "Local_Version")
        self.campaign_tree.heading("#0", text="Name")
        self.campaign_tree.column("#0", minwidth=200, width=200)

        self.campaign_tree.heading("#1", text="Tag Line")
        self.campaign_tree.column("#1", minwidth=550, width=550)

        self.campaign_tree.heading("#2", text="Author")
        self.campaign_tree.column("#2", minwidth=100, width=100)

        self.campaign_tree.heading("#3", text="Online Version")
        self.campaign_tree.column("#3", minwidth=100, width=100)

        self.campaign_tree.heading("#4", text="Local Version")
        self.campaign_tree.column("#4", minwidth=150, width=150)

        self.campaign_tree.heading("#5", text="")
        self.campaign_tree.column("#5", minwidth=0, width=0)

        self.campaign_tree.grid(row=1, column=3, sticky="NS")
        campaign_vsb.grid(row=1, column=4, sticky='ns')

        campaign_buttons = Frame(campaign_content)
        campaign_buttons.grid(row=2, column=3)
        campaign_buttons.grid_rowconfigure(1)
        campaign_buttons.grid_columnconfigure(2)

        campaign_download_button = Button(campaign_buttons, text="Install/Update", command= lambda: self.download_button(self.campaign_tree) )
        campaign_download_button.grid(row=1, column=1)

        campaign_remove_button = Button(campaign_buttons, text="Remove", command= lambda: self.remove_button(self.campaign_tree) )
        campaign_remove_button.grid(row=1, column=2)

        # Mission Page
        mission_page.grid_rowconfigure(10)
        mission_page.grid_columnconfigure(3, weight=1)

        mission_content = Frame(mission_page)
        mission_content.grid(row=1, column=3, sticky="NS")
        mission_content.grid_rowconfigure(3)
        mission_content.grid_columnconfigure(2)
        mission_vsb = Scrollbar(mission_content, orient = "vertical")
        self.mission_tree = Treeview(mission_content, yscrollcommand = mission_vsb.set)
        mission_vsb.configure(command=self.mission_tree.yview)

        self.mission_tree['columns'] = ("Name", "Tag Line", "Author", "Online_Version", "Local_Version", "resource_id")
        self.mission_tree['displaycolumns'] = ("Name", "Tag Line", "Author", "Online_Version", "Local_Version")
        self.mission_tree.heading("#0", text="Name")
        self.mission_tree.column("#0", minwidth=200, width=200)

        self.mission_tree.heading("#1", text="Tag Line")
        self.mission_tree.column("#1", minwidth=550, width=550)

        self.mission_tree.heading("#2", text="Author")
        self.mission_tree.column("#2", minwidth=100, width=100)

        self.mission_tree.heading("#3", text="Online Version")
        self.mission_tree.column("#3", minwidth=100, width=100)

        self.mission_tree.heading("#4", text="Local Version")
        self.mission_tree.column("#4", minwidth=150, width=150)

        self.mission_tree.heading("#5", text="")
        self.mission_tree.column("#5", minwidth=0, width=0)

        self.mission_tree.grid(row=1, column=3, sticky="NS")
        mission_vsb.grid(row=1, column=4, sticky='ns')

        mission_buttons = Frame(mission_content)
        mission_buttons.grid(row=2, column=3)
        mission_buttons.grid_rowconfigure(1)
        mission_buttons.grid_columnconfigure(2)

        mission_download_button = Button(mission_buttons, text="Install/Update", command= lambda: self.download_button(self.mission_tree) )
        mission_download_button.grid(row=1, column=1)

        mission_remove_button = Button(mission_buttons, text="Remove", command= lambda: self.remove_button(self.mission_tree) )
        mission_remove_button.grid(row=1, column=2)


        # Map Page
        map_page.grid_rowconfigure(10)
        map_page.grid_columnconfigure(3, weight=1)

        map_content = Frame(map_page)
        map_content.grid(row=1, column=3, sticky="NS")
        map_content.grid_rowconfigure(3)
        map_content.grid_columnconfigure(2)
        map_vsb = Scrollbar(map_content, orient = "vertical")
        self.map_tree = Treeview(map_content, yscrollcommand = map_vsb.set)
        map_vsb.configure(command=self.map_tree.yview)

        self.map_tree['columns'] = ("Name", "Tag Line", "Author", "Online_Version", "Local_Version", "resource_id")
        self.map_tree['displaycolumns'] = ("Name", "Tag Line", "Author", "Online_Version", "Local_Version")
        self.map_tree.heading("#0", text="Name")
        self.map_tree.column("#0", minwidth=200, width=200)

        self.map_tree.heading("#1", text="Tag Line")
        self.map_tree.column("#1", minwidth=550, width=550)

        self.map_tree.heading("#2", text="Author")
        self.map_tree.column("#2", minwidth=100, width=100)

        self.map_tree.heading("#3", text="Online Version")
        self.map_tree.column("#3", minwidth=100, width=100)

        self.map_tree.heading("#4", text="Local Version")
        self.map_tree.column("#4", minwidth=150, width=150)

        self.map_tree.heading("#5", text="")
        self.map_tree.column("#5", minwidth=0, width=0)

        self.map_tree.grid(row=1, column=3, sticky="NS")
        map_vsb.grid(row=1, column=4, sticky='ns')

        map_buttons = Frame(map_content)
        map_buttons.grid(row=2, column=3)
        map_buttons.grid_rowconfigure(1)
        map_buttons.grid_columnconfigure(2)

        map_download_button = Button(map_buttons, text="Install/Update", command= lambda: self.download_button(self.map_tree) )
        map_download_button.grid(row=1, column=1)

        map_remove_button = Button(map_buttons, text="Remove", command= lambda: self.remove_button(self.map_tree) )
        map_remove_button.grid(row=1, column=2)

        quitButton = Button(self, text="Quit", command=self.client_exit)
        quitButton.grid(row=4, column=3)

        menu = Menu(self.master)
        self.master.config(menu=menu)

        file = Menu(menu)
        file.add_command(label="Refresh Data", command=self.refresh_all)
        file.add_command(label="Exit", command=self.client_exit)
        menu.add_cascade(label="File", menu=file)

    def error_and_exit(self, title, msg):
        messagebox.showerror(title, msg)
        self.client_exit()

    def display_error(self, title, msg):
        messagebox.showerror(title, msg)

    def display_message(self, title, msg):
        messagebox.showinfo(title, msg)

    def remove_button(self, tree_item):
        curItem = tree_item.focus()
        if tree_item.item(curItem)['values'][-1] == "Unmanaged":
            self.display_error("Unmanaged resource", "This resource is unmanaged, please remove it manually")
        else:
            resource = self.vtol_sync.get_resource_by_id(tree_item.item(curItem)['values'][-1])
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
                self.display_error("Removal Failed", "Failed to remove %s" % (tree_item.item(curItem)['title']))

    def download_button(self, tree_item):
        curItem = tree_item.focus()
        if tree_item.item(curItem)['values'][-1] == "Unmanaged":
            self.display_error("Unmanaged resource", "This is a local unmanaged resource, it cannot be installed")
        else:
            resource = self.vtol_sync.get_resource_by_id(tree_item.item(curItem)['values'][-1])

            try:
                self.vtol_sync.download_resource(resource)
            except Exception as err:
                self.display_error("Error downloading resource", err)
            if resource['resource_type'] == "map":
                self.refresh_maps()
            elif resource['resource_type'] == "campaign":
                self.refresh_campaigns()
            elif resource['resource_type'] == "mission":
                self.refresh_missions()
            else:
                self.refresh_all()

    def refresh_maps(self):
        # Clear Map Data
        for i in self.map_tree.get_children():
            self.map_tree.delete(i)
        self.populate_maps()

    def refresh_campaigns(self):
        # Clear Campaign Data
        for i in self.campaign_tree.get_children():
            self.campaign_tree.delete(i)
        self.populate_campaigns()

    def refresh_missions(self):
        # Clear Mission Data
        for i in self.mission_tree.get_children():
            self.mission_tree.delete(i)
        self.populate_missions()

    def refresh_all(self):
        self.refresh_campaigns()
        self.refresh_maps()
        self.refresh_missions()

    def populate_all(self):
        # try:
        t1 = threading.Thread(target=self.populate_campaigns)
        t1.start()

        t2 = threading.Thread(target=self.populate_missions)
        t2.start()

        t3 = threading.Thread(target=self.populate_maps)
        t3.start()
        #t1.join()
        #self.populate_campaigns()
        #self.populate_missions()
        #self.populate_maps()
        # except Exception as err:
        #     self.error_and_exit("A fatal error occured",  err)
        # self.vtol_sync.get_online_all()
        # self.vtol_sync.get_local_all()

    def populate_missions(self):
        for mission in self.vtol_sync.all_missions():
            if "managed" in mission:
                if mission['managed']:
                    self.mission_tree.insert("", "end", text="%s" % (mission['title']), values=(mission['tag_line'], mission['author'], mission['cur_version'], mission['local_version'], mission['resource_id']))
                else:
                    if self.show_unmanaged.get():
                        self.mission_tree.insert("", "end", text="%s" % (mission['vtol_id']), values=("Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged"))
            else:
                self.mission_tree.insert("", "end", text="%s" % (mission['title']), values=(mission['tag_line'], mission['author'], mission['cur_version'], "Not Downloaded", mission['resource_id']))

    def populate_campaigns(self):
        for campaign in self.vtol_sync.all_campaigns():
            if "managed" in campaign:
                if campaign['managed']:
                    self.campaign_tree.insert("", "end", text="%s" % (campaign['title']), values=(campaign['tag_line'], campaign['author'], campaign['cur_version'], campaign['local_version'], campaign['resource_id']))
                else:
                    if self.show_unmanaged.get():
                        self.campaign_tree.insert("", "end", text="%s" % (campaign['vtol_id']), values=("Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged"))
            else:
                self.campaign_tree.insert("", "end", text="%s" % (campaign['title']), values=(campaign['tag_line'], campaign['author'], campaign['cur_version'], "Not Downloaded", campaign['resource_id']))

    def populate_maps(self):
        for map in self.vtol_sync.all_maps():
            if "managed" in map:
                if map['managed']:
                    self.map_tree.insert("", "end", text="%s" % (map['title']), values=(map['tag_line'], map['author'], map['cur_version'], map['local_version'], map['resource_id']))
                else:
                    if self.show_unmanaged.get():
                        self.map_tree.insert("", "end", text="%s" % (map['vtol_id']), values=("Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged", "Unmanaged"))
            else:
                self.map_tree.insert("", "end", text="%s" % (map['title']), values=(map['tag_line'], map['author'], map['cur_version'], "Not Downloaded", map['resource_id']))

    def client_exit(self):
        exit()

def main():
    root = Tk()
    root.geometry("1150x330")
    root.lift()
    os.system('''/usr/bin/osascript -e 'tell app "Finder" to set frontmost of process "Python" to true' ''')

    app = Window(root)

    #Run it
    #root.after(1000, app.get_vtol_data)
    root.after(1000, app.populate_all)
    root.mainloop()

    #
    # root.master.get_vtol_data()
    # root.master.populate_campaigns()
    # root.update()



if __name__ == '__main__':
    main()