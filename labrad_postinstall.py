# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import sys

menuDir = "LabRAD"
menuPath = os.path.join(get_special_folder_path("CSIDL_COMMON_PROGRAMS"),
                        menuDir)
scriptsPath = os.path.join(sys.prefix, 'Scripts')
configPath = os.path.join(sys.prefix, 'Lib', 'site-packages', 'labrad', 'config')

def mkdir(a, *p):
    """Make a directory and tell the installer."""
    path = os.path.join(a, *p)
    if not os.path.isdir(path):
        os.mkdir(path)
        directory_created(path)

def rmdir(a, *p):
    path = os.path.join(a, *p)
    os.rmdir(path)
    
def create_local_copy(globname, locname):
    if not os.path.exists(locname):
        with open(globname) as globfile:
            with open(locname, 'w') as locfile:
                # skip the first five lines, which are a note
                # about making a local copy
                locfile.writelines(globfile.readlines()[5:])
    
def install():
    print "Creating start menu entries..."
    mkdir(menuPath)

    nodeShortcut = os.path.join(menuPath, "LabRAD Node.lnk")
    if os.path.isfile(nodeShortcut):
        os.remove(nodeShortcut)
    create_shortcut("twistd.py", "Node to start and stop LabRAD servers",
	            nodeShortcut, "-n labradnode")
    file_created(nodeShortcut)
	
    # create local copy of configuration
    create_local_copy(os.path.join(configPath, "node-template.ini"),
                      os.path.join(configPath, "node.ini"))
    nodeConf = os.path.join(menuPath, "LabRAD Node Config.lnk")
    if os.path.isfile(nodeConf):
        os.remove(nodeConf)
    create_shortcut(os.path.join(configPath, "node.ini"),
                    "Node Configuration", nodeConf)
    file_created(nodeConf)

	
    controllerShortcut = os.path.join(menuPath, "LabRAD Controller.lnk")
    if os.path.isfile(controllerShortcut):
        os.remove(controllerShortcut)
    create_shortcut("twistd.py", "Web control for LabRAD, localhost:7667",
	            controllerShortcut, "-n labradcontrol")
    file_created(controllerShortcut)
    
    # create local copy of configuration
    create_local_copy(os.path.join(configPath, "controller-template.ini"),
                      os.path.join(configPath, "controller.ini"))
    controllerConf = os.path.join(menuPath, "LabRAD Controller Config.lnk")
    if os.path.isfile(controllerConf):
        os.remove(controllerConf)
    create_shortcut(os.path.join(configPath, "controller.ini"),
                    "Controller Configuration", controllerConf)
    file_created(controllerConf)

    
    ipyShortcut = os.path.join(menuPath, "LabRAD Shell.lnk")
    ipyScript = os.path.join(configPath, "ipythonrc-labrad.ini")
    if os.path.isfile(ipyShortcut):
        os.remove(ipyShortcut)
    create_shortcut(os.path.join(scriptsPath, 'ipython.py'), "",
                    ipyShortcut, "-rcfile %s" % ipyScript)
    file_created(ipyShortcut)
    
    ipyShortcut = os.path.join(menuPath, "LabRAD Tutorial.lnk")
    ipyScript = os.path.join(configPath, "ipythonrc-labrad_tut.ini")
    if os.path.isfile(ipyShortcut):
        os.remove(ipyShortcut)
    create_shortcut(os.path.join(scriptsPath, 'ipython.py'), "",
                    ipyShortcut, "-rcfile %s" % ipyScript)
    file_created(ipyShortcut)
    
    print "Done."
    
    
def remove():
    pass


if __name__ == '__main__':
    if sys.argv[1] == '-install':
        install()
    elif sys.argv[1] == '-remove':
        remove()
    else:
        raise Exception('Unknown options: %s.' % sys.argv)