"""
Hypertext Transfer Protocol.
"""

from pypacker import pypacker, triggerlist

import re
import logging

logger = logging.getLogger("pypacker")


class HTTPTriggerList(triggerlist.TriggerList):
	def _pack(self):
		#logger.debug("packing HTTP-header")
		# no header = no CRNL
		if len(self) == 0:
			#logger.debug("empty buf 2")
			return b""
		packed = []
		itera = iter(self)
		packed.append( next(itera)[0] )	# startline

		for h in itera:
			#logger.debug("key/value: %s/%s" % (h[0], h[1]))
			# TODO: more performant
			packed.append(b": ".join(h))
		return b"\r\n".join(packed)

	def _get_positions_for_bytes(self, bts):
		# just return first match
		for pos, key_val in enumerate(self):
			if key_val[0].lower().startswith(bts.lower()):
				return pos
		raise KeyError


class HTTP(pypacker.Packet):
	__hdr__ = (
		#("req_resp", None, triggerlist.Triggerlist),
		("header", None, HTTPTriggerList),
	)

	__REQ_METHODS_BASIC	= set([b"GET", b"POST", b"HEAD", b"PUT", b"OPTIONS", b"CONNECT", b"UPDATE", b"TRACE"])
	__PROG_SPLIT_HEADBODY	= re.compile(b"\r\n\r\n")
	__PROG_SPLIT_HEADER	= re.compile(b"\r\n")
	__PROG_SPLIT_KEYVAL	= re.compile(b": ")

	def _dissect(self, buf):
		# parse header if this is the start of a request/response
		# requestline: [method] [uri] [version] -> GET / HTTP/1.1
		# responseline: [version] [status] [reason] -> HTTP/1.1 200 OK
		spos = buf.find(b" ")
		# search for "METHOD ..." or "HTTP/1.1 ...
		if (spos < 3 or not buf[:spos] in HTTP.__REQ_METHODS_BASIC) and not buf.startswith(b"HTTP/1."):
			return

		bts_header, bts_body = HTTP.__PROG_SPLIT_HEADBODY.split(buf, 1)
		self.header.init_lazy_dissect(bts_header, self.__parse_header)

	def __parse_header(self, buf):
		#logger.debug("parsing: %s" % buf)
		header = []

		lines = HTTP.__PROG_SPLIT_HEADER.split(buf)
		reqline = lines[0]
		del lines[0]
		header.append((reqline,))

		for line in lines:
			#logger.debug("checking HTTP-header: %s" % line)
			if len(line) == 0:
				break
			key, val = HTTP.__PROG_SPLIT_KEYVAL.split(line, 1)
			header.append((key, val))

		return header
