#!/bin/bash

# set volume to max
# does not work when run at startup, seems to 
# come too early i.e. before session login
# 
# this is now done in soundserver.py
# /usr/bin/osascript -e 'set volume output volume 100'

cd /Users/daqflipper/sound/software
# screen -m -d -L -S soundserver ./soundserver.py

# launchd will redirect things to the correpsonding
# files
# 
# (see also http://superuser.com/a/548055/45396 for
# launchd configuration options not to kill
# any leftover daughter processes)
./soundserver.py

