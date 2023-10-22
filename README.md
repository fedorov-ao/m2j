# m2j

Cross-platform mouse-to-joystick emulator written in python (2.7). Consists of platform-independent code (`m2j.py`), platform-dependent code (`m2j_linux.py` for Linux and `m2j_win.py` for Windows) and config files.

## Linux

### Installing

#### Dependencies 

`playsound` module - for playing sounds  
`evdev` module - for reading and emulating input  

#### Installation procedure

(# means running command in shell as root, $ - as regular user)

Install playsound module  
`$pip install playsound`

Install evdev module  
`$pip install evdev`

Note: evdev-1.6.0 for python 2.7 is bugged and will not run. Copy device.py and uinput.py files from `3rdparty/evdev` in repo dir to `evdev` installation dir.  
`$cp /path/to/repo/3rdparty/evdev/{device,uinput}.py ~/.local/lib/python2.7/site-packages/evdev/`

Installing evdev-1.6.1 for python 2.7  
`$pip install pathlib2`  
`$pip download evdev`  
`$tar -xf evdev-1.6.1.tar.gz`  
`$cd evdev-1.6.1`  
`$patch -p1 < path/to/evdev-1.6.1-py27.patch`  
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

### Running

`$./m2j_linux.py -h` for help  
`$./m2j_linux.py -c configname.cfg`

## Windows 

### Installing

#### Dependencies

`playsound` module - for playing sounds  
`pywin32` module - for reading and emulating input ([Github repo](https://github.com/mhammond/pywin32); last build supporting python 2.7 is [228](https://github.com/mhammond/pywin32/releases/tag/b228))  
virtual joystick driver - for creating virtual joysticks that will be controlled by the emulator  
`ppjoy` (up to win xp; [Github repo](https://github.com/elitak/PPJoy/releases)) or `vJoy` ([Github repo](https://sourceforge.net/projects/vjoystick/); forks: [\[1\]](https://github.com/shauleiz/vJoy), [\[2\]](https://github.com/jshafer817/vJoy), [\[3\]](https://github.com/njz3/vJoy/) (which seems to be the most recent, [last build](https://github.com/njz3/vJoy/releases/tag/v2.2.1.1) (min win7 32bit)))  

#### Installation procedure

In command line: `pip install pywin32 playsound`

Install appropriate virtual joystick driver  

Create 5 joysticks (8 axes and 16 buttons each)

Use [dinput8blocker](https://github.com/fedorov-ao/dinput8blocker) wrapper DLL to enable and disable mouse input for the game using DirectInput API.

### Running

`$./m2j_win.py -h` for help  
`$./m2j_win.py -c configname.cfg` 
