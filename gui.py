from tkinter import *

from tkinter import *

from tkinter import ttk
import os
from tkinter import scrolledtext
def donothing():
    filewin = Toplevel(root)
    button = Button(filewin, text="Do nothing button")
    button.pack()

#
# root = Tk()
#
# root.geometry('1200x800')
#
# menubar = Menu(root)
# filemenu = Menu(menubar, tearoff=0)
# filemenu.add_command(label="Refresh", command=donothing)
#
# filemenu.add_separator()
#
# filemenu.add_command(label="Exit", command=root.quit)
# menubar.add_cascade(label="File", menu=filemenu)
#
# root.title("Welcome to LikeGeeks app")
#
#
#
#
# txt = scrolledtext.ScrolledText(root, width=40, height=10)
#
# txt.grid(column=0, row=4)
#
# txt.insert(INSERT, "Test testestestest")
#
#
#
# root.config(menu=menubar)
# root.mainloop()

from tkinter import Tk, RIGHT, BOTH, RAISED
from tkinter.ttk import Frame, Button, Style
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from downloader import Syncer, auto_discover_vtol_dir
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
        self.master = master
        self.init_window()

    def init_window(self):
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
        nb.grid(row=1, column=1, columnspan=3)

        campaign_page.grid_rowconfigure(10)
        campaign_page.grid_columnconfigure(3, weight=1)

        # Campaign Page
        self.campaign_tree = Treeview(campaign_page)
        self.campaign_tree['columns'] = ("Name", "Tag Line", "Author", "Category", "Online_Version", "Local_Version", "resource_id")

        self.campaign_tree.heading("#0", text="Name")
        self.campaign_tree.heading("#1", text="Tag Line")
        self.campaign_tree.heading("#2", text="Author")
        self.campaign_tree.heading("#3", text="Category")
        self.campaign_tree.heading("#4", text="Online Version")
        self.campaign_tree.heading("#5", text="Local Version")

        # Mission Page
        mission_page.grid_rowconfigure(10)
        mission_page.grid_columnconfigure(3, weight=1)

        self.mission_tree = Treeview(mission_page)
        self.mission_tree['columns'] = ("Name", "Tag Line", "Author", "Category", "Online_Version", "Local_Version", "resource_id")
        self.mission_tree.heading("#0", text="Name")
        self.mission_tree.heading("#1", text="Tag Line")
        self.mission_tree.heading("#2", text="Author")
        self.mission_tree.heading("#3", text="Category")
        self.mission_tree.heading("#4", text="Online Version")
        self.mission_tree.heading("#5", text="Local Version")

        # Map Page
        map_page.grid_rowconfigure(10)
        map_page.grid_columnconfigure(3, weight=1)

        self.map_tree = Treeview(map_page)
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

        self.campaign_tree.grid(row=1, column=3)
        self.mission_tree.grid(row=1, column=3)
        self.map_tree.grid(row=1, column=3)

        map_download_button = Button(map_page, text="Install/Update", command= lambda: self.download_button(self.map_tree) )
        map_download_button.grid(row=2, column=3)

        quitButton = Button(self, text="Quit", command=self.client_exit)
        quitButton.grid(row=4, column=4)

        menu = Menu(self.master)
        self.master.config(menu=menu)

        file = Menu(menu)
        file.add_command(label="Refresh Data", command=self.refresh_all)
        file.add_command(label="Exit", command=self.client_exit)
        menu.add_cascade(label="File", menu=file)


    def download_button(self, tree_item):
        curItem = tree_item.focus()

        resource = self.vtol_sync.get_resource_by_id(tree_item.item(curItem)['values'][-1])

        self.vtol_sync.download_resource(resource)

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
        self.populate_campaigns()
        self.populate_missions()
        self.populate_maps()
        # self.vtol_sync.get_online_all()
        # self.vtol_sync.get_local_all()

    def populate_missions(self):
        for mission in self.vtol_sync.all_missions():
            if mission['downloaded']:
                self.mission_tree.insert("", "end", text="%s" % (mission['title']), values=(mission['tag_line'], mission['author'], mission['details']['category'], mission['cur_version'], mission['local_version'], mission['resource_id']))
            else:
                self.mission_tree.insert("", "end", text="%s" % (mission['title']), values=(mission['tag_line'], mission['author'], mission['details']['category'], mission['cur_version'], "Not Downloaded", mission['resource_id']))

    def populate_campaigns(self):
        for campaign in self.vtol_sync.all_campaigns():
            if campaign['downloaded']:
                self.campaign_tree.insert("", "end", text="%s" % (campaign['title']), values=(campaign['tag_line'], campaign['author'], campaign['details']['category'], campaign['cur_version'], campaign['local_version'], campaign['resource_id']))
            else:
                self.campaign_tree.insert("", "end", text="%s" % (campaign['title']), values=(campaign['tag_line'], campaign['author'], campaign['details']['category'], campaign['cur_version'], "Not Downloaded", campaign['resource_id']))

    def populate_maps(self):
        for map in self.vtol_sync.all_maps():
            if map['downloaded']:
                self.map_tree.insert("", "end", text="%s" % (map['title']), values=(map['tag_line'], map['author'], map['cur_version'], map['local_version'], map['resource_id']))
            else:
                self.map_tree.insert("", "end", text="%s" % (map['title']), values=(map['tag_line'], map['author'], map['cur_version'], "Not Downloaded", map['resource_id']))

    def client_exit(self):
        exit()

def main():
    root = Tk()
    root.geometry("1400x400")
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