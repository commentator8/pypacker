"""
Internet Protocol version 4.

RFC 791
"""

from pypacker import pypacker, triggerlist, checksum
from pypacker.layer3.ip_shared import *

import logging

logger = logging.getLogger("pypacker")


# IP options
# http://www.iana.org/assignments/ip-parameters/ip-parameters.xml
IP_OPT_EOOL			= 0
IP_OPT_NOP			= 1
IP_OPT_SEC			= 2
IP_OPT_LSR			= 3
IP_OPT_TS			= 4
IP_OPT_ESEC			= 5
IP_OPT_CIPSO			= 6
IP_OPT_RR			= 7
IP_OPT_SID			= 8
IP_OPT_SSR			= 9
IP_OPT_ZSU			= 10
IP_OPT_MTUP			= 11
IP_OPT_MTUR			= 12
IP_OPT_FINN			= 13
IP_OPT_VISA			= 14
IP_OPT_ENCODE			= 15
IP_OPT_IMITD			= 16
IP_OPT_EIP			= 17
IP_OPT_TR			= 18
IP_OPT_ADDEXT			= 19
IP_OPT_RTRALT			= 20
IP_OPT_SDB			= 21
IP_OPT_UNASSGNIED		= 22
IP_OPT_DPS			= 23
IP_OPT_UMP			= 24
IP_OPT_QS			= 25
IP_OPT_EXP			= 30


class IPOptSingle(pypacker.Packet):
	__hdr__ = (
		("type", "B", 0),
	)


class IPOptMulti(pypacker.Packet):
	"""
	len = total length (header + data)
	"""
	__hdr__ = (
		("type", "B", 0),
		("len", "B", 2),
	)

	def bin(self, update_auto_fields=True):
		if update_auto_fields:
			self.len = len(self)
		return pypacker.Packet.bin(self, update_auto_fields=update_auto_fields)


class IPTriggerList(triggerlist.TriggerList):
	def _handle_mod(self, v):
		"""Update header length. NOTE: needs to be a multiple of 4 Bytes."""
		# TODO: this will repack the whole header
		#logger.debug("updating: %r" % self._packet)
		# options length need to be multiple of 4 Bytes
		hdr_len_off = int(self._packet.hdr_len / 4) & 0xf
		#logger.debug("IP: new hl: %d / %d" % (self._packet.hdr_len, hdr_len_off))
		self._packet.hl = hdr_len_off


class IP(pypacker.Packet):
	"""Convenient access for: src[_s], dst[_s]"""
	__hdr__ = (
		("v_hl", "B", 69),		# = 0x45
		("tos", "B", 0),
		("len", "H", 20),
		("id", "H", 0),
		("off", "H", 0),
		("ttl", "B", 64),
		("p", "B", IP_PROTO_TCP),
		("sum", "H", 0),
		("src", "4s", b"\x00" * 4),
		("dst", "4s", b"\x00" * 4),
		("opts", None, IPTriggerList)
	)

	def __get_v(self):
		return self.v_hl >> 4

	def __set_v(self, value):
		self.v_hl = (value << 4) | (self.v_hl & 0xf)
	v = property(__get_v, __set_v)

	def __get_hl(self):
		return self.v_hl & 0x0f

	def __set_hl(self, value):
		self.v_hl = (self.v_hl & 0xf0) | value
	hl = property(__get_hl, __set_hl)

	## convenient access
	src_s = pypacker.get_property_ip4("src")
	dst_s = pypacker.get_property_ip4("dst")

	def _dissect(self, buf):
		ol = ((buf[0] & 0xf) << 2) - 20		# total IHL - standard IP-len = options length

		if ol < 0:
			# invalid header length: assume no options at all
			raise Exception("invalid header length: %d" % ol)
		elif ol > 0:
			#logger.debug("got some IP options: %s" % tl_opts)
			self.opts.init_lazy_dissect(buf[20: 20 + ol], self.__parse_opts)

		self._parse_handler(buf[9], buf[self.hdr_len:])
		return 20+ol

	__IP_OPT_SINGLE = set([IP_OPT_EOOL, IP_OPT_NOP])

	def __parse_opts(self, buf):
		"""Parse IP options and return them as List."""
		optlist = []
		i = 0
		p = None

		while i < len(buf):
			#logger.debug("got IP-option type %s" % buf[i])
			if buf[i] in IP.__IP_OPT_SINGLE:
				p = IPOptSingle(type=buf[i])
				i += 1
			else:
				olen = buf[i + 1]
				#logger.debug("IPOptMulti")
				p = IPOptMulti(type=buf[i], len=olen, body_bytes=buf[i + 2: i + olen])
				#logger.debug("body bytes: %s" % buf[i + 2: i + olen])
				i += olen		# typefield + lenfield + data-len
				#logger.debug("IPOptMulti 2")
			optlist.append(p)
		return optlist

	def bin(self, update_auto_fields=True):
		if update_auto_fields:
			if self._changed():
				#logger.debug("updating length")
				self.len = len(self)

				if self._header_changed:
					#logger.debug("updating checksum")
					#logger.debug(">>> IP: calculating sum")
					# reset checksum for recalculation,  mark as changed / clear cache
					self.sum = 0
					#logger.debug(">>> IP: bytes for sum: %s" % self.header_bytes)
					self.sum = checksum.in_cksum(self._pack_header())

		return pypacker.Packet.bin(self, update_auto_fields=update_auto_fields)

	def _direction(self, next):
		#logger.debug("checking direction: %s<->%s" % (self, next))
		# TODO: handle broadcast
		if self.src == next.src and self.dst == next.dst:
			# consider packet to itself: can be DIR_REV
			return pypacker.Packet.DIR_SAME | pypacker.Packet.DIR_REV
		elif self.src == next.dst and self.dst == next.src:
			return pypacker.Packet.DIR_REV
		else:
			return pypacker.Packet.DIR_UNKNOWN

	def reverse_address(self):
		self.src, self.dst = self.dst, self.src


# Type of service (ip_tos), RFC 1349 ("obsoleted by RFC 2474")
IP_TOS_DEFAULT			= 0x00			# default
IP_TOS_LOWDELAY			= 0x10			# low delay
IP_TOS_THROUGHPUT		= 0x08			# high throughput
IP_TOS_RELIABILITY		= 0x04			# high reliability
IP_TOS_LOWCOST			= 0x02			# low monetary cost - XXX
IP_TOS_ECT			= 0x02			# ECN-capable transport
IP_TOS_CE			= 0x01			# congestion experienced

# IP precedence (high 3 bits of ip_tos), hopefully unused
IP_TOS_PREC_ROUTINE		= 0x00
IP_TOS_PREC_PRIORITY		= 0x20
IP_TOS_PREC_IMMEDIATE		= 0x40
IP_TOS_PREC_FLASH		= 0x60
IP_TOS_PREC_FLASHOVERRIDE	= 0x80
IP_TOS_PREC_CRITIC_ECP		= 0xa0
IP_TOS_PREC_INTERNETCONTROL	= 0xc0
IP_TOS_PREC_NETCONTROL		= 0xe0

# Fragmentation flags (ip_off)
IP_RF				= 0x8000		# reserved
IP_DF				= 0x4000		# don't fragment
IP_MF				= 0x2000		# more fragments (not last frag)
IP_OFFMASK			= 0x1fff		# mask for fragment offset

# Time-to-live (ip_ttl), seconds
IP_TTL_DEFAULT			= 64			# default ttl, RFC 1122, RFC 1340
IP_TTL_MAX			= 255			# maximum ttl

# load handler
from pypacker.layer3 import esp, icmp, igmp, ip6, ipx, ospf, pim
from pypacker.layer4 import tcp, udp, sctp

pypacker.Packet.load_handler(IP,
	{
		IP_PROTO_IP: IP,
		IP_PROTO_ICMP: icmp.ICMP,
		IP_PROTO_IGMP: igmp.IGMP,
		IP_PROTO_TCP: tcp.TCP,
		IP_PROTO_UDP: udp.UDP,
		IP_PROTO_IP6: ip6.IP6,
		IP_PROTO_ESP: esp.ESP,
		IP_PROTO_PIM: pim.PIM,
		IP_PROTO_IPXIP: ipx.IPX,
		IP_PROTO_SCTP: sctp.SCTP,
		IP_PROTO_OSPF: ospf.OSPF
	}
)
