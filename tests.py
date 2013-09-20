import anyvcs
import datetime
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from abc import ABCMeta, abstractmethod
from anyvcs import UnknownVCSType, PathDoesNotExist, BadFileType
from anyvcs.common import CommitLogEntry, UTCOffset

if False:
  import sys
  logfile = sys.stdout
else:
  logfile = open(os.devnull, 'w')
date_rx = re.compile(r'^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?:\s+|T)(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})(?:\.(?P<us>\d{6}))?(?:Z|\s+(?P<tz>[+-]?\d{4}))$')

UTC = UTCOffset(0, 'UTC')

def check_call(args, **kwargs):
  logfile.write('%s\n' % repr(args))
  kwargs.setdefault('stdout', logfile)
  kwargs.setdefault('stderr', logfile)
  subprocess.check_call(args, **kwargs)

def check_output(args, **kwargs):
  logfile.write('%s\n' % repr(args))
  kwargs.setdefault('stderr', logfile)
  return subprocess.check_output(args, **kwargs)

def normalize_ls(x):
  return sorted(x, key=lambda y: y.get('name'))

def normalize_heads(x):
  return sorted(x)

def normalize_datetime(x):
  return x.astimezone(UTC).replace(microsecond=0)

def normalize_logmsg(x):
  return x.rstrip()

def parse_date(x):
  m = date_rx.match(x)
  if m is None:
    return None
  d = datetime.datetime(*[int(x) for x in m.group('year', 'month', 'day', 'hour', 'minute', 'second')])
  if m.group('us'):
    d = d.replace(microsecond=int(m.group('us')))
  tz = m.group('tz')
  if tz:
    offset = datetime.timedelta(minutes=int(tz[-2:]), hours=int(tz[-4:-2]))
    if tz[0] == '-':
      offset = -offset
  else:
    offset = 0
  d = d.replace(tzinfo=UTCOffset(offset))
  return d


### VCS FRAMEWORK CLASSES ###

class VCSTest(unittest.TestCase):
  __metaclass__ = ABCMeta

  @classmethod
  def setUpClass(cls):
    cls.dir = tempfile.mkdtemp(prefix='anyvcs-test.')
    cls.main_path = os.path.join(cls.dir, 'main')
    cls.working_path = os.path.join(cls.dir, 'work')
    cls.working_head = None
    cls.setUpRepos()

  @classmethod
  def setUpRepos(cls):
    raise NotImplementedError

  @classmethod
  def getAbsoluteRev(cls):
    raise NotImplementedError

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls.dir)

  @classmethod
  def check_call(cls, *args, **kwargs):
    kwargs.setdefault('cwd', cls.working_path)
    check_call(*args, **kwargs)

  @classmethod
  def check_output(cls, *args, **kwargs):
    kwargs.setdefault('cwd', cls.working_path)
    return check_output(*args, **kwargs)

  @classmethod
  def encode_branch(cls, s):
    return s

  @classmethod
  def decode_branch(cls, s):
    return s

  @classmethod
  def encode_tag(cls, s):
    return s

  @classmethod
  def decode_tag(cls, s):
    return s

  def assertCommitLogEqual(self, a, b):
    self.assertEqual(a.rev, b.rev)
    self.assertEqual(a.parents, b.parents)
    self.assertEqual(normalize_datetime(a.date), normalize_datetime(b.date), '%s != %s' % (a.date, b.date))
    self.assertEqual(a.author, b.author)
    self.assertEqual(a.subject, b.subject)

class GitTest(VCSTest):
  @classmethod
  def setUpRepos(cls):
    cls.repo = anyvcs.create(cls.main_path, 'git')
    check_call(['git', 'clone', cls.main_path, cls.working_path])
    cls.main_branch = 'master'
    cls.working_head = 'master'
    for action in cls.setUpWorkingCopy(cls.working_path):
      action.doGit(cls)

  @classmethod
  def getAbsoluteRev(cls):
    return cls.check_output(['git', 'log', '-1', '--pretty=format:%H'])

class HgTest(VCSTest):
  @classmethod
  def setUpRepos(cls):
    cls.repo = anyvcs.create(cls.main_path, 'hg')
    check_call(['hg', 'clone', cls.main_path, cls.working_path])
    cls.main_branch = 'default'
    cls.working_head = 'default'
    for action in cls.setUpWorkingCopy(cls.working_path):
      action.doHg(cls)

  @classmethod
  def getAbsoluteRev(cls):
    return cls.check_output(['hg', 'log', '-l1', '--template={node}'])

class SvnTest(VCSTest):
  @classmethod
  def setUpRepos(cls):
    cls.repo = anyvcs.create(cls.main_path, 'svn')
    check_call(['svn', 'checkout', 'file://' + cls.main_path, cls.working_path])
    cls.main_branch = 'HEAD'
    cls.working_head = 'HEAD'
    for action in cls.setUpWorkingCopy(cls.working_path):
      action.doSvn(cls)

  @classmethod
  def getAbsoluteRev(cls):
    xml = cls.check_output(['svn', 'info', '--xml'])
    tree = ET.fromstring(xml)
    rev = tree.find('entry').attrib.get('revision')
    if cls.working_head == 'HEAD':
      return int(rev)
    else:
      return '/%s:%s' % (cls.encode_branch(cls.working_head), rev)

  @classmethod
  def encode_branch(cls, s):
    if s == 'trunk':
      return s
    return 'branches/' + s

  @classmethod
  def decode_branch(cls, s):
    if s == 'trunk':
      return s
    assert s.startswith('branches/')
    return s[9:]

  @classmethod
  def encode_tag(cls, s):
    return 'tags/' + s

  @classmethod
  def decode_tag(cls, s):
    assert s.startswith('tags/')
    return s[5:]


class Action(object):
  __metaclass__ = ABCMeta

  @abstractmethod
  def doGit(self, test):
    raise NotImplementedError

  @abstractmethod
  def doHg(self, test):
    raise NotImplementedError

  @abstractmethod
  def doSvn(self, test):
    raise NotImplementedError

class CreateStandardDirectoryStructure(Action):
  """Create the standard directory structure, if any"""

  def doGit(self, test):
    pass

  def doHg(self, test):
    pass

  def doSvn(self, test):
    test.check_call(['svn', 'mkdir', 'trunk', 'branches', 'tags'])
    commit = Commit('create standard directory structure')
    commit.doSvn(test)
    test.check_call(['svn', 'switch', 'file://'+test.main_path+'/trunk'])
    test.main_branch = 'trunk'
    test.working_head = 'trunk'

class Commit(Action):
  """Commit and push"""

  def __init__(self, message):
    self.message = message

  def doGit(self, test):
    test.check_call(['git', 'add', '-A', '.'])
    test.check_call(['git', 'commit', '-m', self.message])
    test.check_call(['git', 'push', '--set-upstream', 'origin', test.working_head])

  def doHg(self, test):
    test.check_call(['hg', 'addremove'])
    test.check_call(['hg', 'commit', '-m', self.message])
    test.check_call(['hg', 'push', '--new-branch', '-b', test.working_head])

  def doSvn(self, test):
    xml = test.check_output(['svn', 'status', '--xml'])
    tree = ET.fromstring(xml)
    for entry in tree.iter('entry'):
      test.check_call(['svn', 'add', '-q', entry.attrib.get('path')])
    test.check_call(['svn', 'commit', '-m', self.message])
    test.check_call(['svn', 'update'])

class BranchAction(Action):
  def __init__(self, name):
    self.name = name

class CreateBranch(BranchAction):
  """Create a new branch based on the current branch and switch to it"""

  def doGit(self, test):
    test.check_call(['git', 'checkout', '-b', self.name])
    test.working_head = self.name

  def doHg(self, test):
    test.check_call(['hg', 'branch', self.name])
    test.working_head = self.name

  def doSvn(self, test):
    xml = test.check_output(['svn', 'info', '--xml'])
    tree = ET.fromstring(xml)
    url1 = tree.find('entry').find('url').text
    url2 = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'copy', url1, url2, '-m', 'create branch ' + self.name])
    test.check_call(['svn', 'switch', url2])
    test.working_head = self.name

class CreateUnrelatedBranch(BranchAction):
  """Create a new branch unrelated to any other branch and switch to it"""

  def doGit(self, test):
    test.check_call(['git', 'checkout', '--orphan', self.name])
    test.check_call(['git', 'rm', '-rf', '.'])
    test.working_head = self.name

  def doHg(self, test):
    test.check_call(['hg', 'update', 'null'])
    test.check_call(['hg', 'branch', self.name])
    test.working_head = self.name

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'mkdir', url, '-m', 'create branch ' + self.name])
    test.check_call(['svn', 'switch', url])
    test.working_head = self.name

class DeleteBranch(BranchAction):
  """Delete/close a branch and push"""

  def doGit(self, test):
    test.check_call(['git', 'branch', '-d', self.name])
    test.check_call(['git', 'push', 'origin', ':' + self.name])

  def doHg(self, test):
    test.check_call(['hg', 'update', self.name])
    test.check_call(['hg', 'commit', '--close-branch', '-m', 'close branch ' + self.name])
    test.check_call(['hg', 'push'])
    test.check_call(['hg', 'update', test.working_head])

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'delete', url, '-m', 'delete branch ' + self.name])

class SwitchBranch(BranchAction):
  """Switch working copy to another branch"""

  def doGit(self, test):
    test.check_call(['git', 'checkout', self.name])
    test.working_head = self.name

  def doHg(self, test):
    test.check_call(['hg', 'update', self.name])
    test.working_head = self.name

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'switch', url])
    test.working_head = self.name

class Merge(BranchAction):
  """Merge and push"""

  def doGit(self, test):
    test.check_call(['git', 'merge', '--no-ff', self.name])
    test.check_call(['git', 'push', 'origin', test.working_head])

  def doHg(self, test):
    test.check_call(['hg', 'merge', self.name])
    test.check_call(['hg', 'commit', '-m', 'merge from %s to %s' % (self.name, test.working_head)])
    test.check_call(['hg', 'push'])

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'merge', url])
    test.check_call(['svn', 'commit', '-m', 'merge from %s to %s' % (self.name, test.working_head)])

class ReintegrateMerge(Merge):
  """Merge and push"""

  def doSvn(self, test):
    url = 'file://' + test.main_path + '/' + test.encode_branch(self.name)
    test.check_call(['svn', 'merge', '--reintegrate', url])
    test.check_call(['svn', 'commit', '-m', 'reintegrate merge from %s to %s' % (self.name, test.working_head)])

class CreateTag(Action):
  """Create tag and push"""

  def __init__(self, name):
    self.name = name

  def doGit(self, test):
    test.check_call(['git', 'tag', self.name, '-m', 'create tag ' + self.name])
    test.check_call(['git', 'push', 'origin', self.name])

  def doHg(self, test):
    test.check_call(['hg', 'tag', self.name, '-m', 'create tag ' + self.name])
    test.check_call(['hg', 'push'])

  def doSvn(self, test):
    xml = test.check_output(['svn', 'info', '--xml'])
    tree = ET.fromstring(xml)
    url1 = tree.find('entry').find('url').text
    url2 = 'file://' + test.main_path + '/' + test.encode_tag(self.name)
    test.check_call(['svn', 'copy', url1, url2, '-m', 'create tag ' + self.name])


### TEST CASE: EmptyTest ###

class EmptyTest(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    return
    yield

  def test_empty(self):
    result = self.repo.empty()
    correct = True
    self.assertEqual(result, correct)

class GitEmptyTest(GitTest, EmptyTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log(self):
    result = self.repo.log()
    self.assertEqual(len(result), 0)

class HgEmptyTest(HgTest, EmptyTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = ['tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_bookmarks(self):
    result = self.repo.bookmarks()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log(self):
    result = self.repo.log()
    self.assertEqual(len(result), 0)

class SvnEmptyTest(SvnTest, EmptyTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['HEAD']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log(self):
    result = self.repo.log()
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0].rev, 0)


### TEST CASE: BasicTest ###

class BasicTest(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    with open(os.path.join(working_path, 'a'), 'w') as f:
      f.write('Pisgah')
    os.chmod(os.path.join(working_path, 'a'), 0644)
    os.symlink('a', os.path.join(working_path, 'b'))
    os.mkdir(os.path.join(working_path, 'c'))
    os.mkdir(os.path.join(working_path, 'c', 'd'))
    with open(os.path.join(working_path, 'c', 'd', 'e'), 'w') as f:
      f.write('Denali')
    os.chmod(os.path.join(working_path, 'c', 'd', 'e'), 0755)
    os.symlink('e', os.path.join(working_path, 'c', 'd', 'f'))
    yield Commit('commit 1')
    cls.rev1 = cls.getAbsoluteRev()

  def test_empty(self):
    result = self.repo.empty()
    correct = False
    self.assertEqual(result, correct)

  def test_ls1(self):
    result = self.repo.ls(self.main_branch, '')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls2(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls3(self):
    result = self.repo.ls(self.main_branch, '/a')
    correct = [{'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls4(self):
    result = self.repo.ls(self.main_branch, '/b')
    correct = [{'type':'l'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls5(self):
    result = self.repo.ls(self.main_branch, '/c')
    correct = [
      {'name':'d', 'type':'d'}
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls6(self):
    result = self.repo.ls(self.main_branch, '/c/')
    correct = [
      {'name':'d', 'type':'d'}
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls7(self):
    result = self.repo.ls(self.main_branch, '/c', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls8(self):
    result = self.repo.ls(self.main_branch, '/c/', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls9(self):
    result = self.repo.ls(self.main_branch, '/', directory=True)
    correct = [{'type':'d'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls10(self):
    result = self.repo.ls(self.main_branch, '/a', directory=True)
    correct = [{'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.ls, self.main_branch, '/z')

  def test_ls_error2(self):
    self.assertRaises(PathDoesNotExist, self.repo.ls, self.main_branch, '/a/')

  def test_ls_recursive(self):
    result = self.repo.ls(self.main_branch, '/', recursive=True)
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c/d/e', 'type':'f'},
      {'name':'c/d/f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_recursive_dirs(self):
    result = self.repo.ls(self.main_branch, '/', recursive=True, recursive_dirs=True)
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
      {'name':'c/d', 'type':'d'},
      {'name':'c/d/e', 'type':'f'},
      {'name':'c/d/f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_size(self):
    result = self.repo.ls(self.main_branch, '/', report=('size',))
    correct = [
      {'name':'a', 'type':'f', 'size':6},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_target(self):
    result = self.repo.ls(self.main_branch, '/', report=('target',))
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'l', 'target':'a'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_executable1(self):
    result = self.repo.ls(self.main_branch, '/', report=('executable',))
    correct = [
      {'name':'a', 'type':'f', 'executable':False},
      {'name':'b', 'type':'l'},
      {'name':'c', 'type':'d'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_ls_report_executable2(self):
    result = self.repo.ls(self.main_branch, '/c/d', report=('executable',))
    correct = [
      {'name':'e', 'type':'f', 'executable':True},
      {'name':'f', 'type':'l'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_cat1(self):
    result = self.repo.cat(self.main_branch, 'a')
    correct = 'Pisgah'
    self.assertEqual(result, correct)

  def test_cat2(self):
    result = self.repo.cat(self.main_branch, '/a')
    correct = 'Pisgah'
    self.assertEqual(result, correct)

  def test_cat3(self):
    result = self.repo.cat(self.main_branch, 'c/d/e')
    correct = 'Denali'
    self.assertEqual(result, correct)

  def test_cat4(self):
    result = self.repo.cat(self.main_branch, '/c/d/e')
    correct = 'Denali'
    self.assertEqual(result, correct)

  def test_cat_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.cat, self.main_branch, '/z')

  def test_cat_error2(self):
    self.assertRaises(PathDoesNotExist, self.repo.cat, self.main_branch, '/a/')

  def test_cat_error3(self):
    self.assertRaises(BadFileType, self.repo.cat, self.main_branch, '/b')

  def test_cat_error4(self):
    self.assertRaises(BadFileType, self.repo.cat, self.main_branch, '/c')

  def test_readlink1(self):
    result = self.repo.readlink(self.main_branch, 'b')
    correct = 'a'
    self.assertEqual(result, correct)

  def test_readlink2(self):
    result = self.repo.readlink(self.main_branch, '/b')
    correct = 'a'
    self.assertEqual(result, correct)

  def test_readlink3(self):
    result = self.repo.readlink(self.main_branch, 'c/d/f')
    correct = 'e'
    self.assertEqual(result, correct)

  def test_readlink4(self):
    result = self.repo.readlink(self.main_branch, '/c/d/f')
    correct = 'e'
    self.assertEqual(result, correct)

  def test_readlink_error1(self):
    self.assertRaises(PathDoesNotExist, self.repo.readlink, self.main_branch, '/z')

  def test_readlink_error2(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.main_branch, '/a')

  def test_readlink_error3(self):
    self.assertRaises(PathDoesNotExist, self.repo.readlink, self.main_branch, '/b/')

  def test_readlink_error4(self):
    self.assertRaises(BadFileType, self.repo.readlink, self.main_branch, '/c')

  def test_log_head(self):
    result = self.repo.log(revrange=self.main_branch)
    self.assertIsInstance(result, CommitLogEntry)
    self.assertEqual(result.rev, self.rev1)

  def test_log_rev(self):
    result = self.repo.log(revrange=self.rev1)
    self.assertIsInstance(result, CommitLogEntry)
    self.assertEqual(result.rev, self.rev1)

class GitBasicTest(GitTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['master']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['master',]
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log_all(self):
    result = self.repo.log()
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 1)
    self.assertIsInstance(result[0], CommitLogEntry)
    self.assertEqual(result[0].rev, self.rev1)

class HgBasicTest(HgTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = ['default']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = ['tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_bookmarks(self):
    result = self.repo.bookmarks()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['default', 'tip']
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_log_all(self):
    result = self.repo.log()
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 1)
    self.assertIsInstance(result[0], CommitLogEntry)
    self.assertEqual(result[0].rev, self.rev1)

class SvnBasicTest(SvnTest, BasicTest):
  def test_branches(self):
    result = self.repo.branches()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_tags(self):
    result = self.repo.tags()
    correct = []
    self.assertEqual(normalize_heads(result), normalize_heads(correct))

  def test_heads(self):
    result = self.repo.heads()
    correct = ['HEAD']
    self.assertEqual(result, correct)

  def test_log_all(self):
    result = self.repo.log()
    self.assertIsInstance(result, list)
    self.assertEqual(len(result), 2)
    self.assertIsInstance(result[0], CommitLogEntry)
    self.assertEqual(result[0].rev, self.rev1)


### TEST CASE: UnrelatedBranchTest ###

class UnrelatedBranchTest(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    yield CreateStandardDirectoryStructure()
    with open(os.path.join(working_path, 'a'), 'w') as f:
      f.write('spoon')
    yield Commit('modify a')
    yield CreateUnrelatedBranch('branch1')
    with open(os.path.join(working_path, 'b'), 'w') as f:
      f.write('fish')
    yield Commit('modify b')

  def test_branches(self):
    result = self.repo.branches()
    correct = map(self.encode_branch, [self.main_branch, 'branch1'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_ancestor(self):
    result = self.repo.ancestor(
      self.encode_branch(self.main_branch),
      self.encode_branch('branch1'))
    correct = None
    self.assertEqual(result, correct)

  def test_main_ls(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [{'name':'a', 'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

  def test_branch1_ls(self):
    result = self.repo.ls(self.encode_branch('branch1'), '/')
    correct = [{'name':'b', 'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))

class GitUnrelatedBranchTest(GitTest, UnrelatedBranchTest): pass
class HgUnrelatedBranchTest(HgTest, UnrelatedBranchTest): pass
class SvnUnrelatedBranchTest(SvnTest, UnrelatedBranchTest): pass


### TEST CASES: BranchTest* ###

def setup_branch_test(test, step):
  """Setup a typical branching scenario for testing.

  step rev tree    branch     message                           ancestor
     1   1   *     (main)     standard directory structure
     2   2   *     (main)     modify a                          1=main
     3   3   |\*   (branch1)  create branch1
         4   | *   (branch1)  modify b
     4   5   * |   (main)     modify c                          2=main
     5   6 */| |   (branch2)  create branch2
         7 * | |   (branch2)  modify c
     6   8 | |\*   (branch1)  merge from main to branch1        3=branch1
     7   9 | | |\* (branch1a) create branch1a
        10 | | | * (branch1a) modify b
     8  11 | | */| (branch1)  reintegrate branch1a into branch1
     9  12 |\* | | (main)     reintegrate branch2 into main     4=main
    10  13 | |\* | (branch1)  merge from main to branch1
    11  14 | | * | (branch1)  modify a
    12  15 | */| | (main)     reintegrate branch1 into main
    13  16 X | | | (branch2)  delete branch2
        17   | | X (branch1a) delete branch1a
        18   | X   (branch1)  delete branch1

  """
  a_path = os.path.join(test.working_path, 'a')
  b_path = os.path.join(test.working_path, 'b')
  c_path = os.path.join(test.working_path, 'c')

  if step < 1: return
  yield CreateStandardDirectoryStructure()

  if step < 2: return
  with open(a_path, 'w') as f: f.write('step 2')
  yield Commit('2: modify a')
  test.ancestor1 = test.getAbsoluteRev()

  if step < 3: return
  yield CreateBranch('branch1')
  with open(b_path, 'w') as f: f.write('step 3')
  yield Commit('4: modify b')

  if step < 4: return
  yield SwitchBranch(test.main_branch)
  with open(c_path, 'w') as f: f.write('step 4')
  yield Commit('5: modify c')
  test.ancestor2 = test.getAbsoluteRev()

  if step < 5: return
  yield CreateBranch('branch2')
  with open(c_path, 'w') as f: f.write('step 5')
  yield Commit('7: modify c')

  if step < 6: return
  yield SwitchBranch('branch1')
  yield Merge(test.main_branch)
  test.ancestor3 = test.getAbsoluteRev()

  if step < 7: return
  yield CreateBranch('branch1a')
  with open(b_path, 'w') as f: f.write('step 7')
  yield Commit('10: modify b')

  if step < 8: return
  yield SwitchBranch('branch1')
  yield ReintegrateMerge('branch1a')

  if step < 9: return
  yield SwitchBranch(test.main_branch)
  yield ReintegrateMerge('branch2')
  test.ancestor4 = test.getAbsoluteRev()

  if step < 10: return
  yield SwitchBranch('branch1')
  yield Merge(test.main_branch)

  if step < 11: return
  with open(a_path, 'w') as f: f.write('step 11')
  yield Commit('14: modify a')

  if step < 12: return
  yield SwitchBranch(test.main_branch)
  yield ReintegrateMerge('branch1')

  if step < 13: return
  yield DeleteBranch('branch2')
  yield DeleteBranch('branch1a')
  yield DeleteBranch('branch1')

### TEST CASE: BranchTestStep3 ###

class BranchTestStep3(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 3):
      yield action

  def test_branches(self):
    result = self.repo.branches()
    correct = map(self.encode_branch, [self.main_branch, 'branch1'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_ancestor_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ancestor(self.main_branch, branch1)
    correct = self.ancestor1
    self.assertEqual(result, correct)

  def test_main(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [{'name':'a', 'type':'f'}]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(self.main_branch, '/a')
    self.assertEqual(result, 'step 2')

  def test_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ls(branch1, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1, '/b')
    self.assertEqual(result, 'step 3')

class GitBranchTestStep3(GitTest, BranchTestStep3): pass
class HgBranchTestStep3(HgTest, BranchTestStep3): pass
class SvnBranchTestStep3(SvnTest, BranchTestStep3): pass

### TEST CASE: BranchTestStep7 ###

class BranchTestStep7(object):
  @classmethod
  def setUpWorkingCopy(cls, working_path):
    for action in setup_branch_test(cls, 7):
      yield action

  def test_branches(self):
    result = self.repo.branches()
    correct = map(self.encode_branch,
                  [self.main_branch, 'branch1', 'branch1a', 'branch2'])
    self.assertEqual(sorted(result), sorted(correct))

  def test_ancestor_main_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ancestor(self.main_branch, branch1)
    correct = self.ancestor2
    self.assertEqual(result, correct)

  def test_ancestor_main_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = self.repo.ancestor(self.main_branch, branch1a)
    correct = self.ancestor2
    self.assertEqual(result, correct)

  def test_ancestor_main_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.repo.ancestor(self.main_branch, branch2)
    correct = self.ancestor2
    self.assertEqual(result, correct)

  def test_ancestor_branch1_branch1a(self):
    branch1 = self.encode_branch('branch1')
    branch1a = self.encode_branch('branch1a')
    result = self.repo.ancestor(branch1, branch1a)
    correct = self.ancestor3
    self.assertEqual(result, correct)

  def test_main(self):
    result = self.repo.ls(self.main_branch, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(self.main_branch, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(self.main_branch, '/c')
    self.assertEqual(result, 'step 4')

  def test_branch1(self):
    branch1 = self.encode_branch('branch1')
    result = self.repo.ls(branch1, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1, '/b')
    self.assertEqual(result, 'step 3')
    result = self.repo.cat(branch1, '/c')
    self.assertEqual(result, 'step 4')

  def test_branch1a(self):
    branch1a = self.encode_branch('branch1a')
    result = self.repo.ls(branch1a, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'b', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch1a, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch1a, '/b')
    self.assertEqual(result, 'step 7')
    result = self.repo.cat(branch1a, '/c')
    self.assertEqual(result, 'step 4')

  def test_branch2(self):
    branch2 = self.encode_branch('branch2')
    result = self.repo.ls(branch2, '/')
    correct = [
      {'name':'a', 'type':'f'},
      {'name':'c', 'type':'f'},
    ]
    self.assertEqual(normalize_ls(result), normalize_ls(correct))
    result = self.repo.cat(branch2, '/a')
    self.assertEqual(result, 'step 2')
    result = self.repo.cat(branch2, '/c')
    self.assertEqual(result, 'step 5')

class GitBranchTestStep7(GitTest, BranchTestStep7): pass
class HgBranchTestStep7(HgTest, BranchTestStep7): pass
class SvnBranchTestStep7(SvnTest, BranchTestStep7): pass


if __name__ == '__main__':
  unittest.main()
