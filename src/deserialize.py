# this code comes from ABE. it can probably be simplified
#
#

import mmap
import string
import struct
import types
import time
from processor import print_log

from utils import hash_160_to_pubkey_address, hash_160_to_script_address, public_key_to_pubkey_address, hash_encode,\
    hash_160, Hash

import bitcoin
from bitcoin import *
import sys

#
# Workalike python implementation of Bitcoin's CDataStream class.
#
import struct
import StringIO
import random

NO_SIGNATURE = 'ff'

class SerializationError(Exception):
    """Thrown when there's a problem deserializing or serializing."""


class BCDataStream(object):
    """Workalike python implementation of Bitcoin's CDataStream class."""
    def __init__(self):
        self.input = None
        self.read_cursor = 0

    def clear(self):
        self.input = None
        self.read_cursor = 0

    def write(self, bytes):    # Initialize with string of bytes
        if self.input is None:
            self.input = bytes
        else:
            self.input += bytes

    def map_file(self, file, start):    # Initialize with bytes from file
        self.input = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        self.read_cursor = start

    def seek_file(self, position):
        self.read_cursor = position

    def close_file(self):
        self.input.close()

    def read_string(self):
        # Strings are encoded depending on length:
        # 0 to 252 :    1-byte-length followed by bytes (if any)
        # 253 to 65,535 : byte'253' 2-byte-length followed by bytes
        # 65,536 to 4,294,967,295 : byte '254' 4-byte-length followed by bytes
        # ... and the Bitcoin client is coded to understand:
        # greater than 4,294,967,295 : byte '255' 8-byte-length followed by bytes of string
        # ... but I don't think it actually handles any strings that big.
        if self.input is None:
            raise SerializationError("call write(bytes) before trying to deserialize")

        try:
            length = self.read_compact_size()
        except IndexError:
            raise SerializationError("attempt to read past end of buffer")

        return self.read_bytes(length)

    def write_string(self, string):
        # Length-encoded as with read-string
        self.write_compact_size(len(string))
        self.write(string)

    def read_bytes(self, length):
        try:
            result = self.input[self.read_cursor:self.read_cursor+length]
            self.read_cursor += length
            return result
        except IndexError:
            raise SerializationError("attempt to read past end of buffer")

        return ''

    def read_boolean(self):
        return self.read_bytes(1)[0] != chr(0)

    def read_int16(self):
        return self._read_num('<h')

    def read_uint16(self):
        return self._read_num('<H')

    def read_int32(self):
        return self._read_num('<i')

    def read_uint32(self):
        return self._read_num('<I')

    def read_int64(self):
        return self._read_num('<q')

    def read_uint64(self):
        return self._read_num('<Q')

    def read_uint256(self):
        return self.read(32)[::-1]

    def write_boolean(self, val):
        return self.write(chr(1) if val else chr(0))

    def write_int16(self, val):
        return self._write_num('<h', val)

    def write_uint16(self, val):
        return self._write_num('<H', val)

    def write_int32(self, val):
        return self._write_num('<i', val)

    def write_uint32(self, val):
        return self._write_num('<I', val)

    def write_int64(self, val):
        return self._write_num('<q', val)

    def write_uint64(self, val):
        return self._write_num('<Q', val)

    def read_compact_size(self):
        size = ord(self.input[self.read_cursor])
        self.read_cursor += 1
        if size == 253:
            size = self._read_num('<H')
        elif size == 254:
            size = self._read_num('<I')
        elif size == 255:
            size = self._read_num('<Q')
        return size

    def write_compact_size(self, size):
        if size < 0:
            raise SerializationError("attempt to write size < 0")
        elif size < 253:
            self.write(chr(size))
        elif size < 2**16:
            self.write('\xfd')
            self._write_num('<H', size)
        elif size < 2**32:
            self.write('\xfe')
            self._write_num('<I', size)
        elif size < 2**64:
            self.write('\xff')
            self._write_num('<Q', size)

    def _read_num(self, format):
        (i,) = struct.unpack_from(format, self.input, self.read_cursor)
        self.read_cursor += struct.calcsize(format)
        return i

    def _write_num(self, format, num):
        s = struct.pack(format, num)
        self.write(s)


class EnumException(Exception):
    pass


class Enumeration:
    """enum-like type

    From the Python Cookbook, downloaded from http://code.activestate.com/recipes/67107/
    """

    def __init__(self, name, enumList):
        self.__doc__ = name
        lookup = {}
        reverseLookup = {}
        i = 0
        uniqueNames = []
        uniqueValues = []
        for x in enumList:
            if isinstance(x, types.TupleType):
                x, i = x
            if not isinstance(x, types.StringType):
                raise EnumException("enum name is not a string: %r" % x)
            if not isinstance(i, types.IntType):
                raise EnumException("enum value is not an integer: %r" % i)
            if x in uniqueNames:
                raise EnumException("enum name is not unique: %r" % x)
            if i in uniqueValues:
                raise EnumException("enum value is not unique for %r" % x)
            uniqueNames.append(x)
            uniqueValues.append(i)
            lookup[x] = i
            reverseLookup[i] = x
            i = i + 1
        self.lookup = lookup
        self.reverseLookup = reverseLookup

    def __getattr__(self, attr):
        if attr not in self.lookup:
            raise AttributeError
        return self.lookup[attr]

    def whatis(self, value):
        return self.reverseLookup[value]


# This function comes from bitcointools, bct-LICENSE.txt.
def long_hex(bytes):
    return bytes.encode('hex_codec')


# This function comes from bitcointools, bct-LICENSE.txt.
def short_hex(bytes):
    t = bytes.encode('hex_codec')
    if len(t) < 11:
        return t
    return t[0:4]+"..."+t[-4:]


def parse_TxIn(vds):
    d = {}
    # TransactionOutpoint parse
    prevout_hash = hash_encode(vds.read_bytes(32))
    prevout_n = vds.read_uint32()

    # TransactionInput parse
    scriptLen = vds.read_compact_size()
    if scriptLen > 0:
        scriptSig = vds.read_bytes(scriptLen)
    else:
        scriptSig = None

    d['scriptSig'] = scriptSig.encode('hex')

    # TODO kMaxSquenceNumber ((0x1ull << 56) - 1)
    #if prevout_n > 0 and prevout_n < 999999:
    sequence = vds.read_uint32()
    #else:
    #    sequence = None

    if prevout_hash == '00'*32:
        d['is_coinbase'] = True
    else:
        d['is_coinbase'] = False
        d['prevout_hash'] = prevout_hash
        d['prevout_n'] = prevout_n
        d['sequence'] = sequence
        d['pubkeys'] = []
        d['signatures'] = {}
        d['address'] = None
        if scriptSig:
            parse_scriptSig(d, scriptSig)

    return d


def parse_TxOut(vds, i):
    d = {}
    d['value'] = vds.read_int64()
    scriptLen = vds.read_compact_size()
    scriptPubKey = vds.read_bytes(scriptLen)
    d['address'] = get_address_from_output_script(scriptPubKey)
    d['raw_output_script'] = scriptPubKey.encode('hex')
    d['index'] = i
    return d


def parse_Transaction(vds, is_coinbase):
    d = {}
    start = vds.read_cursor
    d['version'] = vds.read_int32()
    d['time'] = vds.read_int32()
    n_vin = vds.read_compact_size()
    d['inputs'] = []
    for i in xrange(n_vin):
        o = parse_TxIn(vds)
        if not o['is_coinbase']: # of huidige is_coinbase?
            d['inputs'].append(o)

    n_vout = vds.read_compact_size()
    d['outputs'] = []
    for i in xrange(n_vout):
        o = parse_TxOut(vds, i)
        d['outputs'].append(o)

    d['lockTime'] = vds.read_uint32()
    return d


opcodes = Enumeration("Opcodes", [
    ("OP_0", 0), ("OP_PUSHDATA1", 76), "OP_PUSHDATA2", "OP_PUSHDATA4", "OP_1NEGATE", "OP_RESERVED",
    "OP_1", "OP_2", "OP_3", "OP_4", "OP_5", "OP_6", "OP_7",
    "OP_8", "OP_9", "OP_10", "OP_11", "OP_12", "OP_13", "OP_14", "OP_15", "OP_16",
    "OP_NOP", "OP_VER", "OP_IF", "OP_NOTIF", "OP_VERIF", "OP_VERNOTIF", "OP_ELSE", "OP_ENDIF", "OP_VERIFY",
    "OP_RETURN", "OP_TOALTSTACK", "OP_FROMALTSTACK", "OP_2DROP", "OP_2DUP", "OP_3DUP", "OP_2OVER", "OP_2ROT", "OP_2SWAP",
    "OP_IFDUP", "OP_DEPTH", "OP_DROP", "OP_DUP", "OP_NIP", "OP_OVER", "OP_PICK", "OP_ROLL", "OP_ROT",
    "OP_SWAP", "OP_TUCK", "OP_CAT", "OP_SUBSTR", "OP_LEFT", "OP_RIGHT", "OP_SIZE", "OP_INVERT", "OP_AND",
    "OP_OR", "OP_XOR", "OP_EQUAL", "OP_EQUALVERIFY", "OP_RESERVED1", "OP_RESERVED2", "OP_1ADD", "OP_1SUB", "OP_2MUL",
    "OP_2DIV", "OP_NEGATE", "OP_ABS", "OP_NOT", "OP_0NOTEQUAL", "OP_ADD", "OP_SUB", "OP_MUL", "OP_DIV",
    "OP_MOD", "OP_LSHIFT", "OP_RSHIFT", "OP_BOOLAND", "OP_BOOLOR",
    "OP_NUMEQUAL", "OP_NUMEQUALVERIFY", "OP_NUMNOTEQUAL", "OP_LESSTHAN",
    "OP_GREATERTHAN", "OP_LESSTHANOREQUAL", "OP_GREATERTHANOREQUAL", "OP_MIN", "OP_MAX",
    "OP_WITHIN", "OP_RIPEMD160", "OP_SHA1", "OP_SHA256", "OP_HASH160",
    "OP_HASH256", "OP_CODESEPARATOR", "OP_CHECKSIG", "OP_CHECKSIGVERIFY", "OP_CHECKMULTISIG",
    "OP_CHECKMULTISIGVERIFY",
    "OP_NOP1", "OP_NOP2", "OP_NOP3", "OP_NOP4", "OP_NOP5", "OP_NOP6", "OP_NOP7", "OP_NOP8", "OP_NOP9", "OP_NOP10",
    ("OP_INVALIDOPCODE", 0xFF),
])


def script_GetOp(bytes):
    i = 0
    while i < len(bytes):
        vch = None
        opcode = ord(bytes[i])
        i += 1

        if opcode <= opcodes.OP_PUSHDATA4:
            nSize = opcode
            if opcode == opcodes.OP_PUSHDATA1:
                nSize = ord(bytes[i])
                i += 1
            elif opcode == opcodes.OP_PUSHDATA2:
                (nSize,) = struct.unpack_from('<H', bytes, i)
                i += 2
            elif opcode == opcodes.OP_PUSHDATA4:
                (nSize,) = struct.unpack_from('<I', bytes, i)
                i += 4
            if i+nSize > len(bytes):
              vch = "_INVALID_"+bytes[i:]
              i = len(bytes)
            else:
             vch = bytes[i:i+nSize]
             i += nSize

        yield (opcode, vch, i)


def script_GetOpName(opcode):
  try:
    return (opcodes.whatis(opcode)).replace("OP_", "")
  except KeyError:
    return "InvalidOp_"+str(opcode)


def decode_script(bytes):
    result = ''
    for (opcode, vch, i) in script_GetOp(bytes):
        if len(result) > 0:
            result += " "
        if opcode <= opcodes.OP_PUSHDATA4:
            result += "%d:" % (opcode,)
            result += short_hex(vch)
        else:
            result += script_GetOpName(opcode)
    return result


def match_decoded(decoded, to_match):
    if len(decoded) != len(to_match):
        return False
    for i in range(len(decoded)):
        if to_match[i] == opcodes.OP_PUSHDATA4 and decoded[i][0] <= opcodes.OP_PUSHDATA4:
            continue    # Opcodes below OP_PUSHDATA4 all just push data onto stack, and are equivalent.
        if to_match[i] != decoded[i][0]:
            return False
    return True




def get_address_from_input_script(bytes):
    try:
        decoded = [ x for x in script_GetOp(bytes) ]
    except:
        # coinbase transactions raise an exception
        return [], [], None
    # non-generated TxIn transactions push a signature
    # (seventy-something bytes) and then their public key
    # (33 or 65 bytes) onto the stack:

    match = [ opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4 ]
    if match_decoded(decoded, match):
        return None, None, public_key_to_pubkey_address(decoded[1][1])

    # p2sh transaction, 2 of n
    match = [ opcodes.OP_0 ]
    while len(match) < len(decoded):
        match.append(opcodes.OP_PUSHDATA4)

    if match_decoded(decoded, match):

        redeemScript = decoded[-1][1]
        num = len(match) - 2
        signatures = map(lambda x:x[1].encode('hex'), decoded[1:-1])
        dec2 = [ x for x in script_GetOp(redeemScript) ]

        # 2 of 2
        match2 = [ opcodes.OP_2, opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4, opcodes.OP_2, opcodes.OP_CHECKMULTISIG ]
        if match_decoded(dec2, match2):
            pubkeys = [ dec2[1][1].encode('hex'), dec2[2][1].encode('hex') ]
            return pubkeys, signatures, hash_160_to_script_address(hash_160(redeemScript))

        # 2 of 3
        match2 = [ opcodes.OP_2, opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4, opcodes.OP_3, opcodes.OP_CHECKMULTISIG ]
        if match_decoded(dec2, match2):
            pubkeys = [ dec2[1][1].encode('hex'), dec2[2][1].encode('hex'), dec2[3][1].encode('hex') ]
            return pubkeys, signatures, hash_160_to_script_address(hash_160(redeemScript))

    return [], [], None


def get_address_from_output_script(bytes):
    try:
        decoded = [ x for x in script_GetOp(bytes) ]
    except:
        return None

    # The Genesis Block, self-payments, and pay-by-IP-address payments look like:
    # 65 BYTES:... CHECKSIG
    match = [opcodes.OP_PUSHDATA4, opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return public_key_to_pubkey_address(decoded[0][1])

    # coins sent to black hole
    # DUP HASH160 20 BYTES:... EQUALVERIFY CHECKSIG
    match = [opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_0, opcodes.OP_EQUALVERIFY, opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return None

    # Pay-by-Bitcoin-address TxOuts look like:
    # DUP HASH160 20 BYTES:... EQUALVERIFY CHECKSIG
    match = [opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUALVERIFY, opcodes.OP_CHECKSIG]
    if match_decoded(decoded, match):
        return hash_160_to_pubkey_address(decoded[2][1])

    # strange tx
    match = [opcodes.OP_DUP, opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUALVERIFY, opcodes.OP_CHECKSIG, opcodes.OP_NOP]
    if match_decoded(decoded, match):
        return hash_160_to_pubkey_address(decoded[2][1])

    # p2sh
    match = [ opcodes.OP_HASH160, opcodes.OP_PUSHDATA4, opcodes.OP_EQUAL ]
    if match_decoded(decoded, match):
        addr = hash_160_to_script_address(decoded[1][1])
        return addr

    return None


def parse_scriptSig(d, bytes):
    try:
        decoded = [ x for x in script_GetOp(bytes) ]
    except Exception:
        # coinbase transactions raise an exception
        print_log("cannot find address in input script 1 ", bytes.encode('hex'))
        return

    # payto_pubkey
    match = [ opcodes.OP_PUSHDATA4 ]
    if match_decoded(decoded, match):
        sig = decoded[0][1].encode('hex')
        d['address'] = "(pubkey)"
        d['signatures'] = [sig]
        d['num_sig'] = 1
        d['x_pubkeys'] = ["(pubkey)"]
        d['pubkeys'] = ["(pubkey)"]
        return

    # non-generated TxIn transactions push a signature
    # (seventy-something bytes) and then their public key
    # (65 bytes) onto the stack:
    match = [ opcodes.OP_PUSHDATA4, opcodes.OP_PUSHDATA4 ]
    if match_decoded(decoded, match):
        sig = decoded[0][1].encode('hex')
        x_pubkey = decoded[1][1].encode('hex')
        try:
            signatures = parse_sig([sig])
            pubkey, address = parse_xpub(x_pubkey)
        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            print_log("cannot find address in input script 2 ", bytes.encode('hex'))
            return
        d['signatures'] = signatures
        d['x_pubkeys'] = [x_pubkey]
        d['num_sig'] = 1
        d['pubkeys'] = [pubkey]
        d['address'] = address
        return

    # p2sh transaction, m of n
    match = [ opcodes.OP_0 ] + [ opcodes.OP_PUSHDATA4 ] * (len(decoded) - 1)
    if not match_decoded(decoded, match):
        #print_log("cannot find address in input script 3 ", bytes.encode('hex'), decoded, match)
        return

    x_sig = [x[1].encode('hex') for x in decoded[1:-1]]
    dec2 = [ x for x in script_GetOp(decoded[-1][1]) ]
    m = dec2[0][0] - opcodes.OP_1 + 1
    n = dec2[-2][0] - opcodes.OP_1 + 1
    op_m = opcodes.OP_1 + m - 1
    op_n = opcodes.OP_1 + n - 1
    match_multisig = [ op_m ] + [opcodes.OP_PUSHDATA4]*n + [ op_n, opcodes.OP_CHECKMULTISIG ]

    if not match_decoded(dec2, match_multisig):
        print_log("cannot find address in input script 4", bytes.encode('hex'))
        return
    x_pubkeys = map(lambda x: x[1].encode('hex'), dec2[1:-2])
    pubkeys = [parse_xpub(x)[0] for x in x_pubkeys]     # xpub, addr = parse_xpub()
    redeemScript = Transaction.multisig_script(pubkeys, m)
    # write result in d
    d['num_sig'] = m
    d['signatures'] = parse_sig(x_sig)
    d['x_pubkeys'] = x_pubkeys
    d['pubkeys'] = pubkeys
    d['redeemScript'] = redeemScript
    d['address'] = hash_160_to_bc_address(hash_160(redeemScript.decode('hex')), bitcoin.SCRIPT_ADDR)




def parse_sig(x_sig):
    s = []
    for sig in x_sig:
        if sig[-2:] == '01':
            s.append(sig[:-2])
        else:
            assert sig == NO_SIGNATURE
            s.append(None)
    return s

def is_extended_pubkey(x_pubkey):
    return x_pubkey[0:2] in ['fe', 'ff']

def x_to_xpub(x_pubkey):
    if x_pubkey[0:2] == 'ff':
        from account import BIP32_Account
        xpub, s = BIP32_Account.parse_xpubkey(x_pubkey)
        return xpub


def parse_xpub(x_pubkey):
    if x_pubkey[0:2] in ['02','03','04']:
        pubkey = x_pubkey
    elif x_pubkey[0:2] == 'ff':
        from account import BIP32_Account
        xpub, s = BIP32_Account.parse_xpubkey(x_pubkey)
        pubkey = BIP32_Account.derive_pubkey_from_xpub(xpub, s[0], s[1])
    elif x_pubkey[0:2] == 'fe':
        from account import OldAccount
        mpk, s = OldAccount.parse_xpubkey(x_pubkey)
        pubkey = OldAccount.get_pubkey_from_mpk(mpk.decode('hex'), s[0], s[1])
    elif x_pubkey[0:2] == 'fd':
        addrtype = ord(x_pubkey[2:4].decode('hex'))
        hash160 = x_pubkey[4:].decode('hex')
        pubkey = None
        address = hash_160_to_bc_address(hash160, addrtype)
    else:
        raise BaseException("Cannnot parse pubkey")
    if pubkey:
        address = public_key_to_bc_address(pubkey.decode('hex'))
    return pubkey, address

