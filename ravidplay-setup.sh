#!/bin/bash
scriptdir=`pwd`

# Download external libraries from https://github.com if they don't exist:
if [ ! -d python-omxplayer-wrapper ]; then
    git clone https://github.com/willprice/python-omxplayer-wrapper.git
else
    echo "Directory ./python-omxplayer-wrapper already exists"
fi
# Install external libraries:
# python-omxplayer-wrapper v0.3.3
cd python-omxplayer-wrapper
sudo python3 setup.py install
sudo python3 -m pip install mock
cd ..
