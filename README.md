# m2j

## What is it?

Cross-platform mouse-to-joystick emulator written in Python (2.7).

## Features

 * Cross-platform: designed to be run under Linux and Windows (currently only 32-bit environments were tested).
 * Can map input from multiple input devices to multiple output devices (virtual joysticks). The configuration that uses 2 mice is quite convenient.  
 * Is extensively configurable: the actual mapping is specified not in the code, but in JSON configuration files.  

## Why Python 2?

Because of dependencies (namely, `pywin32`). The project aims to support as low as 32-bit Windows XP. The last version of Python 3 that supports Windows XP is 3.4.4, but `pywin32` requires at least Python 3.5. `evdev` used under Linux requires at least Python 3.5, but can be backported to Python 2.7.  

## What's inside

### Code

 * `m2j.py` - platform-independent library code
 * `m2j_linux.py` - run this under Linux
 * `m2j_win.py` - run this under Windows
 
### Configuration files

 * `curves.cfg` - main config file, contains config nodes that are used to initialize a configuration
 * `m2j_cfg.cfg` - contains settings that are common for all configurations  
 * `m2j_1mouse.cfg` - config file for 1-mouse configuration
 * `m2j_2mice2.cfg` - config file for 2-mice configuration (the mostly useful one, see `BINDS.md` for binds)
 * `m2j_3mice.cfg` - config file for 3-mice configuration (experimental!)
 * `m2j_linux.cfg` - mix-in config file for running under Linux
 * `m2j_1mouse_linux.cfg` - config file for running 1-mouse configuration under Linux
 * `m2j_2mice2_linux.cfg` - config file for running 2-mice configuration under Linux
 * `m2j_3mice_linux.cfg` - config file for running 3-mice configuration under Linux
 * `m2j_win.cfg` - mix-in config file for running under Windows
 * `m2j_1mouse_win.cfg` - config file for running 1-mouse configuration under Windows
 * `m2j_2mice2_win.cfg` - config file for running 2-mice configuration under Windows
 * `m2j_3mice_win.cfg` - config file for running 3-mice configuration under Windows

Also, be sure to check companion utilities that can be used alongside with `m2j`:

 * `joy2tir` ([Github](https://github.com/fedorov-ao/joy2tir)) - maps input from joysticks to (unencrypted) TrackIR
 * `dinput8blocker` ([Github](https://github.com/fedorov-ao/dinput8blocker)) - used to block and unblock input from DirectInput8 devices (i.e. mouse)

## How to install and run

### Linux

#### Installing

##### Dependencies 

 * `playsound` module - for playing sounds ([Github](https://pypi.org/project/playsound))  
 * `evdev` module - for reading and emulating input ([Github](https://github.com/gvalkov/python-evdev))  

##### Installation procedure

(# means running command in shell as root, $ - as regular user)

Install playsound module  
`$pip install playsound`

Install evdev module  
At the time of writing (19.02.2024) the last version of evdev is 1.7.0. It is supposed to be run under Python >= 3.5 and needs to be backported to Python 2.7.  
The patch is in `3rdparty/evdev/evdev-1.7.0-py27.patch`, updated files are in `3rdparty/evdev/evdev-1.7.0-py27`. 

Installing evdev-1.7.0 for Python 2.7  
`$wget https://github.com/gvalkov/python-evdev/archive/refs/tags/v1.7.0.tar.gz`  
`$tar -xf evdev-1.7.0.tar.gz`  
`$cd evdev-1.7.0`  
`$patch -p1 < path/to/evdev-1.7.0-py27.patch` (or `$cp -r /path/to/3rdparty/evdev/evdev-1.7.0-py27/* evdev-1.7.0`)  
`$./setup.py build`  
`$./setup.py install --prefix ~/.local/`  

May need to  
`#modprobe -i uinput`

`m2j_linux.py` uses /dev/uinput , which typically belongs to user root and group root. In order to be able to run emulator without sudo following steps are needed:

add group "input" (can be any other appropriate name)  
`#groupadd input`

change the group of /dev/uinput to "input"  
`#chown root:input /dev/uinput`

change group permissions of `"/dev/uinput"` to `"rw"`  
`$chmod g+rw /dev/uinput`

add the user to the group "input"  
`#usermod -a -G input username`

reboot

check  
`$ls -l /dev/uinput`  
`crw-rw---- 1 root input 10, 223 янв  6 19:51 /dev/uinput`  
`$groups`  
`user ... input`  

#### Running

`$./m2j_linux.py` or `$./m2j_linux.py -h` - for get help about command-line switches  
`$./m2j_linux.py -c configname.cfg` - to use configuration specified in `configname.cfg`. I.e. `$./m2j_linux.py -c m2j_1mouse_linux.cfg` runs 1-mouse configuration.  

### Windows 

#### Installing

##### Dependencies

 * `playsound` module - for playing sounds  
 * `pywin32` module - for reading and emulating input ([Github](https://github.com/mhammond/pywin32); last build supporting Python 2.7 is [228](https://github.com/mhammond/pywin32/releases/tag/b228))  
 * virtual joystick driver - for creating virtual joysticks that will be controlled by the emulator:  
    * `ppjoy` (supports up to 32-bit (?) Windows XP; [Github](https://github.com/elitak/PPJoy/releases)) or
    * `vJoy` ([Github](https://sourceforge.net/projects/vjoystick/); forks: [\[1\]](https://github.com/shauleiz/vJoy), [\[2\]](https://github.com/jshafer817/vJoy), [\[3\]](https://github.com/njz3/vJoy/). It seems that fork 3 is the most recent, [last build](https://github.com/njz3/vJoy/releases/tag/v2.2.1.1) requires at least 32-bit Windows 7.)  

##### Installation procedure

In command line: `pip install pywin32 playsound`

Install appropriate virtual joystick driver  

Create 5 joysticks (8 axes and 16 buttons each)

Use [dinput8blocker](https://github.com/fedorov-ao/dinput8blocker) wrapper DLL to enable and disable mouse input for the game using DirectInput API.

#### Running

`m2j_win.py` or `m2j_win.py -h` - for get help about command-line switches  
`m2j_win.py -c configname.cfg` - to use configuration specified in `configname.cfg` I.e. `m2j_win.py -c m2j_1mouse_win.cfg` runs 1-mouse configuration.    

### Command-line switches

```
-h | --help : help message
-d fileName | --devices=fileName : print input devices info to file fileName (- for stdout)
-j fileName | --devices_json=fileName : print input devices JSON config to file fileName (- for stdout)
-i | --log_input : log input from input devices to console (Ctrl-C to exit)
-p presetName | --preset=presetName : use preset presetName
-c configFileName | --config=configFileName : use config file configFileName
-v log_level | --log_level=logLevel : set log level to logLevel
```
