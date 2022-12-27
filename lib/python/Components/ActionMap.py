from enigma import eActionMap
from keyids import KEYIDS
from Components.config import config
from Tools.Directories import fileReadXML

MODULE_NAME = __name__.split(".")[-1]

keyBindings = {}


def addKeyBinding(filename, keyId, context, mapto, flags):
	keyBindings.setdefault((context, mapto), []).append((keyId, filename, flags))


def queryKeyBinding(context, mapto):  # Returns a list of (keyId, flags) for a specified mapto action in a context.
	if (context, mapto) in keyBindings:
		return [(x[0], x[2]) for x in keyBindings[(context, mapto)]]
	return []


def parseKeymap(filename, context, actionMapInstance, device, domKeys):
	unmapDict = {}
	error = False
	keyId = -1
	for key in domKeys.findall("key"):
		keyName = key.attrib.get("id")
		if keyName is None:
			print("[ActionMap] Error: Keymap attribute 'id' in context '%s' in file '%s' must be specified!" % (context, filename))
			error = True
		else:
			try:
				if len(keyName) == 1:
					keyId = ord(keyName) | 0x8000
				elif keyName[0] == "\\":
					if keyName[1].lower() == "x":
						keyId = int(keyName[2:], 16) | 0x8000
					elif keyName[1].lower() == "d":
						keyId = int(keyName[2:], 10) | 0x8000
					elif keyName[1].lower() == "o":
						keyId = int(keyName[2:], 8) | 0x8000
					elif keyName[1].lower() == "b":
						keyId = int(keyName[2:], 2) | 0x8000
					else:
						print("[ActionMap] Error: Keymap id '%s' in context '%s' in file '%s' is not a hex, decimal, octal or binary number!" % (keyName, context, filename))
						error = True
				else:
					keyId = KEYIDS.get(keyName, -1)
					if keyId is None:
						print("[ActionMap] Error: Keymap id '%s' in context '%s' in file '%s' is undefined/invalid!" % (keyName, context, filename))
						error = True
			except ValueError:
				print("[ActionMap] Error: Keymap id '%s' in context '%s' in file '%s' can not be evaluated!" % (keyName, context, filename))
				keyId = -1
				error = True
		mapto = key.attrib.get("mapto")
		unmap = key.attrib.get("unmap")
		if mapto is None and unmap is None:
			print("[ActionMap] Error: At least one of the attributes 'mapto' or 'unmap' in context '%s' id '%s' (%d) in file '%s' must be specified!" % (context, keyName, keyId, filename))
			error = True
		flags = key.attrib.get("flags")
		if flags is None:
			print("[ActionMap] Error: Attribute 'flag' in context '%s' id '%s' (%d) in file '%s' must be specified!" % (context, keyName, keyId, filename))
			error = True
		else:
			flagToValue = lambda x: {
				'm': 1,
				'b': 2,
				'r': 4,
				'l': 8
			}[x]
			newFlags = sum(map(flagToValue, flags))
			if not newFlags:
				print("[ActionMap] Error: Attribute 'flag' value '%s' in context '%s' id '%s' (%d) in file '%s' appears invalid!" % (flags, context, keyName, keyId, filename))
				error = True
			flags = newFlags
		if not error:
			if unmap is None:  # If a key was unmapped, it can only be assigned a new function in the same keymap file (avoid file parsing sequence dependency).
				if unmapDict.get((context, keyName, mapto)) in [filename, None]:
					# print("[ActionMap] DEBUG: Context '%s' keyName '%s' (%d) mapped to '%s' (Device: %s)." % (context, keyName, keyId, mapto, device.capitalize()))
					actionMapInstance.bindKey(filename, device, keyId, flags, context, mapto)
					addKeyBinding(filename, keyId, context, mapto, flags)
			else:
				actionMapInstance.unbindPythonKey(context, keyId, unmap)
				unmapDict.update({(context, keyName, unmap): filename})


def loadKeymap(filename):
	actionMapInstance = eActionMap.getInstance()
	domKeymap = fileReadXML(filename, source=MODULE_NAME)
	if domKeymap:
		for domMap in domKeymap.findall("map"):
			context = domMap.attrib.get("context")
			if context is None:
				print("ActionMap] Error: All keymap action maps in '%s' must have a context!" % filename)
			else:
				parseKeymap(filename, context, actionMapInstance, "generic", domMap)
				for domDevice in domMap.findall("device"):
					parseKeymap(filename, context, actionMapInstance, domDevice.attrib.get("name"), domDevice)


def removeKeymap(filename):
	actionMapInstance = eActionMap.getInstance()
	actionMapInstance.unbindKeyDomain(filename)


class ActionMap:
	def __init__(self, contexts=None, actions=None, prio=0):
		self.contexts = contexts or []
		self.actions = actions or {}
		self.prio = prio
		self.p = eActionMap.getInstance()
		self.bound = False
		self.exec_active = False
		self.enabled = True
		unknown = list(self.actions.keys())
		for action in unknown[:]:
			for context in self.contexts:
				if queryKeyBinding(context, action):
					unknown.remove(action)
					break
		if unknown:
			print(_("[ActionMap] Missing actions in keymap, missing context in this list ->'%s' for mapto='%s'.") % ("', '".join(sorted(self.contexts)), "', '".join(sorted(list(self.actions.keys())))))

	def setEnabled(self, enabled):
		self.enabled = enabled
		self.checkBind()

	def doBind(self):
		if not self.bound:
			for context in self.contexts:
				self.p.bindAction(context, self.prio, self.action)
			self.bound = True

	def doUnbind(self):
		if self.bound:
			for context in self.contexts:
				self.p.unbindAction(context, self.action)
			self.bound = False

	def checkBind(self):
		if self.exec_active and self.enabled:
			self.doBind()
		else:
			self.doUnbind()

	def execBegin(self):
		self.exec_active = True
		self.checkBind()

	def execEnd(self):
		self.exec_active = False
		self.checkBind()

	def action(self, context, action):
		if action in self.actions:
			print("[ActionMap] Keymap '%s' -> Action mapto='%s'." % (context, action))
			res = self.actions[action]()
			if res is not None:
				return res
			return 1
		else:
			print(_("[ActionMap] in this context list -> '%s' -> mapto='%s' it is not defined in this code 'missing'.") % (context, action))
			return 0

	def destroy(self):
		pass


class NumberActionMap(ActionMap):
	def action(self, contexts, action):
		if action in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9") and action in self.actions:
			res = self.actions[action](int(action))
			if res is not None:
				return res
			return 1
		else:
			return ActionMap.action(self, contexts, action)


class HelpableActionMap(ActionMap):
	# An Actionmap which automatically puts the actions into the helpList.
	#
	# A context list is allowed, and for backward compatibility, a single
	# string context name also is allowed.
	#
	# Sorry for this complicated code.  It's not more than converting a
	# "documented" actionmap (where the values are possibly (function,
	# help)-tuples) into a "classic" actionmap, where values are just
	# functions.  The classic actionmap is then passed to the
	# ActionMapconstructor,	the collected helpstrings (with correct
	# context, action) is added to the screen's "helpList", which will
	# be picked up by the "HelpableScreen".
	def __init__(self, parent, contexts, actions=None, prio=0, description=None):
		def exists(record):
			for context in parent.helpList:
				if record in context[2]:
					print("[ActionMap] removed duplicity: %s %s" % (context[1], record))
					return True
			return False

		if isinstance(contexts, str):
			contexts = [contexts]
		actions = actions or {}
		self.description = description
		adict = {}
		for context in contexts:
			alist = []
			for (action, funchelp) in actions.items():
				# Check if this is a tuple.
				if isinstance(funchelp, tuple):
					if queryKeyBinding(context, action):
						if not exists((action, funchelp[1])):
							alist.append((action, funchelp[1]))
					adict[action] = funchelp[0]
				else:
					if queryKeyBinding(context, action):
						if not exists((action, None)):
							alist.append((action, None))
					adict[action] = funchelp
			parent.helpList.append((self, context, alist))
		ActionMap.__init__(self, contexts, adict, prio)


class HelpableNumberActionMap(NumberActionMap, HelpableActionMap):
	def __init__(self, parent, contexts, actions=None, prio=0, description=None):
		# Initialise NumberActionMap with empty context and actions
		# so that the underlying ActionMap is only initialised with
		# these once, via the HelpableActionMap.
		#
		NumberActionMap.__init__(self, [], {})
		HelpableActionMap.__init__(self, parent, contexts, actions, prio, description)
