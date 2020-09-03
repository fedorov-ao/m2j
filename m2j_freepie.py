import sys
sys.path.append(".")

import time
import ctypes
from ctypes import wintypes, windll

import m2j
from m2j import *

g_w2nKeyMapping = {
	codes.KEY_SCROLLLOCK : Key.ScrollLock,
	codes.BTN_LEFT : 0,
	codes.BTN_RIGHT : 1,
	codes.BTN_MIDDLE : 2,
	codes.BTN_SIDE : 3,
	codes.BTN_EXTRA : 4,
 }

def w2n_key(k):
	"""Wrapper-to-native key conversion"""
	return g_w2nKeyMapping.get(k, None)
	
g_w2nAxisMapping = {
	codes.ABS_X : AxisTypes.X, 
	codes.ABS_Y : AxisTypes.Y, 
	codes.ABS_Z : AxisTypes.ZAxis, 
	codes.ABS_RX : AxisTypes.ZRotation, 
	codes.ABS_RY : AxisTypes.Slider, 
	codes.ABS_RZ : AxisTypes.XRotation, 
	codes.ABS_THROTTLE : AxisTypes.YRotation, 
	codes.ABS_RUDDER : AxisTypes.Dial
} 

def w2n_axis(a):
	"""Wrapper-to-native key conversion"""
	return g_w2nAxisMapping.get(a, None)

class PollingKeyDevice:
	def read_one(self):
		if (len(self.events_) == 0):
			return None
		else:
			return self.events_.pop()
	
	def update(self):
		value = None
		for i in xrange(len(self.keys_)):
			wKey = self.keys_[i]
			s, prev = self.get_key_value_(wKey), self.states_[i]
			if s != prev:
				if s and not prev:
					#pressed
					value = 1
				elif not s and prev:
					#released
					value = 0
				self.states_[i] = s
				
				self.append_event_(codes.EV_KEY, wKey, value)
				
	def append_event_(self, type, code, value):
		self.events_.append(InputEvent(type, code, value, time.time(), self.id_))     
		
	def __init__(self, id, keys, get_key_value):
		self.id_ = id
		self.keys_ = keys
		self.get_key_value_ = get_key_value
		
		self.events_ = []
		self.states_ = [0 for i in xrange(len(self.keys_))]
		
		
class PollingAxisDevice:
	def read_one(self):
		if (len(self.events_) == 0):
			return None
		else:
			return self.events_.pop()
	
	def update(self):
		value = None
		for i in xrange(len(self.axes_)):
			ad = self.axes_[i]
			value = self.get_axis_value_(ad[1])
			if value != 0.0:
				self.append_event_(ad[0], ad[1], value)
				
	def append_event_(self, type, code, value):
		self.events_.append(InputEvent(type, code, value, time.time(), self.id_))     
		
	def __init__(self, id, axes, get_axis_value):
		self.id_ = id
		self.axes_ = axes
		self.get_axis_value_ = get_axis_value
		
		self.events_ = []

def mouseAxisReporter(wAxis):
	v = 0.0
	if wAxis == codes.REL_X: v = mouse.deltaX
	elif wAxis == codes.REL_Y: v = mouse.deltaY
	elif wAxis == codes.REL_WHEEL: v = mouse.wheel
	return v
	
class CompositePollingDevice:
	def read_one(self):
		event = None
		while self.i_ != len(self.children_):
			event = self.children_[self.i_].read_one()
			if event is None:
				self.i_ += 1
			else:
				break
		return event
		
	def update(self):
		for c in self.children_:
			c.update()
		self.i_ = 0
		
	def add(self, child):
		self.children_.append(child)
		self.i_ = 0
		
	def __init__(self):
		self.children_ = []
		self.i_ = 0
		
		
class MouseBlocker:   
	user32 = ctypes.windll.user32
	kernel32 = ctypes.windll.kernel32
	wintypes = ctypes.wintypes

	WH_MOUSE_LL=14

	def swallow(self, s):
		if s != self.s_:
			if s == True:
				assert(self.hookId_ is None)
				self.hookId_ = user32.SetWindowsHookExA(WH_MOUSE_LL, self.hook_, kernel32.GetModuleHandleA(None), 0)
				if not self.hookId_:
					raise OSError("Failed to install mouse hook")
			else:
				assert(self.hookId_ is not None)
				b = user32.UnhookWindowsHookEx(self.hookId_)
				if not b:
					raise OSError("Failed to remove mouse hook")
				self.hookId_ = None
		self.s_ = s

	def hook(nCode, wParam, lParam):
		#return 1
		return user32.CallNextHookEx(None, nCode, wParam, lParam)   

	def __init__(self):
		self.s_ = False
		self.hookId_ = None
		CMPFUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
		self.hook_ = CMPFUNC(self.hook)


class CursorBlocker:   
  """Blocks mouse cursor movement by confining it in 1x1 rectangle"""
	user32 = ctypes.windll.user32
	kernel32 = ctypes.windll.kernel32
	wintypes = ctypes.wintypes

	def swallow(self, s):
    if s != self.s_:
      self.s_ = s
      if s == True:
        if not user32.GetClipCursor(ctypes.byref(self.r_)):
          raise Exception("Failed to retrieve current cursor clip rectangle")
        p = wintypes.POINT
        if not user32.GetCursorPos(ctypes.byref(p)):
          raise Exception("Failed to get current cursor position")
        r = wintypes.RECT(p.x, p.y, p.x+1, p.y+1)
        if not user32.ClipCursor(ctypes.byref(r)):
          raise Exception("Failed to set current cursor clip rectangle")
      else:
        if not user32.ClipCursor(ctypes.byref(self.r_)):
          raise Exception("Failed to restore current cursor clip rectangle")

	def __init__(self):
    self.s_, self.r_ = False, wintypes.RECT()


class FreePIEMouse2:
	def read_one(self):
		return self.be_.read_one()

	def update(self):
		self.be_.update()

	def swallow(self, s):
		self.blocker_.swallow(s)

	def __init__(self, axisDevice, keyDevice, blocker):
		self.be_ = CompositePollingDevice()
		self.be_.add(axisDevice)
		self.be_.add(keyDevice)
		self.blocker_ = blocker


class FreePIEMouse:
	def read_one(self):
		if (len(self.events_) == 0):
			return None
		else:
			return self.events_.pop()

	def swallow(self, s):
		pass  

	def update(self):
		dx, dy, dw = mouse.deltaX, mouse.deltaY, mouse.wheel
		diagnostics.watch(dw)
		if dx !=0:
			self.append_event_(codes.EV_REL, codes.REL_X, dx)
		if dy !=0:
			self.append_event_(codes.EV_REL, codes.REL_Y, dy)
		if dw != 0:
			self.append_event_(codes.EV_REL, codes.REL_WHEEL, dw)   
			
	def append_event_(self, type, code, value):
		self.events_.append(InputEvent(type, code, value, time.time(), self.source_))

	def __init__(self, source):
		self.source_ = source
		self.events_ = []

class PPJoystick:
	def move_axis(self, axis, v, relative = True):
		if relative:
			v += self.v_[axis]
		v = clamp(v, -1.0, 1.0)
		self.v_[axis] = v
		
		self.ppj_.setAxis(w2n_axis(axis), v*self.scales_[axis])
		
	def __init__(self, id, scales):
		self.ppj_ = ppJoy[id]
		self.scales_ = scales
		self.v_ = dict()
		for a in self.scales_.keys():
			self.v_[a] = 0.0  
		
		
def init_sinks(settings):
	resetTime = 0.5
	alpha = 0.5
	beta = 0.5
	stepData = [(0, 0.0), (100, 0.001), (1000, 0.005), (3000, 0.01), (5000, 0.01)]
	#sigmoidStepData = [(0, 0.0012363115783173878), (100, 0.0018421199497179954), (200, 0.0027431494497252027), (300, 0.004081285576579949), (400, 0.006064217492137119), (500, 0.008993104981045781), (600, 0.013298496788432927), (700, 0.01958286139838219), (800, 0.028662087949434385), (900, 0.0415863482469612), (1000, 0.05960146101105877), (1100, 0.08399080743303779), (1200, 0.11573760825049116), (1300, 0.1550127594361938), (1400, 0.20065616994377408), (1500, 0.25), (1600, 0.29934383005622606), (1700, 0.3449872405638062), (1800, 0.3842623917495089), (1900, 0.4160091925669623), (2000, 0.44039853898894127), (2100, 0.45841365175303883), (2200, 0.47133791205056563), (2300, 0.48041713860161783), (2400, 0.4867015032115671), (2500, 0.4910068950189542), (2600, 0.4939357825078629), (2700, 0.49591871442342006), (2800, 0.4972568505502748), (2900, 0.498157880050282), (3000, 0.4987636884216826)]
	#sigmoidStepData = [(0, 0.0006181557891586939), (100, 0.0009210599748589977), (200, 0.0013715747248626013), (300, 0.0020406427882899746), (400, 0.0030321087460685593), (500, 0.0044965524905228905), (600, 0.006649248394216463), (700, 0.009791430699191094), (800, 0.014331043974717192), (900, 0.0207931741234806), (1000, 0.029800730505529387), (1100, 0.04199540371651889), (1200, 0.05786880412524558), (1300, 0.0775063797180969), (1400, 0.10032808497188704), (1500, 0.125), (1600, 0.14967191502811303), (1700, 0.1724936202819031), (1800, 0.19213119587475444), (1900, 0.20800459628348114), (2000, 0.22019926949447063), (2100, 0.22920682587651942), (2200, 0.23566895602528282), (2300, 0.24020856930080892), (2400, 0.24335075160578354), (2500, 0.2455034475094771), (2600, 0.24696789125393145), (2700, 0.24795935721171003), (2800, 0.2486284252751374), (2900, 0.249078940025141), (3000, 0.2493818442108413)]
	sigmoidStepData = [(0, 0.00024726231566347755), (100, 0.0003684239899435991), (200, 0.0005486298899450405), (300, 0.0008162571153159899), (400, 0.0012128434984274238), (500, 0.0017986209962091563), (600, 0.0026596993576865854), (700, 0.0039165722796764375), (800, 0.005732417589886877), (900, 0.00831726964939224), (1000, 0.011920292202211755), (1100, 0.01679816148660756), (1200, 0.023147521650098233), (1300, 0.03100255188723876), (1400, 0.040131233988754816), (1500, 0.05), (1600, 0.05986876601124522), (1700, 0.06899744811276125), (1800, 0.07685247834990178), (1900, 0.08320183851339247), (2000, 0.08807970779778826), (2100, 0.09168273035060777), (2200, 0.09426758241011313), (2300, 0.09608342772032358), (2400, 0.09734030064231342), (2500, 0.09820137900379085), (2600, 0.09878715650157259), (2700, 0.09918374288468401), (2800, 0.09945137011005496), (2900, 0.0996315760100564), (3000, 0.09975273768433653)]
	stepX = SpeedBasedConverter(SigmoidApproximator(12.0/3000, -6.0, 0.01), EmaFilter(alpha), resetTime)
	stepY = SpeedBasedConverter(SegmentApproximator(stepData), EmaFilter(alpha), resetTime)
	stepDataZ = [(0, 0.0), (10, 0.001), (20, 0.005), (50, 0.01), (100, 0.1), (200, 0.1)]
	#stepZ = SpeedBasedConverter(SigmoidApproximator(12.0/100, -6.0, 0.05), EmaFilter(alpha), resetTime)
	stepZ = ProportionalConverter(0.001)

	joystick = settings["joystick"]
	head = settings["head"]
	mouse = settings["mouse"]

	clickTime = 0.5
	clickSink = ClickSink(clickTime)

	modifierSink = ModifierSink()
	clickSink.set_next(modifierSink)

	mainSink = BindingSink(cmp=CmpWithModifiers())
	modifierSink.set_next(mainSink)

	stateSink = StateSink()

	mainSink.add_several((ED.multiclick(codes.KEY_SCROLLLOCK, 2), ), (DeviceGrabberSink(mouse), ToggleSink(stateSink)), 0)
	mainSink.add((), stateSink, 1)

	topSink = BindingSink(cmp=CmpWithModifiers())
	stateSink.set_next(topSink)
	topModeSink = ModeSink()
	topSink.add(ED.press(codes.BTN_RIGHT), SetMode(topModeSink, 1), 0)
	topSink.add(ED.release(codes.BTN_RIGHT), SetMode(topModeSink, 0), 0)
	topSink.add((), topModeSink)

	joystickSink = BindingSink(cmp=CmpWithModifiers())
	topModeSink.add(0, joystickSink)
	topModeSink.set_mode(0)

	joystickSink.add(ED.click(codes.BTN_MIDDLE), SetAxisSink(joystick, codes.ABS_Z, 0))
	joystickSink.add_several([ED.multiclick(codes.BTN_MIDDLE, 2)], [SetAxisSink(joystick, codes.ABS_X, 0), SetAxisSink(joystick, codes.ABS_Y, 0)])

	modeSink = ModeSink()
	joystickSink.add_several((ED.move(codes.REL_X), ED.bcast()), (MoveAxisSink(joystick, codes.ABS_X, stepX, True),), 0)
	#joystickSink.add_several((ED.move(codes.REL_X), ED.bcast()), (MoveAxisSink(joystick, codes.ABS_X, ProportionalConverter(0.001), True),), 0)
	joystickSink.add_several((ED.move(codes.REL_Y), ED.bcast()), (MoveAxisSink(joystick, codes.ABS_Y, stepY, True),), 0)
	joystickSink.add(ED.press(codes.BTN_EXTRA), SetMode(modeSink, 1), 0)
	joystickSink.add(ED.press(codes.BTN_SIDE), SetMode(modeSink, 2), 0)
	joystickSink.add_several((ED.release(codes.BTN_SIDE), ED.release(codes.BTN_EXTRA),), (SetMode(modeSink, 0),), 0)
	joystickSink.add([], modeSink, 1)

	mode0Sink = BindingSink(cmp=CmpWithModifiers())
	modeSink.add(0, mode0Sink)
	mode0Sink.add_several((ED.move(codes.REL_WHEEL), ED.bcast()), (MoveAxisSink(joystick, codes.ABS_Z, stepZ, True),), 0)

	mode1Sink = BindingSink(cmp=CmpWithModifiers())
	modeSink.add(1, mode1Sink)
	mode1Sink.add_several((ED.move(codes.REL_WHEEL), ED.bcast()), (MoveAxisSink(joystick, codes.ABS_RX, stepZ, True),), 0)
	fullForward = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, 1.0), (codes.ABS_RX, 0), (codes.ABS_RY, 0), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, 1.0),)
	mode1Sink.add(ED.click(codes.BTN_LEFT), SetAxesSink(head, fullForward))

	mode2Sink = BindingSink(cmp=CmpWithModifiers())
	modeSink.add(2, mode2Sink)
	mode2Sink.add_several((ED.move(codes.REL_WHEEL), ED.bcast()), (MoveAxisSink(joystick, codes.ABS_RY, stepZ, True),), 0)
	fullBackward = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, -1.0), (codes.ABS_RX, -0.15), (codes.ABS_RY, 0), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, -1.0),)
	mode2Sink.add(ED.click(codes.BTN_LEFT), SetAxesSink(head, fullBackward))

	modeSink.set_mode(0)

	headSink = BindingSink(cmp=CmpWithModifiers())
	topModeSink.add(1, headSink)

	headModeSink = ModeSink()
	headSink.add(ED.press(codes.BTN_EXTRA), SetMode(headModeSink, 1), 0)
	headSink.add(ED.release(codes.BTN_EXTRA), SetMode(headModeSink, 0), 0)
	headSink.add((), headModeSink, 1)

	headMode0Sink = BindingSink(cmp=CmpWithModifiers())
	headModeSink.add(0, headMode0Sink)
	headMode0Sink.add_several((ED.move(codes.REL_X), ED.bcast()), (MoveAxisSink(head, codes.ABS_RY, stepX, True),), 0) 
	headMode0Sink.add_several((ED.move(codes.REL_Y), ED.bcast()), (MoveAxisSink(head, codes.ABS_RX, stepY, True),), 0) 
	headMode0Sink.add_several((ED.move(codes.REL_WHEEL), ED.bcast()), (MoveAxisSink(head, codes.ABS_THROTTLE, stepZ, True),), 0) 
	headMode0Sink.add(ED.click(codes.BTN_MIDDLE), SetAxisSink(head, codes.ABS_THROTTLE, -1.0), 0) 
	headMode0Sink.add(ED.multiclick(codes.BTN_MIDDLE, 2), SetAxesSink(head, ((codes.ABS_RX, 0.0), (codes.ABS_RY, 0.0))), 0) 

	headMode1Sink = BindingSink(cmp=CmpWithModifiers())
	headModeSink.add(1, headMode1Sink)
	headMode1Sink.add_several((ED.move(codes.REL_X), ED.bcast()), (MoveAxisSink(head, codes.ABS_X, stepX, True),), 0) 
	headMode1Sink.add_several((ED.move(codes.REL_Y), ED.bcast()), (MoveAxisSink(head, codes.ABS_Y, stepY, True),), 0) 
	headMode1Sink.add_several((ED.move(codes.REL_WHEEL), ED.bcast()), (MoveAxisSink(head, codes.ABS_Z, stepZ, True),), 0) 
	headMode1Sink.add(ED.multiclick(codes.BTN_MIDDLE, 2), SetAxesSink(head, ((codes.ABS_X, 0.0), (codes.ABS_Y, 0.0), (codes.ABS_Z, 0.0))), 0)

	headModeSink.set_mode(0)

	return clickSink
		
	
if starting:
	reload(m2j)
	global g_es
	global g_devices
	mouseAxisDevice = PollingAxisDevice(0, ((codes.EV_REL, codes.REL_X), (codes.EV_REL, codes.REL_Y), (codes.EV_REL, codes.REL_WHEEL),), mouseAxisReporter)
	mouseKeyDevice = PollingKeyDevice(0, (codes.BTN_LEFT, codes.BTN_RIGHT, codes.BTN_MIDDLE, codes.BTN_SIDE, codes.BTN_EXTRA), lambda wKey : mouse.getButton(w2n_key(wKey)))
	g_devices = (
		#FreePIEMouse(0),
		FreePIEMouse2(mouseAxisDevice, mouseKeyDevice, CursorBlocker()),
		PollingKeyDevice(1, (codes.KEY_SCROLLLOCK,), lambda wKey : keyboard.getPressed(w2n_key(wKey))),
	)
	joystick = PPJoystick(0, {codes.ABS_X : 999.0, codes.ABS_Y : 999.0, codes.ABS_Z : 999.0, codes.ABS_RX : 5, codes.ABS_RY : 10.0, codes.ABS_RZ : 999.0, codes.ABS_RUDDER : 999.0, codes.ABS_THROTTLE : 999.0,})
	head = Opentrack("127.0.0.1", 5555)
  settings = {"mouse": g_devices[0], "joystick": joystick, "head": head}
  sink = init_sinks(settings)
	g_es = EventSource(g_devices, sink, 0.01)
	assert(g_es)
	
for d in g_devices:
	d.update()
	
g_es.run_once()
