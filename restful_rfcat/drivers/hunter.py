# A device driver to interact with Hunter ceiling fans
from operator import itemgetter
import threading
import logging
import re
import struct
import time
from restful_rfcat import radio
from restful_rfcat.drivers._utils import DeviceDriver, PWMThreeSymbolMixin, ThreeSpeedFanMixin, LightMixin

logger = logging.getLogger(__name__)

class HunterCeiling(DeviceDriver, PWMThreeSymbolMixin):
	devices = {}
	commands = {
		'fan0': '1001',
		'fan1': '0001',
		'fan2': '0010',
		'fan3': '0100',
		'light': '1000'
	}
	commands_rev = dict([(v,k) for k,v in commands.items()])
	radio = radio.OOKRadioChannelHack(347999900, 5280, 2)

	def __init__(self, dip_switch, **kwargs):
		""" dip_switch is the jumper settings from the remote
		Left (4) to right (1), with connected jumpers as 1 and others as 1
		"""
		# save the name and label
		super(HunterCeiling, self).__init__(**kwargs)
		self.dip_switch = dip_switch
		self._remember_device()

	def _remember_device(self):
		# magical registration of devices for eavesdropping
		class_name = self.__class__.__name__
		device_type = class_name[len('HunterCeiling'):].lower()
		device_name = '%s-%s' % (self.dip_switch, device_type)
		self.devices[device_name] = self

	@staticmethod
	def _encode(bin_key):
		"""
		>>> print(HunterCeiling._encode("00110011"))
		\x00\x00\x00\x00\x01%\xb2[
		"""
		pwm_str_key = HunterCeiling._encode_pwm_symbols(bin_key)
		pwm_str_key = "001" + pwm_str_key #added leading 0 for clock
		#print "Binary (PWM) key:",pwm_str_key
		dec_pwm_key = int(pwm_str_key, 2);
		#print "Decimal (PWN) key:",dec_pwm_key
		key_packed = struct.pack(">Q", dec_pwm_key)
		return key_packed

	@classmethod
	def _send(klass, bits, repeat=None):
		symbols = klass._encode(bits)
		if repeat is None:
			klass.radio.send(symbols + '\x00')
		else:
			klass.radio.send(symbols + '\x00', repeat)

	def _send_command(self, command, repeat=None):
		logger.info("Sending command %s to %s" % (command, self.dip_switch))
		self._send(self._get_bin_key(command), repeat)

	def _get_bin_key(self, command):
		"""
		>>> HunterCeiling(name='test', label='Test', dip_switch='1011')._get_bin_key('fan2')
		'011011110010'
		>>> HunterCeiling(name='test', label='Test', dip_switch='0010')._get_bin_key('light')
		'001001111000'
		"""
		bin_key = '0%s111%s' % (self.dip_switch[::-1], self.commands[command])
		return bin_key

class HunterCeilingFan(ThreeSpeedFanMixin, HunterCeiling):
	def _send_command(self, command, repeat=None):
		# ThreeSpeedFanMixin will send a command of 0,1,2,3
		# Change this to fan0, fan1, fan2, fan3 for HunterCeiling
		super(HunterCeilingFan, self)._send_command('fan' + command, repeat)

class HunterCeilingLight(LightMixin, HunterCeiling):
	last_set = 0

	def set_state(self, state):
		""" Hunter ceiling lights don't have an idempotent ON/OFF
		    so we just always send the toggle command, and save the
		    user's intended state, assuming the user knows what he wants changed
		"""
		if state not in self.get_available_states():
			raise ValueError("Invalid state: %s" % (state,))
		if time.time() < self.last_set + 5 and \
		   self._get() == state:
			# debounce duplicate light settings for 5 seconds
			# in case something was slow and the user clicked twice
			# very important with Hunter because it's a toggle light
			logger.info("Ignoring quickly-repeated light command")
			return self._get()
		self.last_set = time.time()
		repeat = None
		if state == "ON" and self._get() == "ON":
			logger.info("%s light should already be on, forcing on" % (self.name,))
			repeat = 100	# send a dim command to force on
		self._send_command('light', repeat)
		self._set(state)
		return state

class HunterCeilingEavesdropper(HunterCeiling):
	radio = radio.OOKRadioChannelHack(347999900, 5280, 2.1, 250000)
	def __init__(self):
		# don't register as a device with the regular super constractor
		# which packets we saw
		self.packets_seen = {}
		# how long ago we saw a packet
		self.packet_last_seen = 9

	@staticmethod
	def _decode_pwm_symbols(symbols):
		""" Decode the eavesdropped remote control transmission into a PWM-decoded packet
		    Since it starts with a clock bit, strip it before processing as PWM

		>>> HunterCeilingEavesdropper._decode_pwm_symbols("1001011001011")
		'0101'
		>>> HunterCeilingEavesdropper._decode_pwm_symbols( \
		        '1'+HunterCeiling._encode_pwm_symbols("001001110101") \
		)
		'001001110101'

		# sometimes the 0 bits get held a little longer
		>>> HunterCeilingEavesdropper._decode_pwm_symbols("10010011001011")
		'0101'
		"""
		if symbols is None or len(symbols) < 10 or symbols[0] != '1':
			return None
		return HunterCeiling._decode_pwm_symbols(symbols[1:])

	@staticmethod
	def _parse_packet(packet):
		""" Returns (dip_switch, command) for a valid packet
		    else returns (None, None)
		>>> HunterCeilingEavesdropper._parse_packet("001001110101")
		('0010', '0101')
		"""
		if len(packet) == 12:
			match = re.match('0([01]{4})111([01]{4})', packet)
			if match is not None:
				return (match.group(1)[::-1], match.group(2))
		return (None, None)

	@classmethod
	def validate_packet(klass, packet):
		""" Given a decoded packet
		    check that the given packet is syntactical
		>>> HunterCeilingEavesdropper.validate_packet("001001110101")
		False
		>>> HunterCeilingEavesdropper.validate_packet("001001110100")
		True
		"""
		if packet is None:
			return False
		(dip_switch, command) = klass._parse_packet(packet)
		return command is not None and command in klass.commands_rev

	@classmethod
	def handle_packet(klass, packet, count):
		(dip_switch, command) = klass._parse_packet(packet)
		logger.info("Overheard command %s to %s, %s times" % (command, dip_switch, count))
		if command is not None and command in klass.commands_rev:
			# find device
			command = klass.commands_rev[command]
			if command.startswith('fan'):
				device_type = 'fan'
			elif command.startswith('light'):
				device_type = 'light'
			device_name = '%s-%s' % (dip_switch, device_type)
			found_device = klass.devices.get(device_name)
			# find new state
			state = None
			if command.startswith('fan'):
				# idempotent state set
				state = command[3]
				if state == '0':
					state = 'OFF'
			elif command.startswith('light'):
				if found_device is not None:
					# toggle light
					old_state = found_device._get()
					available_states = found_device.get_available_states()
					try:
						old_state_index = available_states.index(old_state)
						new_state_index = len(available_states) - 1 - old_state_index
						state = available_states[new_state_index]
					except ValueError:
						# don't know current state, don't guess new state
						pass
				if count > 47:
					# dim command, not a toggle
					# so assume that the light was turned on
					state = 'ON'
			if found_device is not None and state is not None:
				logger.info("Eavesdropped command to turn %s-%s to %s" % (found_device.name, device_type, state))
				if hasattr(found_device, '_handle_state_update'):
					found_device._handle_state_update(state)
				else:
					found_device._set(state)

	def eavesdrop(self):
		packets = self.radio.receive_packets(20)
		if packets is None:
			# error, try again next time
			return None
		# try to parse each packet, skipping the clock bit at the start
		self.packet_last_seen = min(9, self.packet_last_seen + 1)
		logical_packets = [self._decode_pwm_symbols(p) for p in packets]
		for p in logical_packets:
			if not self.validate_packet(p):
				continue
			count = self.packets_seen.get(p, 0)
			self.packets_seen[p] = count + 1
			self.packet_last_seen = 0

		if self.packet_last_seen > 3:
			if len(self.packets_seen) > 0:
				# end of an existing transmission
				key, count = max(self.packets_seen.items(), key=itemgetter(1))
				self.handle_packet(key, count)
				self.packets_seen.clear()

	def run(self):
		self.request_stop = threading.Event()
		while not self.request_stop.is_set():
			self.eavesdrop()
		self.radio.reset_device()

	def stop(self):
		self.request_stop.set()
