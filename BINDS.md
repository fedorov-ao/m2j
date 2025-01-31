# Bindings

## 2mice2

Config file: `m2j_2mice2.cfg`, preset in `curves.cfg`: `2mice2`

Configuration that maps 2 mice (and keyboard) to 4 virtual joysticks.  
Mice should have 6 buttons (clickable mouse wheel is counted as a button). Mouse axes are `X`, `Y`, `WHEEL`; buttons are `LMB` (left), `RMB` (right), `MMB` (middle, clickable wheel), `EXTRA` (side button closer to cord), `SIDE` (side button farther from cord).  
Keyboard is a standard keyboard.  
Virtual joysticks should have 8 axes and 16 buttons. Joystick axes are `X`, `Y`, `Z`, `RX`, `RY`, `RZ`, `RUDDER`, `THROTTLE`; buttons are designated by numbers from `0` to `15`.  

Mouse operated by right hand is referred here and in config as `rmouse`, by left hand - as `lmouse`. For example, `rmouse.X` is the X axis of rmouse.  
`rmouse` and `lmouse` each operate primarilly in independent modes, though there are modes that use both mice.  
`rmouse` modes are `pri`, `sec`, `ter`, `qua`, `hat`, `aux3`, `aux4`.  
`lmouse` modes are `yaw`, `fwd`, `fwd2`, `fwd3`, `fwd4`, `head_rotation`, `head_movement`, `aux1`, `aux2`.
See **Mode-specific bindings** section to find out which axes and buttons of which virtual joystick are controlled in a given mode.  

Virtual joysticks are also referred by names. For example, `joystick1.X` is X axis of joystick `joystick1`.  
`joystick1` - handles basic functions, `joystick2`, `joystick3` - auxillary funcions, `head` - head (POV) rotation and movement.  

### Global bindigs

 * press `keyboard.SCROLLOCK` - toggle emulation, grab/ungrab `rmouse` and `lmouse`  
 * doubleclick `rmouse.SIDE`, then press `rmouse.EXTRA` - partially disable emulation: ungrab `lmouse` and don't process input from it  
   * press `rmouse.EXTRA` in this partially disabled mode - enable emulation: grab `lmouse` back and resume processing input from it  
 * doubleclick `rmouse.EXTRA`, then press `rmouse.SIDE` - partially disable emulation (version 2): ungrab `lmouse`, but still process its' wheel movement  
   * press `rmouse.SIDE` in this partially disabled mode - enable emulation: grab `lmouse` back and resume processing input from it  
 * tripleclick `keyboard.KEY_MENU` - open/close info window  
 * press `keyboard.KEY_MENU` - enter console menu mode  
   * click `keyboard.KEY_MENU` - leave console menu mode  

### Mode-specific bindigs

This section describes which axes/buttons of which virtual joystick are controlled in a given mode, along with some comments (like possible bindings for IL-2 1946 or LockOn).

**rmouse**

**pri,sec,ter,qua,hat**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|rmouse.X||move|joystick.X|roll|roll||
|move|rmouse.Y||move|joystick.Y|pitch|pitch||

**pri**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||press/release|joystick.0|weapon 1 (mguns)|fire||
|press/release|rmouse.RMB||press/release|joystick.1|weapon 2 (guns)|lock target||
|click|rmouse.MMB||center|joystick.Z||||
|hold|rmouse.MMB||center|joystick.X, joystick.Y, joystick.Z||||
|move|rmouse.WHEEL|keyboard.RSHIFT|move|joystick2.X|right engines throttle|||
|move|rmouse.WHEEL|keyboard.RCTRL|move|joystick2.Y|right engines propellers pitch|||
|move|rmouse.WHEEL|keyboard.RALT|move|joystick2.Z|right engines mix|||
|move|rmouse.WHEEL|keyboard.LSHIFT|move|joystick2.RX|left engines throttle|||
|move|rmouse.WHEEL|keyboard.LCTRL|move|joystick2.RY|left engines propellers pitch|||
|move|rmouse.WHEEL|keyboard.LALT|move|joystick2.RZ|left engines mix|||
|press/release|rmouse.SIDE||switch to/from|sec||||
|press/release|rmouse.EXTRA||switch to/from|ter||||
|press|rmouse.SIDE|lmouse.SIDE|switch to|reng|||actually switching from qua mode|
|release|rmouse.SIDE||switch from|reng||||
|press|rmouse.EXTRA|lmouse.SIDE|switch to|leng|||actually switching from qua mode|
|release|lmouse.SIDE||switch from|qua||||
|press/release|rmouse.SIDE|rmouse.EXTRA|switch to/from|pent|||switching to pent mode requires pressing both rmouse.SIDE and rmouse.EXTRA|
|press/release|rmouse.EXTRA|rmouse.SIDE|switch to/from|pent|||switching to pent mode requires pressing both rmouse.SIDE and rmouse.EXTRA|
|press/release|lmouse.EXTRA||switch to/from|hat||||
|press/release|lmouse.EXTRA|rmouse.SIDE|switch to/from|aux3||||
|press/release|lmouse.EXTRA|rmouse.EXTRA|switch to/from|aux4||||

**sec**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||press/release|joystick.2|weapon 3 (rockets)|release weapon||
|press/release|rmouse.RMB||press/release|joystick.3|weapon 4 (bombs)|change weapon||
|press/release|rmouse.MMB||press/release|joystick.4||toggle cannon||
|move|rmouse.WHEEL||move|joystick.RX|propeller pitch|||

**ter**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|click|rmouse.LMB||click|joystick.8|toggle boost|toggle laser rangefinder||
|hold/release|rmouse.LMB||press/release|joystick.11||toggle optical||
|click|rmouse.RMB||click|joystick.9|supercharger 2|change radar mode (?)||
|hold/release|rmouse.RMB||press/release|joystick.12|supercharger 1|toggle radar||
|click|rmouse.MMB||click|joystick.10|extend/retract airbrake|extend airbrake||
|hold/release|rmouse.MMB||press/release|joystick.13||retract airbrake||
|move|rmouse.WHEEL||move|joystick.RZ|flaps|||

**qua**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||press/release|joystick.5|level stabisizer|chaff||
|press/release|rmouse.RMB||press/release|joystick.6|bomb bay doors|flare||
|press/release|rmouse.MMB||press/release|joystick.7||||
|move|rmouse.WHEEL||move|joystick.RY|radiator|||

**pent**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||press/release|joystick.14|extend/retract gears|||
|press/release|rmouse.RMB||press/release|joystick.15|lock/unlock tail wheel|||
|move|rmouse.WHEEL||move|joystick.Z|rudder|||

**reng**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|rmouse.WHEEL||move|joystick2.X|right engines throttle|||
|move|rmouse.WHEEL|rmouse.SIDE|move|joystick2.Y|right engines propellers pitch|||
|move|rmouse.WHEEL|rmouse.EXTRA|move|joystick2.Z|right engines mix|||

**leng**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|rmouse.WHEEL||move|joystick2.RX|left engines throttle|||
|move|rmouse.WHEEL|rmouse.SIDE|move|joystick2.RY|left engines propellers pitch|||
|move|rmouse.WHEEL|rmouse.EXTRA|move|joystick2.RZ|left engines mix|||

**hat**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||move left|head.X|||depends on the current hat mode|
|press/release|rmouse.RMB||move right|head.X|||depends on the current hat mode|
|press/release|rmouse.EXTRA||move up|head.Y|||depends on the current hat mode|
|press/release|rmouse.SIDE||move down (?)|head.Y|||depends on the current hat mode|

**aux3**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||press/release|joystick3.0||||
|press/release|rmouse.RMB||press/release|joystick3.1||||
|press/release|rmouse.EXTRA||press/release|joystick3.2||||
|press/release|rmouse.SIDE||press/release|joystick3.3||||
|move up|rmouse.WHEEL||click or hold|joystick3.4||||
|move down|rmouse.WHEEL||click or hold|joystick3.5||||
|click|rmouse.MIDDLE||click|joystick3.6||||
|hold/release|rmouse.MIDDLE||press/release|joystick3.7||||
|hold/release|rmouse.MIDDLE||press/release|joystick3.15||||

**aux4**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.LMB||press/release|joystick3.8||||
|press/release|rmouse.RMB||press/release|joystick3.9||||
|press/release|rmouse.EXTRA||press/release|joystick3.10||||
|press/release|rmouse.SIDE||press/release|joystick3.11||||
|move up|rmouse.WHEEL||click or hold|joystick3.12||||
|move down|rmouse.WHEEL||click or hold|joystick3.13||||
|click|rmouse.MIDDLE||click|joystick3.14||||

**lmouse**

**yaw**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|click|rmouse.LMB|rmouse.SIDE|set view to|fb|||look straight forward and zoom full out|
|hold|rmouse.LMB|rmouse.SIDE|set view to|ff|||look straight forward and zoom full in|
|click|rmouse.LMB|rmouse.EXTRA|set view to|pos_fb|||head pos full backward|
|hold|rmouse.LMB|rmouse.EXTRA|set view to|pos_ff|||head pos full forward|
|press/release|rmouse.RMB|rmouse.SIDE|set view to/return view back|pose2 (?)||||
|press/release|rmouse.RMB|rmouse.EXTRA|set view to/return view back|pose3 (?)||||
|press/release|rmouse.MMB||press/release|head.0|look through sight|||
|move|lmouse.X||move|joystick.Z|yaw|yaw||
|move|lmouse.Y||move|joystick.RUDDER|brakes|||
|move|lmouse.WHEEL||move|head.THROTTLE|zoom|zoom||
|press/release|lmouse.RMB||switch to/from|fwd||||
|press/release|lmouse.RMB|rmouse.EXTRA|switch to/from|fwd2||||
|press/release|lmouse.RMB|rmouse.SIDE|switch to/from|fwd3||||
|press/release|lmouse.RMB|rmouse.SIDE, rmouse.EXTRA|switch to/from|fwd4||||
|press/release|lmouse.SIDE|rmouse.SIDE|switch to/from|aux1||||
|press/release|lmouse.SIDE|rmouse.EXTRA|switch to/from|aux2||||

__var `2mice2.switcher` == yaw__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press|lmouse.LMB||switch to|head_rotation|||save prev view if var `2mice2.prevPoseMode` == on_release|
|click and press|lmouse.LMB||switch to|head_rotation|||save prev view if var `2mice2.prevPoseMode` == on_hold|

__var `2mice2.switcher` == head_rotation__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|release|lmouse.LMB||switch to|head_rotation||||
|press/release|lmouse.LEFT|rmouse.SIDE|switch to/from|head_movement||||

__var `2mice2.switcher` == toggle__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|click|lmouse.LMB||switch to|head_rotation||||
|click|lmouse.RMB|lmouse.LMB|switch to|head_movement||||

**fwd**

When entering `fwd` mode the `head` joystick is set to `fwd` pose (look forward and down, zoom full out).

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|lmouse.X||move|joystick.Z|yaw|yaw||
|move|lmouse.Y||move|joystick.RUDDER|brakes|||
|press|lmouse.LMB||update pose|saved pose||||
|release|rmouse.RMB||switch to|yaw|||return view to previous state, lmouse.X controls joystick.Z|
|release|rmouse.RMB|rmouse.SIDE|switch to|yaw|||look straight forward and zoom full out|
|release|rmouse.RMB|rmouse.EXTRA|switch to|yaw|||look straight forward and zoom full in|

**fwd2**, **fwd3**, **fwd4**

When entering `fwd2`, `fwd3`, `fwd4` mode the `head` joystick is set respectively to `pose2`, `pose3`, `pose4` pose

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|lmouse.X||move|joystick.Z|yaw|yaw||
|move|lmouse.Y||move|joystick.RUDDER|brakes|||
|press|lmouse.LMB||update pose|saved pose||||
|release|rmouse.RMB||switch to|yaw|||return view to previous state, lmouse.X controls joystick.Z|

**head_rotation**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|lmouse.X||move|head.RX|horizontal view rotation (via TrackIR emulator)|horizontal view rotation||
|move|lmouse.Y||move|head.RY|vertical view rotation (via TrackIR emulator)|vertical view rotation||
|move|lmouse.X|lmouse.SIDE, rmouse.EXTRA, rmouse.SIDE|move|head.RZ|roll view rotation (via TrackIR emulator)|roll view rotation||
|move|lmouse.WHEEL||move|head.THROTTLE|zoom|zoom||

__var `2mice2.switcher` == yaw__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press/release|rmouse.SIDE||switch to/from|head_movement||||
|release|lmouse.LMB||switch to|yaw|||restore prev view if var `2mice2.prevPoseMode` == on_hold|
|release|lmouse.LMB|rmouse.EXTRA|switch to|yaw|||restore prev view if var `2mice2.prevPoseMode` == on_release|

__var `2mice2.switcher` == head_rotation__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|press|lmouse.LMB||switch to|yaw||||

__var `2mice2.switcher` == toggle__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|click|lmouse.LMB||switch to|yaw||||
|click|lmouse.RMB|lmouse.LMB|switch to|head_movement||||

**head_movement**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|lmouse.X||move|head.X|horizontal view position (via TrackIR emulator)|||
|move|lmouse.Y||move|head.Y|vertical view position (via TrackIR emulator)|||
|move|lmouse.WHEEL||move|head.Z|lateral view position (via TrackIR emulator)|||

__var `2mice2.switcher` == toggle__

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|click|lmouse.RMB|lmouse.LMB|switch to|previous mode (yaw or head_rotation)||||

**aux1**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|lmouse.X||move|joystick3.X|yaw trim|||
|move|lmouse.Y||move|joystick3.Y|elevator trim|||
|move|lmouse.WHEEL||move|joystick3.Z|roll trim|||
|click|lmouse.MMB||center|joystick3.Z||||
|hold|lmouse.MMB||center|joystick3.X, joystick3.Y, joystick3.Z||||

**aux2**

|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|move|lmouse.X||move|joystick3.RX||||
|move|lmouse.Y||move|joystick3.RY||||
|move|lmouse.WHEEL||move|joystick3.RZ||||
|click|lmouse.MMB||center|joystick3.RZ||||
|hold|lmouse.MMB||center|joystick3.RX, joystick3.RY, joystick3.RZ||||
