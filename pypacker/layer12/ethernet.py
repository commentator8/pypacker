"""
Ethernet II, IEEE 802.3

RFC 1042
"""

from pypacker import pypacker, triggerlist

import logging
import struct

# avoid unneeded references for performance reasons
pack = struct.pack
unpack = struct.unpack

logger = logging.getLogger("pypacker")

ETH_CRC_LEN	= 4
ETH_HDR_LEN	= 14

ETH_LEN_MIN	= 64		# minimum frame length with CRC
ETH_LEN_MAX	= 1518		# maximum frame length with CRC

ETH_MTU		= (ETH_LEN_MAX - ETH_HDR_LEN - ETH_CRC_LEN)
ETH_MIN		= (ETH_LEN_MIN - ETH_HDR_LEN - ETH_CRC_LEN)

# Ethernet payload types - http://standards.ieee.org/regauth/ethertype
ETH_TYPE_PUP		= 0x0200		# PUP protocol
ETH_TYPE_IP		= 0x0800		# IPv4 protocol
ETH_TYPE_ARP		= 0x0806		# address resolution protocol
ETH_TYPE_WOL		= 0x0842		# Wake on LAN
ETH_TYPE_CDP		= 0x2000		# Cisco Discovery Protocol
ETH_TYPE_DTP		= 0x2004		# Cisco Dynamic Trunking Protocol
ETH_TYPE_REVARP		= 0x8035		# reverse addr resolution protocol
ETH_TYPE_ETHTALK	= 0x809B		# Apple Talk
ETH_TYPE_AARP		= 0x80F3		# Appletalk Address Resolution Protocol
ETH_TYPE_8021Q		= 0x8100		# IEEE 802.1Q VLAN tagging
ETH_TYPE_IPX		= 0x8137		# Internetwork Packet Exchange
ETH_TYPE_NOV		= 0x8138		# Novell
ETH_TYPE_IP6		= 0x86DD		# IPv6 protocol
ETH_TYPE_MPLS_UCAST	= 0x8847		# MPLS unicast
ETH_TYPE_MPLS_MCAST	= 0x8848		# MPLS multicast
ETH_TYPE_PPOE_DISC	= 0x8863		# PPPoE Discovery
ETH_TYPE_PPOE_SESS	= 0x8864		# PPPoE Session
ETH_TYPE_JUMBOF		= 0x8870		# Jumbo Frames
ETH_TYPE_PROFINET	= 0x8892		# Realtime-Ethernet PROFINET
ETH_TYPE_ATAOE		= 0x88A2		# ATA other Ethernet
ETH_TYPE_ETHERCAT	= 0x88A4		# Realtime-Ethernet Ethercat
ETH_TYPE_PBRIDGE	= 0x88A8		# Provider Bridging IEEE 802.1ad
ETH_TYPE_POWERLINK	= 0x88AB		# Realtime Ethernet POWERLINK
ETH_TYPE_LLDP		= 0x88CC		# Link Layer Discovery Protocol
ETH_TYPE_SERCOS		= 0x88CD		# Realtime Ethernet SERCOS III
ETH_TYPE_FIBRE_ETH	= 0x8906		# Fibre Channel over Ethernet
ETH_TYPE_FCOE		= 0x8914		# FCoE Initialization Protocol (FIP)
ETH_TYPE_TUNNELING	= 0x9100		# Provider Bridging IEEE 802.1QInQ 2007

ETH_TYPE_LLC		= 0xFFFFF


# MPLS label stack fields
MPLS_LABEL_MASK		= 0xfffff000
MPLS_QOS_MASK		= 0x00000e00
MPLS_TTL_MASK		= 0x000000ff
MPLS_LABEL_SHIFT	= 12
MPLS_QOS_SHIFT		= 9
MPLS_TTL_SHIFT		= 0
MPLS_STACK_BOTTOM	= 0x0100


class Dot1Q(pypacker.Packet):
	__hdr__ = (
		("type", "H", ETH_TYPE_IP),
		("tci", "H", 0) 	# tag control information PCP(3 bits),CFI(1 bit), VID(12 bits)
	)

	def __get_prio(self):
		return (self.tci & 0xe000) >> 13

	def __set_prio(self, value):
		self.tci = (value & 7) << 13
	prio = property(__get_prio, __set_prio)

	def __get_cfi(self):
		return (self.tci & 0x1000) >> 12

	def __set_cfi(self, value):
		self.tci = (value & 1) << 12
	cfi = property(__get_cfi, __set_cfi)

	def __get_vid(self):
		return self.tci & 0x0fff

	def __set_vid(self, value):
		self.tci = value & 0xfff
	vid = property(__get_vid, __set_vid)


bridge_types_set = set([ETH_TYPE_8021Q, ETH_TYPE_PBRIDGE, ETH_TYPE_TUNNELING])


class Ethernet(pypacker.Packet):
	__hdr__ = (
		("dst", "6s", b"\xff" * 6),
		("src", "6s", b"\xff" * 6),
		("vlan", None, triggerlist.TriggerList),
		# ("len", "H", None),
		("type", "H", ETH_TYPE_IP)		# type = Ethernet II, len = 802.3
	)

	dst_s = pypacker.get_property_mac("dst")
	src_s = pypacker.get_property_mac("src")

	def _dissect(self, buf):
		hlen = 14
		# we need to check for VLAN TPID here (0x8100) to get correct header-length
		type_len = unpack(">H", buf[12: 14])[0]

		# based on the type field, following bytes can be intrepreted differently than standard Ethernet II
		# Examples: 802.3/802.2 LLC or 802.3/802.2 SNAP

		if type_len in bridge_types_set:
			#logger.debug(">>> got vlan tag")
			# support up to 2 tags (double tagging aka QinQ)
			# triggerlist can't be initiated using _init_triggerlist() as amount of needed bytes is not known
			# -> full parsing of Dot1Q-part needed
			for _ in range(2):
				vlan_tag = Dot1Q(buf[hlen - 2: hlen + 2])

				if vlan_tag.type not in bridge_types_set:
					break
				# logger.debug("re-extracting field: %s" % self.vlan)
				self.vlan.append(vlan_tag)
				hlen += 4
				self.type = vlan_tag.type

		# avoid calling unpack more than once
		eth_type = unpack(">H", buf[hlen - 2: hlen])[0]
		# logger.debug("hlen is: %d" % eth_type)

		# handle ethernet-padding: remove it but save for later use
		# don't use headers for this because this is a rare situation
		dlen = len(buf) - hlen		# data length [+ padding?]

		try:
			# this will only work on complete headers: Ethernet + IP + ...
			# handle padding using IPv4, IPv6
			# TODO: check for other protocols
			# logger.debug(">>> checking for padding")
			if eth_type == ETH_TYPE_IP:

				dlen_ip = unpack(">H", buf[hlen + 2: hlen + 4])[0]		# real data length

				if dlen_ip < dlen:
					# padding found
					# logger.debug("got padding for IPv4")
					self._padding = buf[hlen + dlen_ip:]
					dlen = dlen_ip
			# handle padding using IPv6
			# IPv6 is a piece of sh$§! payloadlength = exclusive standard header, INCLUSIVE options!
			elif eth_type == ETH_TYPE_IP6:
				dlen_ip = unpack(">H", buf[hlen + 4: hlen + 6])[0]		# real data length
				if 40 + dlen_ip < dlen:
					# padding found
					# logger.debug("got padding for IPv6")
					self._padding = buf[hlen + dlen_ip:]
					dlen = dlen_ip
		except struct.error:
			# logger.debug("could not extract padding info, assuming incomplete ethernet frame")
			pass
		except:
			logger.exception("could not extract padding info")

		self._init_handler(eth_type, buf[hlen: hlen + dlen])
		return hlen

	def bin(self, update_auto_fields=True):
		"""Custom bin(): handle padding for Ethernet."""
		return pypacker.Packet.bin(self, update_auto_fields=update_auto_fields) + self.padding

	def __len__(self):
		return super().__len__() + len(self.padding)

	def direction(self, other):
		# logger.debug("checking direction: %s<->%s" % (self, other))
		if self.dst == other.dst and self.src == other.src:
			# consider packet to itself: can be DIR_REV
			return pypacker.Packet.DIR_SAME | pypacker.Packet.DIR_REV
		elif (self.dst == other.src and self.src == other.dst) or\
			(self.dst == b"\xff\xff\xff\xff\xff\xff" and other.dst == self.src):		# broadcast
			return pypacker.Packet.DIR_REV
		else:
			return pypacker.Packet.DIR_UNKNOWN

	# handle padding attribute
	def __get_padding(self):
		try:
			return self._padding
		except AttributeError:
			return b""

	def __set_padding(self, padding):
		self._padding = padding

	padding = property(__get_padding, __set_padding)

	def reverse_address(self):
		self.dst, self.src = self.src, self.dst

# load handler
from pypacker.layer12 import arp, dtp, pppoe, llc
from pypacker.layer3 import ip, ip6, ipx

pypacker.Packet.load_handler(Ethernet,
	{
		ETH_TYPE_IP: ip.IP,
		ETH_TYPE_ARP: arp.ARP,
		ETH_TYPE_DTP: dtp.DTP,
		ETH_TYPE_IPX: ipx.IPX,
		ETH_TYPE_IP6: ip6.IP6,
		ETH_TYPE_PPOE_DISC: pppoe.PPPoE,
		ETH_TYPE_PPOE_SESS: pppoe.PPPoE,
		ETH_TYPE_LLC: llc.LLC,
	}
)
