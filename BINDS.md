# Bindings

## 2mice2

Config file: `m2j_2mice2.cfg`, preset in `curves.cfg`: `2mice2`

rmouse is right mouse, lmouse is left mouse.  
Joystick axes are X,Y,Z,RX,RY,RZ,RUDDER,THROTTLE; buttons are designated by numbers 0-16.  
Mouse axes are X,Y,WHEEL; buttons are LMB (left), RMB (right), MMB (middle), EXTRA, SIDE.  
For example, `joystick1.X` is `X` axis of joystick `joystick1`.  

rmouse and lmouse have independent modes.  
rmouse modes are _pri_, _sec_, _ter_, _qua_, _hat_, _aux3_, _aux4_.  
lmouse modes are _yaw_, _fwd_, _head_rotation_, _head_movement_, _aux1_, _aux2_.

|side|mode|action|input|modifiers|action|argument (output/mode/etc)|1946|LockOn|note|
|:--:|:--:|:---:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
|right|pri,sec,ter,qua,hat|move|rmouse.X||move|joystick.X|roll|roll||
|right|pri,sec,ter,qua,hat|move|rmouse.Y||move|joystick.Y|pitch|pitch||
|right|pri|press/release|rmouse.LMB||press/release|joystick.0|weapon 1 (mguns)|fire||
|right|pri|press/release|rmouse.RMB||press/release|joystick.1|weapon 2 (guns)|||
|right|pri|click|rmouse.MMB||center|joystick.Z||||
|right|pri|hold|rmouse.MMB||center|joystick.X, joystick.Y, joystick.Z||||
|right|pri|move|rmouse.WHEEL||move|joystick.THROTTLE|throttle|thrust||
|right|pri|move|rmouse.WHEEL|keyboard.RSHIFT|move|joystick.THROTTLE||||
|right|pri|move|rmouse.WHEEL|keyboard.RCTRL|move|joystick.RX||||
|right|pri|move|rmouse.WHEEL|keyboard.RALT|move|joystick.RZ||||
|right|pri|move|rmouse.WHEEL|keyboard.LSHIFT|move|joystick.RY||||
|right|pri|move|rmouse.WHEEL|keyboard.LCTRL|move|joystick.RUDDER||||
|right|pri|press/release|rmouse.SIDE||switch to/from|sec||||
|right|sec|press/release|rmouse.LMB||press/release|joystick.2|weapon 3 (rockets)|release weapon||
|right|sec|press/release|rmouse.RMB||press/release|joystick.3|weapon 4 (bombs)|lock target||
|right|sec|press/release|rmouse.MMB||press/release|joystick.4||toggle cannon||
|right|sec|move|rmouse.WHEEL||move|joystick.RX|propeller pitch|||
|right|sec|move|rmouse.WHEEL|keyboard.RSHIFT|move|joystick2.X|right engines throttle|||
|right|sec|move|rmouse.WHEEL|keyboard.RCTRL|move|joystick2.Y|right engines propellers pitch|||
|right|sec|move|rmouse.WHEEL|keyboard.RALT|move|joystick2.Z|right engines propellers pitch|||
|right|sec|move|rmouse.WHEEL|keyboard.LSHIFT|move|joystick2.RX|left engines throttle|||
|right|sec|move|rmouse.WHEEL|keyboard.LCTRL|move|joystick2.RY|left engines propellers pitch|||
|right|sec|move|rmouse.WHEEL|keyboard.LALT|move|joystick2.RZ|left engines propellers pitch|||
|right|pri|press/release|rmouse.EXTRA||switch to/from|ter||||
|right|ter|click|rmouse.LMB||click|joystick.8|toggle boost|toggle laser rangefinder||
|right|ter|hold/release|rmouse.LMB||press/release|joystick.11||toggle optical||
|right|ter|click|rmouse.RMB||click|joystick.9|supercharger 2|change radar mode (?)||
|right|ter|hold/release|rmouse.RMB||press/release|joystick.12|supercharger 1|toggle radar||
|right|ter|click|rmouse.MMB||click|joystick.10|extend/retract airbrake|extend airbrake||
|right|ter|hold/release|rmouse.MMB||press/release|joystick.13||retract airbrake||
|right|ter|press/release|rmouse.LMB|rmouse.SIDE|press/release|joystick.14|extend/retract gears|||
|right|ter|press/release|rmouse.RMB|rmouse.SIDE|press/release|joystick.15|lock/unlock tail wheel|||
|right|ter|move|rmouse.WHEEL||move|joystick.RZ|flaps|||
|right|pri|press/release|lmouse.SIDE||switch to/from|qua||||
|right|qua|press/release|rmouse.LMB||press/release|joystick.5|level stabisizer|chaff||
|right|qua|press/release|rmouse.RMB||press/release|joystick.6|bomb bay doors|flare||
|right|qua|press/release|rmouse.MMB||press/release|joystick.7||||
|right|qua|move|rmouse.WHEEL||move|joystick.RY|radiator|||
|right|pri|press/release|lmouse.EXTRA||switch to/from|hat||||
|right|hat|press/release|rmouse.LMB||move left|head.X|||depends on the current hat mode|
|right|hat|press/release|rmouse.RMB||move right|head.X|||depends on the current hat mode|
|right|hat|press/release|rmouse.EXTRA||move up|head.Y|||depends on the current hat mode|
|right|hat|press/release|rmouse.SIDE||move down (?)|head.Y|||depends on the current hat mode|
|left|yaw|click|rmouse.LMB|rmouse.SIDE|set view to|fb|||look straight forward and zoom full out|
|left|yaw|hold|rmouse.LMB|rmouse.SIDE|set view to|ff|||look straight forward and zoom full in|
|left|yaw|click|rmouse.LMB|rmouse.EXTRA|set view to|pos_fb|||head pos full backward|
|left|yaw|hold|rmouse.LMB|rmouse.EXTRA|set view to|pos_ff|||head pos full forward|
|left|yaw|press|rmouse.RMB||switch to|fwd|||look forward and down, zoom full out, lmouse.X controls joystick.Z|
|left|yaw|release|rmouse.RMB||switch to|yaw|||return view to previous state, lmouse.X controls joystick.Z|
|left|yaw|release|rmouse.RMB|rmouse.SIDE|switch to|yaw|||look straight forward and zoom full out|
|left|yaw|release|rmouse.RMB|rmouse.EXTRA|switch to|yaw|||look straight forward and zoom full in|
|left|yaw|press/release|rmouse.RMB|rmouse.SIDE|set view to/return view back|pose2 (?)||||
|left|yaw|press/release|rmouse.RMB|rmouse.EXTRA|set view to/return view back|pose3 (?)||||
|left|yaw|press/release|rmouse.MMB||press/release|head.0|look through sight|||
|left|yaw|move|lmouse.WHEEL||move|head.THROTTLE|zoom|zoom||
|left|yaw|press|lmouse.LMB||switch to|head_rotation|||save prev view if 2mice2.prevPoseMode == on_release|
|left|yaw|click and press|lmouse.LMB||switch to|head_rotation|||save prev view if 2mice2.prevPoseMode == on_hold|
|left|head_rotation|release|lmouse.LMB||switch to|yaw|||restore prev view if 2mice2.prevPoseMode == on_hold|
|left|head_rotation|release|lmouse.LMB|rmouse.EXTRA|switch to|yaw|||restore prev view if 2mice2.prevPoseMode == on_release|
|left|head_rotation|move|lmouse.X||move|head.RX|horizontal view rotation (via TrackIR emulator)|horizontal view rotation||
|left|head_rotation|move|lmouse.X|rmouse.EXTRA|move|head.RZ|roll view rotation (via TrackIR emulator)|roll view rotation||
|left|head_rotation|move|lmouse.Y||move|head.RY|vertical view rotation (via TrackIR emulator)|vertical view rotation||
|left|head_rotation|move|lmouse.WHEEL||move|head.THROTTLE|zoom|zoom||
|left|head_rotation|press/release|rmouse.SIDE||switch to/from|head_movement||||
|left|head_movement|move|lmouse.X||move|head.X|horizontal view position (via TrackIR emulator)|||
|left|head_movement|move|lmouse.Y||move|head.Y|vertical view position (via TrackIR emulator)|||
|left|head_movement|move|lmouse.WHEEL||move|head.Z|lateral view position (via TrackIR emulator)|||
|right|pri|press/release|lmouse.EXTRA|rmouse.SIDE|switch to/from|aux3||||
|right|aux3|press/release|rmouse.LMB||press/release|joystick3.0||||
|right|aux3|press/release|rmouse.RMB||press/release|joystick3.1||||
|right|aux3|press/release|rmouse.EXTRA||press/release|joystick3.2||||
|right|aux3|press/release|rmouse.SIDE||press/release|joystick3.3||||
|right|aux3|move up|rmouse.WHEEL||click or hold|joystick3.4||||
|right|aux3|move down|rmouse.WHEEL||click or hold|joystick3.5||||
|right|aux3|click|rmouse.MIDDLE||click|joystick3.6||||
|right|aux3|hold/release|rmouse.MIDDLE||press/release|joystick3.7||||
|right|pri|press/release|lmouse.EXTRA|rmouse.EXTRA|switch to/from|aux4||||
|right|aux4|press/release|rmouse.LMB||press/release|joystick3.8||||
|right|aux4|press/release|rmouse.RMB||press/release|joystick3.9||||
|right|aux4|press/release|rmouse.EXTRA||press/release|joystick3.10||||
|right|aux4|press/release|rmouse.SIDE||press/release|joystick3.11||||
|right|aux4|move up|rmouse.WHEEL||click or hold|joystick3.12||||
|right|aux4|move down|rmouse.WHEEL||click or hold|joystick3.13||||
|right|aux4|click|rmouse.MIDDLE||click|joystick3.14||||
|right|aux3|hold/release|rmouse.MIDDLE||press/release|joystick3.15||||
|left|yaw|press/release|lmouse.SIDE|rmouse.SIDE|switch to/from|aux1||||
|left|aux1|move|lmouse.X||move|joystick3.X|yaw trim|||
|left|aux1|move|lmouse.Y||move|joystick3.Y|elevator trim|||
|left|aux1|move|lmouse.WHEEL||move|joystick3.Z|roll trim|||
|left|aux1|click|lmouse.MMB||center|joystick3.Z||||
|left|aux1|hold|lmouse.MMB||center|joystick3.X, joystick3.Y, joystick3.Z||||
|left|yaw|press/release|lmouse.SIDE|rmouse.EXTRA|switch to/from|aux2||||
|left|aux2|move|lmouse.X||move|joystick3.RX||||
|left|aux2|move|lmouse.Y||move|joystick3.RY||||
|left|aux2|move|lmouse.WHEEL||move|joystick3.RZ||||
|left|aux2|click|lmouse.MMB||center|joystick3.RZ||||
|left|aux2|hold|lmouse.MMB||center|joystick3.RX, joystick3.RY, joystick3.RZ||||
