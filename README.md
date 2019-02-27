# VTOLVRMissions.com Downloader
This is a Windows client intended to simplify the process of finding, downloading, and installing various custom resources (e.g. Campaigns, Maps, and Missions) into VTOL VR.

Sidenote: This is the first GUI I've written in Python so it's probably not done "the right way", but it is "mostly" functional and should meet most requirements. Feel free to report any issues in the issues section of github, or find me on the VTOL VR discord.

## Running It
It is recommended that you download the compiled Windows version located in the releases section. Of course you are more than welcome to download the Python source code, review it and/or manually run it if you are familiar with the language.

### Potential Problems
 - Unmanaged resources can be seen by going to settings and checking "Show unmanaged resources". The tables will refresh and show you all the resources in which the metadata file doesn't exist OR could not be parsed.

### How it Works
If you're curious about how it works this is essentially a summary of the mess of spaghetti code.

1. Client starts, and checks if it is able to read the Windows Registry
    - If it is able to read the Windows Registry, it gets the Steam Install location (HKCU\Software\Valve\Steam\SteamPath)
      - In the install location steam has a VDF file containing all the Game Library locations.
      - The script will then check each library location for the VTOL VR directory.
    - If it isn't able to read the windows registry a prompt is displayed to the user to manually provide the location to VTOL VR
2. The client then loads all the local resources (Campaigns, Maps, and Missions) from VTOL VR and checks if each folder has a "vtolvrmissions.com_metadata.json" file in it. If it does, it reads the file to extract the resource metadata.
3. The client then reaches out to vtolvrmissions.com to read all the other resources available. The locations are hardcoded to only the following:
   - Missions
   - Campaigns
   - Maps
   - If other categories (major or minor) exist, the script will not even see them.
4. A comparison is done to determine if the local version of the metadata is the most recent. If it is not, the metadata is updated locally.
5. Downloaded resources are saved to a temp file within the running directory. The resource is extracted, parsed for some sanity and then moved to the proper location.
   - A vtolvrmissions.com_metadata.json file is created within the same directory of the resource containing the stored metadata information.

## Development/Running from Source
The app is written in Python 3.5 and should work with most major versions, however it has not been tested. It is recommended to create a Virtual Environment and installing the requirements.txt that way. It should... just work.

## TODO
  - Implement better logging/display logs to the user
  - Clean up the thread mess (implement pyqt instead of tkinter?)

