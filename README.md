# m2j

## What is it?

Cross-platform mouse-to-joystick emulator written in Python (2.7 and 3).

## Features

 * Cross-platform: designed to be run under Linux and Windows (currently only 32-bit environments were tested).
 * Can map input from multiple input devices to multiple output devices (virtual joysticks). The configuration that uses 2 mice is quite convenient.  
 * Is extensively configurable: the actual mapping is specified not in the code, but in JSON configuration files.  

## Python 2 and Python 3 versions available

The project was initially developed to be run by Python 2 to support as low as 32-bit Windows XP. Windows version of `m2j` uses `pywin32` library. The last version of Python 3 that supports Windows XP is 3.4.4, but `pywin32` requires at least Python 3.5. Linux version of `m2j` uses `evdev` library, that requires at least Python 3.5, but can be backported to Python 2.7.  

## What's inside

### Code

#### Python 2

 * `m2j.py` - platform-independent library code
 * `m2j_linux.py` - run this under Linux
 * `m2j_win.py` - run this under Windows
 
#### Python 3

 * `m2j3.py` - platform-independent library code
 * `m2j_linux3.py` - run this under Linux
 * `m2j_win3.py` - run this under Windows

### Configuration files

 * `curves.cfg` - main config file, contains config nodes that are used to initialize a configuration
 * `m2j_cfg.cfg` - contains settings that are common for all configurations  
 * `m2j_1mouse.cfg` - config file for 1-mouse configuration
 * `m2j_2mice2.cfg` - config file for 2-mice configuration (the mostly useful one, see `BINDS.md` for binds)
 * `m2j_2mice2_ht.cfg` - config file for 2-mice configuration with airmouse (like G10) used as head tracker
 * `m2j_3mice.cfg` - config file for 3-mice configuration (experimental!)
 * `m2j_linux.cfg` - mix-in config file for running under Linux
 * `m2j_1mouse_linux.cfg` - config file for running 1-mouse configuration under Linux
 * `m2j_2mice2_linux.cfg` - config file for running 2-mice configuration under Linux
 * `m2j_2mice2_ht_linux.cfg` - config file for running 2-mice configuration with airmouse used as head tracker
 * `m2j_3mice_linux.cfg` - config file for running 3-mice configuration under Linux
 * `m2j_win.cfg` - mix-in config file for running under Windows
 * `m2j_1mouse_win.cfg` - config file for running 1-mouse configuration under Windows
 * `m2j_2mice2_win.cfg` - config file for running 2-mice configuration under Windows
 * `m2j_3mice_win.cfg` - config file for running 3-mice configuration under Windows

Also, be sure to check companion utilities that can be used alongside with `m2j`:

 * `joy2tir` ([Github](https://github.com/fedorov-ao/joy2tir)) - maps input from joysticks to (unencrypted) TrackIR
 * `dinput8blocker` ([Github](https://github.com/fedorov-ao/dinput8blocker)) - used to block and unblock input from DirectInput8 devices (i.e. mouse)
 * `raw_input_blocker` ([Github](https://github.com/fedorov-ao/raw_input_blocker)) - used to block and unblock input from raw input devices (i.e. mouse)

`raw_input_blocker` is preferable over `dinput8blocker`, because the former can block one selected mouse out of several mice used.

## How to install and run

### Linux

#### Installing

##### Dependencies 

 * `playsound` module - for playing sounds ([Github](https://pypi.org/project/playsound))  
 * `evdev` module - for reading and emulating input ([Github](https://github.com/gvalkov/python-evdev))  

##### Installation procedure

(# means running command in shell as root, $ - as regular user)

###### Python 2

Compile the last version of Python 2.7 (2.7.18) if needed  
`#apt install tk tk-dev libssl-dev`  
`$wget https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tar.xz`  
`$tar -xf Python-2.7.18.tar.xz`  
`cd Python-2.7.18`  
`./configure && make`  
NB: configuring with `--enable-optimizations` and compiling subsequently causes Python's `ssl` module test fail.  

Instal pip for Python 2.7 if needed  
`$wget https://bootstrap.pypa.io/pip/2.7/get-pip.py`  
`$python2 get-pip.py`  

Install `playsound` module  
`$pip2 install playsound`  

Install `evdev` module  
At the time of writing (19.02.2024) the last version of evdev is 1.7.0. It is supposed to be run under Python >= 3.5 and needs to be backported to Python 2.7.  
The patch is in `3rdparty/evdev/evdev-1.7.0-py27.patch`, updated files are in `3rdparty/evdev/evdev-1.7.0-py27`.  

Installing evdev-1.7.0 for Python 2.7  

`$pip2 install pathlib2` (to make evedev setup.py run)  
`$wget https://github.com/gvalkov/python-evdev/archive/refs/tags/v1.7.0.tar.gz`  
`$tar -xf evdev-1.7.0.tar.gz`  
`$cd evdev-1.7.0`  
`$patch -p1 < path/to/evdev-1.7.0-py27.patch` (or `$cp -r /path/to/3rdparty/evdev/evdev-1.7.0-py27/* evdev-1.7.0`)  
`$./setup.py build`  
`$./setup.py install --prefix ~/.local/`  

###### Python 3

Install Python 3

Download `playsound` from ([Github](https://pypi.org/project/playsound)) and unpack `playsound.py` to directory with `m2j_linux3.py` and other script files

Install `evdev`
`$pip3 install evdev` or `#apt install python3-evdev` if `pip3` complains about externally managed environment

###### uinput rights

May need to  
`#modprobe -i uinput`  

`m2j_linux.py` and `m2j_linux3.py` use /dev/uinput , which typically belongs to user root and group root. In order to be able to run emulator without sudo following steps are needed:

add group `uinput` (can be any other appropriate name)  
`#groupadd uinput`  

change the group of /dev/uinput to `uinput`  
`#chown root:uinput /dev/uinput`

add `udev` rule, otherwise group will be reset to `root` on reboot  
`#echo 'KERNEL=="uinput", GROUP="uinput"' | tee /etc/udev/rules.d/90-uinput-group.rules`

change group permissions of `/dev/uinput` to `rw`  
`#chmod g+rw /dev/uinput`

add the user to the group `uinput`  
`#usermod -a -G uinput username`

reboot

check  
`$ls -l /dev/uinput`  
`crw-rw---- 1 root uinput 10, 223 янв  6 19:51 /dev/uinput`  
`$groups`  
`user ... uinput`  

#### Running

`$./m2j_linux[3].py` or `$./m2j_linux[3].py -h` - for get help about command-line switches  
`$./m2j_linux[3].py -c configname.cfg` - to use configuration specified in `configname.cfg`. I.e. `$./m2j_linux.py -c m2j_1mouse_linux.cfg` runs Python 2-based script with 1-mouse configuration.  

### Windows 

#### Installing

##### Python 2

###### Dependencies

 * `playsound` module - for playing sounds  
 * `pywin32` module - for reading and emulating input ([Github](https://github.com/mhammond/pywin32); last build supporting Python 2.7 is [228](https://github.com/mhammond/pywin32/releases/tag/b228))  
 * virtual joystick driver - for creating virtual joysticks that will be controlled by the emulator:  
    * `ppjoy` (supports up to 32-bit (?) Windows XP; [Github](https://github.com/elitak/PPJoy/releases)) or
    * `vJoy` ([Github](https://sourceforge.net/projects/vjoystick/); forks: [\[1\]](https://github.com/shauleiz/vJoy), [\[2\]](https://github.com/jshafer817/vJoy), [\[3\]](https://github.com/njz3/vJoy/). It seems that fork 3 is the most recent, [last build](https://github.com/njz3/vJoy/releases/tag/v2.2.1.1) requires at least 32-bit Windows 7.)  

###### Installation procedure

####### Python 2

Install Python 2

In command line: `pip install pywin32 playsound`

####### Python 3

Install Python 3

In command line: `pip install pywin32 playsound`

####### Common steps

Install appropriate virtual joystick driver  

Create 5 joysticks (8 axes and 16 buttons each)

Use [dinput8blocker](https://github.com/fedorov-ao/dinput8blocker) wrapper DLL to enable and disable mouse input for the game using DirectInput API. Alternatively, try [raw_input_blocker](https://github.com/fedorov-ao/raw_input_blocker) wrapper DLL to block/unblock raw mouse input.

##### Running

`m2j_win[3].py` or `m2j_win[3].py -h` - for get help about command-line switches  
`m2j_win[3].py -c configname.cfg` - to use configuration specified in `configname.cfg` I.e. `m2j_win.py -c m2j_1mouse_win.cfg` runs Python 2-based script with 1-mouse configuration.  

### Command-line switches

`-h | --help : help message`  
`-d fileName | --devices=fileName : print input devices info to file fileName (- for stdout)`  
`-j fileName | --devices_json=fileName : print input devices JSON config to file fileName (- for stdout)`  
`-i | --log_input : log input from input devices to console (Ctrl-C to exit)`  
`-p presetName | --preset=presetName : use preset presetName`  
`-c configFileName | --config=configFileName : use config file configFileName`  
`-v log_level | --log_level=logLevel : set log level to logLevel`  
