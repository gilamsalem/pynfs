#
# environment.py
#
# Requires python 2.3
# 
# Written by Fred Isaman <iisaman@citi.umich.edu>
# Copyright (C) 2004 University of Michigan, Center for 
#                    Information Technology Integration
#

import time
import testmod
from nfs4_const import *
from nfs4_type import *
import rpc
import nfs4client
import os
import nfs4lib
from nfs4lib import use_obj
import logging
import struct
from rpc.security import AuthSys, AuthGss
from threading import Lock
import nfs4_ops as op

log = logging.getLogger("test.env")

class AttrInfo(object):
    def __init__(self, name, access, sample):
        self.name = name
        self.bitnum = nfs4lib.attr2bitnum[name]
        self.mask = 2**self.bitnum
        self.access = access
        self.sample = sample

    def __str__(self):
        return '%s %i %s' % (self.name, self.bitnum, self.access)

    writable = property(lambda self: 'w' in self.access)
    readable = property(lambda self: 'r' in self.access)
    mandatory = property(lambda self: 'm' in self.access)
    readonly = property(lambda self: \
                         'r' in self.access and 'w' not in self.access)
    writeonly = property(lambda self: \
                         'w' in self.access and 'r' not in self.access)

class Environment(testmod.Environment):
    # STUB
    attr_info = [ \
        AttrInfo('supported_attrs', 'rm', []),
        AttrInfo('type', 'rm', 1),
        AttrInfo('fh_expire_type', 'rm', 0),
        AttrInfo('change', 'rm', 0),
        AttrInfo('size', 'rwm', 0),
        AttrInfo('link_support', 'rm', False),
        AttrInfo('symlink_support', 'rm', False),
        AttrInfo('named_attr', 'rm', False),
        AttrInfo('fsid', 'rm', fsid4(0, 0)),
        AttrInfo('unique_handles', 'rm', False),
        AttrInfo('lease_time', 'rm', 0),
        AttrInfo('rdattr_error', 'rm', 0),
        AttrInfo('filehandle', 'rm', 'nonsense'),
        AttrInfo('acl', 'rw', [nfsace4(0,0,0,'EVERYONE@')]),
        AttrInfo('aclsupport', 'r', 0),
        AttrInfo('archive', 'rw', False),
        AttrInfo('cansettime', 'r', False),
        AttrInfo('case_insensitive', 'r', False),
        AttrInfo('case_preserving', 'r', False),
        AttrInfo('chown_restricted', 'r', False),
        AttrInfo('fileid', 'r', 0),
        AttrInfo('files_avail', 'r', 0),
        AttrInfo('files_free', 'r', 0),
        AttrInfo('files_total', 'r', 0),
        # FRED - packer did not complain about missing [] about server
        AttrInfo('fs_locations', 'r',
                 fs_locations4('root',[fs_location4(['server'],'path')])),
        AttrInfo('hidden', 'rw', False),
        AttrInfo('homogeneous', 'r', False),
        AttrInfo('maxfilesize', 'r', 0),
        AttrInfo('maxlink', 'r', 0),
        AttrInfo('maxname', 'r', 0),
        AttrInfo('maxread', 'r', 0),
        AttrInfo('maxwrite', 'r', 0),
        AttrInfo('mimetype', 'rw', 'nonsense'),
        AttrInfo('mode', 'rw', 0),
        AttrInfo('no_trunc', 'r', False),
        AttrInfo('numlinks', 'r', 0),
        AttrInfo('owner', 'rw', 'nonsense'),
        AttrInfo('owner_group', 'rw', 'nonsense'),
        AttrInfo('quota_avail_hard', 'r', 0),
        AttrInfo('quota_avail_soft', 'r', 0),
        AttrInfo('quota_used', 'r', 0),
        AttrInfo('rawdev', 'r', specdata4(0, 0)),
        AttrInfo('space_avail', 'r', 0),
        AttrInfo('space_free', 'r', 0),
        AttrInfo('space_total', 'r', 0),
        AttrInfo('space_used', 'r', 0),
        AttrInfo('system', 'rw', False),
        AttrInfo('time_access', 'r', nfstime4(0, 0)),
        AttrInfo('time_access_set', 'w', settime4(0)),
        AttrInfo('time_backup', 'rw', nfstime4(0, 0)),
        AttrInfo('time_create', 'rw', nfstime4(0, 0)),
        AttrInfo('time_delta', 'r', nfstime4(0, 0)),
        AttrInfo('time_metadata', 'r', nfstime4(0, 0)),
        AttrInfo('time_modify', 'r', nfstime4(0, 0)),
        AttrInfo('time_modify_set', 'w', settime4(0)),
        AttrInfo('mounted_on_fileid', 'r', 0),
        ]

    home = property(lambda s: use_obj(s.opts.home))

    def __init__(self, opts):
        self._lock = Lock()
        self.opts = opts
        self.c1 = nfs4client.NFS4Client(opts.server, opts.port)
        s1 = rpc.security.instance(opts.flavor)
        if opts.flavor == rpc.AUTH_NONE:
            self.cred1 = s1.init_cred()
        elif opts.flavor == rpc.AUTH_SYS:
            self.cred1 = s1.init_cred(uid=4321, gid=42, name="mystery")
        elif opts.flavor == rpc.RPCSEC_GSS:
            call = self.c1.make_call_function(self.c1.c1, 0,
                                              self.c1.default_prog,
                                              self.c1.default_vers)
            krb5_cred = AuthGss().init_cred(call, target="nfs@%s" % opts.server)
            krb5_cred.service = opts.service
            self.cred1 = krb5_cred
        self.c1.set_cred(self.cred1)
        self.cred2 = AuthSys().init_cred(uid=1111, gid=37, name="shampoo")

        opts.home = opts.path + ['tmp']
        self.c1.homedir = opts.home
        # Put this after client creation, to ensure _last_verf bigger than
        # any natural client verifiers
        self.timestamp = int(time.time())
        self._last_verf = self.timestamp + 1
        self.filedata = "This is the file test data."
        self.linkdata = "/etc/X11"
        
        log.info("Created client to %s, %i" % (opts.server, opts.port))

    def init(self):
        """Run once before any test is run"""
        if self.opts.noinit:
            return
        c = self.c1.new_client("Environment.init_%i" % self.timestamp)
        sess = c.create_session()
        if self.opts.maketree:
            self._maketree(sess)
        # Make sure opts.home exists
        res = sess.compound(use_obj(self.opts.home))
        check(res, msg="Could not LOOKUP /%s," % '/'.join(self.opts.home))
        # Make sure it is empty
        clean_dir(sess, self.opts.home)
        sess.c.null()

    def _maketree(self, sess):
        """Make test tree"""
        # ensure /tmp (and path leading up) exists
        path = []
        for comp in self.opts.home:
            path.append(comp)
            res = sess.compound(use_obj(path))
            checklist(res, [NFS4_OK, NFS4ERR_NOENT],
                      "LOOKUP /%s," % '/'.join(path))
            if res.status == NFS4ERR_NOENT:
                res = create_obj(sess, path, NF4DIR)
                check(res, msg="Trying to create /%s," % '/'.join(path))
        # ensure /tree exists and is empty
        tree = self.opts.path + ['tree']
        res = sess.compound(use_obj(tree))
        checklist(res, [NFS4_OK, NFS4ERR_NOENT])
        if res.status == NFS4ERR_NOENT:
            res = create_obj(sess, tree, NF4DIR)
            check(res, msg="Trying to create /%s," % '/'.join(tree))
        else:
            clean_dir(sess, tree)

        # make non-file objects in /tree
        d = {'dir': NF4DIR,
             'socket': NF4SOCK,
             'fifo':  NF4FIFO,
             'link':  createtype4(NF4LNK, linkdata=self.linkdata),
             'block': createtype4(NF4BLK, devdata=specdata4(1, 2)),
             'char': createtype4(NF4CHR, devdata=specdata4(1, 2)),
             }
        for name, kind in d.items():
            path = tree + [name]
            res = create_obj(sess, path, kind)
            if res.status != NFS4_OK:
                log.warning("could not create /%s" % '/'.join(path))
        # Make file-object in /tree
        fh, stateid = create_confirm(sess, 'maketree', tree + ['file'])
        stateid.seqid = 0
        ops = [op.putfh(fh),
               op.write(stateid, 0, FILE_SYNC4, self.filedata)]
        res = sess.compound(ops)
        check(res, msg="Writing data to /%s/file" % '/'.join(tree))
        res = close_file(sess, fh, stateid)
        check(res)
            
    def finish(self):
        """Run once after all tests are run"""
        pass

    def startUp(self):
        """Run before each test"""
        log.debug("Sending pretest NULL")
        self.c1.null()
        log.debug("Got pretest NULL response")

    def sleep(self, sec, msg=''):
        """Sleep for given seconds"""
        log.info("Sleeping for %i seconds: %s" % (sec, msg))
        time.sleep(sec)
        log.info("Woke up")

    def new_verifier(self):
        """Returns a never before used verifier"""
        candidate = int(time.time())
        self._lock.acquire()
        try:
            if candidate <= self._last_verf:
                candidate = self._last_verf + 1
            self._last_verf = candidate
        finally:
            self._lock.release()
        return struct.pack('>d', candidate)

    def testname(self, t):
        """Returns a name for the test that is unique between runs"""
        return "%s_%i" % (t.code, self.timestamp)
    
#########################################
debug_fail = False

def fail(msg):
    raise testmod.FailureException(msg)

def check(res, stat=NFS4_OK, msg=None, warnlist=[]):
    #if res.status == stat:
    #    return
    if type(stat) is str:
        raise "You forgot to put 'msg=' in front of check's string arg"
    log.debug("checking %r == %r" % (res, stat))
    if res.status == stat:
        if not (debug_fail and msg):
            return
    desired = nfsstat4[stat]
    received = nfsstat4[res.status]
    if msg:
        failedop_name = msg
    elif res.resarray:
        failedop_name = nfs_opnum4[res.resarray[-1].resop]
    else:
        failedop_name = 'Compound'
    msg = "%s should return %s, instead got %s" % \
          (failedop_name, desired, received)
    if res.status in warnlist:
        raise testmod.WarningException(msg)
    else:
        raise testmod.FailureException(msg)

def checklist(res, statlist, msg=None):
    if res.status in statlist:
        return
    statnames = [nfsstat4[stat] for stat in statlist]
    desired = ' or '.join(statnames)
    if not desired:
        desired = 'one of <none>'
    received = nfsstat4[res.status]
    if msg:
        failedop_name = msg
    elif res.resarray:
        failedop_name = nfs_opnum4[res.resarray[-1].resop]
    else:
        failedop_name = 'Compound'
    msg = "%s should return %s, instead got %s" % \
          (failedop_name, desired, received)
    raise testmod.FailureException(msg)

def checkdict(expected, got, translate={}, failmsg=''):
    if failmsg: failmsg += ': '
    for k in expected:
        if k not in got:
            try:
                name = translate[k]
            except KeyError:
                name = str(k)
            raise testmod.FailureException(failmsg +
                          "For %s expected %s, but no value returned" %
                          (name, str(expected[k])))
        if expected[k] != got[k]:
            try:
                name = translate[k]
            except KeyError:
                name = str(k)
            raise testmod.FailureException(failmsg +
                          "For %s expected %s, got %s" %
                          (name, str(expected[k]), str(got[k])))

def get_invalid_utf8strings():
    """Return a list of invalid ISO10646-UTF-8 strings"""
    # FIXME: More invalid strings.
    return ["\xc0\xc1", # starts two multibyte sequences
            "\xe0\x8a", # terminates a multibyte sequence too early
            "\xc0\xaf", # overlong character"
            "\xfc\x80\x80\x80\x80\xaf", # overlong character
            "\xfc\x80\x80\x80\x80\x80", # NULL
            "\xed\xa0\x80", # UTF-16 surrogate
            "\xed\xbf\xbf", # UTF-16 surrogate
            "\xef\xbf\xbe", # Invalid character U+FFFE
            "\xe3\xc0\xc0", # just mangled.
            "\xc0\x90", # overlong character
            # byte sequences that should never appear at start
            "\x80",
            "\xbf",
            "\xfe",
            "\xff",
            # starts with no ends
            "\xc0 ",
            "\xdf ",
            "\xe0 ",
            "\xef ",
            "\xf0 ",
            "\xf7 ",
            "\xf8 ",
            "\xfb ",
            "\xfc ",
            "\xfd "
            ]

def get_invalid_clientid():
    """Return a (guessed) invalid clientid"""
    return 0

def makeStaleId(stateid):
    """Given a good stateid, makes it stale

    NOTE this looks into server opaque data, thus is very specific
    to the CITI linux server.  All tests which use this function have
    the flag 'staleid'
    """
    boottime = stateid.other[0:4]
    if ord(boottime[0]):
        staletime = "\0" + boottime[1:4]
    else:
        staletime = "a" + boottime[1:4]
    stale = stateid4(stateid.seqid , staletime+"\0\0\0\0\0\0\0\0")
    return stale

def makeBadID(stateid):
    """Given a good stateid, makes it bad

    NOTE this looks into server opaque data, thus is very specific
    to the CITI linux server.  All tests which use this function have
    the flag 'badid'
    """

    boottime = stateid.other[0:4]
    bad = stateid4(stateid.seqid , boottime+"\0\0\0\0\0\0\0\0")
    return bad

def compareTimes(time1, time2):
    """Compares nfstime4 values

    Returns -1 if time1 < time2
             0 if time1 ==time2
             1 if time1 > time2
    """

    if time1.seconds < time2.seconds:
        return -1
    elif time1.seconds > time2.seconds:
        return 1
    else: # time1.seconds == time2.seconds:
        if time1.nseconds < time2.nseconds:
            return -1
        elif time1.nseconds > time2.nseconds:
            return 1
        else:
            return 0

#############################################

# Of course, there is no guarantee that this is not a valid session id, but...
bad_sessionid = "Bad Session Id"



def clean_dir(sess, path):
    stateid = nfs4lib.state00
    # fh = self.do_getfh(path)
    entries = do_readdir(sess, path)
    for e in entries:
        # We separate setattr and remove to avoid an inode locking bug
        ops = use_obj(path + [e.name])
        ops += [op.setattr(stateid, {FATTR4_MODE:0755})]
        res = sess.compound(ops)
        check(res, msg="Setting mode on %s" % repr(e.name))
        ops = use_obj(path)
        ops += [op.remove(e.name)]
        res = sess.compound(ops)
        if res.status == NFS4ERR_NOTEMPTY:
            clean_dir(sess, path + [e.name])
            res = sess.compound(ops)
        check(res, msg="Trying to remove %s" % repr(e.name))

def do_readdir(sess, file, cookie=0, cookieverf='', attrs=0L,
               dircount=4096, maxcount=4096):
    # Since we may not get whole directory listing in one readdir request,
    # loop until we do. For each request result, create a flat list
    # with <entry4> objects.
    log.info("Called do_readdir()")
    entries = []
    baseops = use_obj(file)
    while True:
        readdir_op = op.readdir(cookie, cookieverf, dircount, maxcount, attrs)
        res = sess.compound(baseops + [readdir_op])
        check(res, msg="READDIR with cookie=%i, maxcount=%i" % (cookie, maxcount))
        reply = res.resarray[-1].reply
        if not reply.entries and not reply.eof:
            raise UnexpectedCompoundRes("READDIR had no entries")
        entries.extend(reply.entries)
        if reply.eof:
            break
        cookie = entries[-1].cookie
        cookieverf = res.resarray[-1].cookieverf
    log.info("do_readdir() = %r" % entries)
    return entries

def do_getattrdict(sess, file, attrlist):
    """file can be either a fh or a path"""
    ops = use_obj(file)
    ops += [op.getattr(nfs4lib.list2bitmap(attrlist))]
    res = sess.compound(ops)
    check(res)
    return res.resarray[-1].obj_attributes

def create_obj(sess, path, kind=NF4DIR, attrs={FATTR4_MODE:0755}):
    """Return ops needed to create given non-file object"""
    # Ensure using createtype4
    if not hasattr(kind, "type"):
        kind = createtype4(kind)
    ops = use_obj(path[:-1]) + [op.create(kind, path[-1], attrs)]
    return sess.compound(ops)

def create_file(sess, owner, path=None, attrs={FATTR4_MODE: 0644},
                access=OPEN4_SHARE_ACCESS_BOTH,
                deny=OPEN4_SHARE_DENY_NONE,
                mode=GUARDED4, verifier=None, want_deleg=False,
                # Setting the following should induce server errors
                seqid=0, clientid=0):
    # Set defaults
    if path is None:
        dir = sess.c.homedir
        name = owner
    else:
        dir = path[:-1]
        name = path[-1]
    if (mode==EXCLUSIVE4) and (verifier==None):
        verifier = sess.c.verifier
    if not want_deleg and access & OPEN4_SHARE_ACCESS_WANT_DELEG_MASK == 0:
        access |= OPEN4_SHARE_ACCESS_WANT_NO_DELEG
    # Create the file
    open_op = op.open(seqid, access, deny, open_owner4(clientid, owner),
                      openflag4(OPEN4_CREATE, createhow4(mode, attrs, verifier)),
                      open_claim4(CLAIM_NULL, name))
    return sess.compound(use_obj(dir) + [open_op, op.getfh()])

def open_file(sess, owner, path=None,
              access=OPEN4_SHARE_ACCESS_READ,
              deny=OPEN4_SHARE_DENY_NONE,
              want_deleg=False,
              # Setting the following should induce server errors
              seqid=0, clientid=0):
    # Set defaults
    if path is None:
        dir = sess.c.homedir
        name = owner
    else:
        dir = path[:-1]
        name = path[-1]
    if not want_deleg and access & OPEN4_SHARE_ACCESS_WANT_DELEG_MASK == 0:
        access |= OPEN4_SHARE_ACCESS_WANT_NO_DELEG
    # Open the file
    open_op = op.open(seqid, access, deny, open_owner4(clientid, owner),
                      openflag4(OPEN4_NOCREATE),
                      open_claim4(CLAIM_NULL, name))
    return sess.compound(use_obj(dir) + [open_op, op.getfh()])

def create_confirm(sess, owner, path=None, attrs={FATTR4_MODE: 0644},
                   access=OPEN4_SHARE_ACCESS_BOTH,
                   deny=OPEN4_SHARE_DENY_NONE,
                   mode=GUARDED4):
    """Create (using open) a regular file, and confirm the open

    Returns the fhandle and stateid from the confirm.
    """
    res = create_file(sess, owner, path, attrs, access, deny, mode)
    check(res, msg="Creating file %s" % _getname(owner, path))
    fh = res.resarray[-1].object
    openstateid = stateid4(0, res.resarray[-2].stateid.other)
    return fh, res.resarray[-2].stateid
    return fh, openstateid

def _getname(owner, path):
    if path is None:
        return owner
    else:
        return path[-1]

def close_file(sess, fh, stateid, seqid=0):
    """close the given file"""
    if fh is None:
        ops = []
    else:
        ops = [op.putfh(fh)]
    ops += [op.close(seqid, stateid)]
    res = sess.compound(ops)
    return res

def maketree(sess, tree, root=None, owner=None):
    if owner is None:
        owner = tree[0]
        if type(owner) is list:
            owner = owner[0]
    if root is None:
        root = sess.c.homedir
        tree = [tree]
    for obj in tree:
        if type(obj) is list:
            res = create_obj(sess, root + [obj[0]])
            check(res)
            maketree(sess, obj[1:], root + [obj[0]], owner)
        else:
            create_confirm(sess, owner, root + [obj])

def rename_obj(sess, oldpath, newpath):
    # Set (sfh) to olddir
    ops = use_obj(oldpath[:-1]) + [op.savefh()]
    # Set (cfh) to newdir
    ops += use_obj(newpath[:-1])
    # Call rename
    ops += [op.rename(oldpath[-1], newpath[-1])]
    return sess.compound(ops)

def link(sess, old, new):
    ops = use_obj(old) + [op.savefh()]
    ops += use_obj(new[:-1])
    ops += [op.link(new[-1])]
    return sess.compound(ops)