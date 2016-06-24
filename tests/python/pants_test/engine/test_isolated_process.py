# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import tarfile
import unittest

from pants.build_graph.address import Address
from pants.engine.engine import LocalSerialEngine
from pants.engine.fs import Dir, Files, PathGlob, PathGlobs, PathRoot
from pants.engine.isolated_process import (Binary, ProcessExecutionNode,  # SnapshotNode,
                                           ProcessOrchestrationNode, Snapshot,
                                           SnapshottedProcessRequest, SnapshottedProcessResult)
from pants.engine.nodes import Node, Noop, Return, State, StepContext, Throw, Waiting
from pants.engine.rule import Rule
from pants.engine.scheduler import SnapshottedProcess
from pants.engine.selectors import Select, SelectLiteral, SelectProjection
from pants.util.contextutil import open_tar, temporary_dir
from pants.util.dirutil import safe_mkdir
from pants.util.objects import datatype
from pants_test.engine.examples.planners import JavaSources
from pants_test.engine.scheduler_test_base import SchedulerTestBase


class FakeClassPath(object):
  pass


class CoolBinary(object):
  pass


class Blah(object):
  pass


def blah_to_request(args):
  pass


def request_to_fake_classpath(args):
  pass


class Concatted(datatype('Concatted', ['value'])):
  pass


class ShellCat(Binary):

  @property
  def bin_path(self):
    return '/bin/cat'


def file_list_to_args_for_cat(files):
  return SnapshottedProcessRequest(args=tuple(f.path for f in files.dependencies))


def process_result_to_concatted(process_result):
  return Concatted(process_result.stdout)


def shell_cat_binary():
  # /bin/cat
  return ShellCat()



class Javac(Binary):
  """
  $ javac -help
  Usage: javac <options> <source files>
  where possible options include:
    -g                         Generate all debugging info
    -g:none                    Generate no debugging info
    -g:{lines,vars,source}     Generate only some debugging info
    -nowarn                    Generate no warnings
    -verbose                   Output messages about what the compiler is doing
    -deprecation               Output source locations where deprecated APIs are used
    -classpath <path>          Specify where to find user class files and annotation processors
    -cp <path>                 Specify where to find user class files and annotation processors
    -sourcepath <path>         Specify where to find input source files
    -bootclasspath <path>      Override location of bootstrap class files
    -extdirs <dirs>            Override location of installed extensions
    -endorseddirs <dirs>       Override location of endorsed standards path
    -proc:{none,only}          Control whether annotation processing and/or compilation is done.
    -processor <class1>[,<class2>,<class3>...] Names of the annotation processors to run; bypasses default discovery process
    -processorpath <path>      Specify where to find annotation processors
    -parameters                Generate metadata for reflection on method parameters
    -d <directory>             Specify where to place generated class files
    -s <directory>             Specify where to place generated source files
    -h <directory>             Specify where to place generated native header files
    -implicit:{none,class}     Specify whether or not to generate class files for implicitly referenced files
    -encoding <encoding>       Specify character encoding used by source files
    -source <release>          Provide source compatibility with specified release
    -target <release>          Generate class files for specific VM version
    -profile <profile>         Check that API used is available in the specified profile
    -version                   Version information
    -help                      Print a synopsis of standard options
    -Akey[=value]              Options to pass to annotation processors
    -X                         Print a synopsis of nonstandard options
    -J<flag>                   Pass <flag> directly to the runtime system
    -Werror                    Terminate compilation if warnings occur
    @<filename>                Read options and filenames from file


  """

  @property
  def bin_path(self):
    return '/usr/bin/javac'

def java_sources_to_javac_args(java_sources):
  return SnapshottedProcessRequest(args=tuple(f for f in java_sources.files))


def javac_bin():
  return Javac()


class SnapshotNode(datatype('SnapshotNode', ['subject']), Node):

  is_inlineable = False
  product = Snapshot
  is_cacheable = True # TODO need to test this somehow.

  def variants(self): # TODO do snapshots need variants? What would that mean?
    pass

  def step(self, step_context):
    selector = Select(Files)
    node = step_context.select_node(selector, self.subject, None)
    dep_state = step_context.get(node)
    dep_values = []
    if type(dep_state) is Waiting:
      return Waiting([node])
    elif type(dep_state) is Return:
      dep_values.append(dep_state.value)
    elif type(dep_state) is Noop:
      if selector.optional:
        dep_values.append(None)
      else:
        return Noop('Was missing (at least) input for {} of {}. Original {}', selector, self.subject, dep_state)
    elif type(dep_state) is Throw:
      # NB: propagate thrown exception directly.
      return dep_state
    else:
      State.raise_unrecognized(dep_state)

    # TODO do something better than this to figure out where snapshots should live.
    snapshot_dir = os.path.join(step_context.project_tree.build_root, 'snapshots')
    safe_mkdir(snapshot_dir)

    result = snapshotting_fn(dep_values[0],
                             snapshot_dir,
                             build_root=step_context.project_tree.build_root)
    return Return(result)



class SnapshottingRule(Rule):
  input_selects = Select(Files)
  output_product_type =Snapshot

  def as_node(self, subject, product_type, variants):
    assert product_type == Snapshot
    # TODO variants
    return SnapshotNode(subject)

def snapshotting_fn(file_list, archive_dir, build_root):
  print('snapshotting for files: {}'.format(file_list))
  # TODO might need some notion of a source root for snapshots.
  tar_location = os.path.join(archive_dir, 'my-tar.tar')
  with open_tar(tar_location, mode='w:gz',) as tar:
    for file in file_list.dependencies:
      tar.add(os.path.join(build_root, file.path), file.path)
  return Snapshot(tar_location)

class ClasspathEntry(datatype('ClasspathEntry', ['path'])):
  """A classpath entry for a subject. This assumes that its the compiled classpath entry, not like, sources on the classpath or something."""


def process_result_to_classpath_entry(args):
  pass


class Checkout(datatype('Checkout', ['path'])):
  pass


class CheckoutNode(datatype('CheckoutNode', ['subject']),Node):
  is_inlineable = True
  product = Checkout
  is_cacheable = True

  def step(self, step_context):
    selector = Select(Snapshot)
    node = step_context.select_node(selector, self.subject, None)
    dep_state = step_context.get(node)
    dep_values = []
    if type(dep_state) is Waiting:
      return Waiting([node])
    elif type(dep_state) is Return:
      dep_values.append(dep_state.value)
    elif type(dep_state) is Noop:
      if selector.optional:
        dep_values.append(None)
      else:
        return Noop('Was missing (at least) input for {} of {}. Original {}', selector, self.subject, dep_state)
    elif type(dep_state) is Throw:
      # NB: propagate thrown exception directly.
      return dep_state
    else:
      State.raise_unrecognized(dep_state)

    with temporary_dir(cleanup=False) as outdir:
      with open_tar(dep_values[0].archive, errorlevel=1) as tar:
        tar.extractall(outdir)
      return Return(Checkout(outdir))



  def variants(self):
    pass


class CheckoutingRule(Rule):
  input_selects = Select(Snapshot)
  output_product_type = Checkout

  def as_node(self, subject, product_type, variants):
    return CheckoutNode(subject)


class SomeTest(SchedulerTestBase, unittest.TestCase):

  def test_orchestration_node_in_a_unit_like_way(self):
    class FakeStepContext(object):

      def get(self, n):
        return Waiting([n])
    # What's the goal here?
    # I think I shouldn't work on this one while I'm not sure I like this layout
    # Lesse
    node = ProcessOrchestrationNode('MySubject', SnapshottedProcess(FakeClassPath,
                                                                    CoolBinary,
                                                                    (Select(Blah),),
                                                                    blah_to_request,
                                                                    request_to_fake_classpath
                                                             ))
    context = FakeStepContext()
    waiting = node.step(context)

    self.assertEquals(1, len(waiting.dependencies))



    #self.fail()

  # TODO test if orchestration node's input creation fns returns None, the orchestration should Noop.

  def test_gather_snapshot_of_pathglobs(self):
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))
    scheduler = self.mk_scheduler(tasks=[
                                    SnapshottingRule()
                                  ],
                                  # Not sure what to put here yet.
                                  goals=None,

                                  project_tree=project_tree)

    request = scheduler.execution_request([Snapshot], [PathGlobs.create('', rglobs=['fs_test/a/b/*'])])
    LocalSerialEngine(scheduler).reduce(request)

    root_entries = scheduler.root_entries(request).items()
    self.assertEquals(1, len(root_entries))
    state = self.assertFirstEntryIsReturn(root_entries, scheduler)
    snapshot = state.value

    with open_tar(snapshot.archive, errorlevel=1) as tar:
      self.assertEqual(['fs_test/a/b/1.txt', 'fs_test/a/b/2'],
                       [tar_info.path for tar_info in tar.getmembers()])

  def test_checkout_pathglobs(self):
    # a checkout is a dir with a bunch of snapshots in it
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))
    scheduler = self.mk_scheduler(tasks=[SnapshottingRule(), CheckoutingRule()],
                                  # Not sure what to put here yet.
                                  goals=None,
                                  project_tree=project_tree)

    request = scheduler.execution_request([Checkout],
                                          [PathGlobs.create('', rglobs=['fs_test/a/b/*'])])
    LocalSerialEngine(scheduler).reduce(request)

    root_entries = scheduler.root_entries(request).items()
    self.assertEquals(1, len(root_entries))
    state = self.assertFirstEntryIsReturn(root_entries, scheduler)
    checkout = state.value

    # NB arguably this could instead be a translation of a Checkout into Files or Paths
    # Not sure if I want that at this point
    # I think snapshot likely needs to be intrinsic / keyed off of output product + subject type.
    # But, I'm not super sure.
    for i in ['fs_test/a/b/1.txt', 'fs_test/a/b/2']:
      self.assertTrue(os.path.exists(os.path.join(checkout.path, i)),
                      'Expected {} to exist in {} but did not'.format(i, checkout.path))

  def test_integration_simple_concat_test(self):
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))

    scheduler = self.mk_scheduler(tasks=[
                                    # subject to files / product of subject to files for snapshot.
                                    SnapshottedProcess(product_type=Concatted,
                                                       binary_type=ShellCat,
                                                       input_selectors=(Select(Files),),
                                                       input_conversion=file_list_to_args_for_cat,
                                                       output_conversion=process_result_to_concatted),
                                    [ShellCat, [], shell_cat_binary]
                                  ],
                                  # Not sure what to put here yet.
                                  goals=None,

                                  project_tree=project_tree)

    request = scheduler.execution_request([Concatted],
                                          [PathGlobs.create('', rglobs=['fs_test/a/b/*'])])
    LocalSerialEngine(scheduler).reduce(request)

    root_entries = scheduler.root_entries(request).items()
    self.assertEquals(1, len(root_entries))
    state = self.assertFirstEntryIsReturn(root_entries, scheduler)
    concatted = state.value

    self.assertEqual(Concatted('one\ntwo\n'), concatted)

  def assertFirstEntryIsReturn(self, root_entries, scheduler):
    root, state = root_entries[0]
    self.assertReturn(state, root, scheduler)
    return state

  def test_process_exec_node_directly(self):
    # process exec node needs to be able to do nailgun
    binary = ShellCat() # Not 100% sure I like this here TODO make it better.
    process_request = SnapshottedProcessRequest(['fs_test/a/b/1.txt', 'fs_test/a/b/2'])
    node = ProcessExecutionNode(binary, process_request)

    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))
    context = StepContext(None, project_tree, tuple(), False)

    step_result = node.step(context)

    self.assertEqual(Return(SnapshottedProcessResult(stdout='one\ntwo\n', stderr='')), step_result)

  def test_more_complex_thing(self):
    # maybe I could
    # request a snapshot of writing the concatted std out to a file
    # Or, I could make a new concat process that dumps the stdout to a file in the checked out dir
    # and snapshots it
    return # skipping rn
    sources = JavaSources(name='somethingorother',
                          files=['scheduler_inputs/src/java/simple/Simple.java'])
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))

    scheduler = self.mk_scheduler(tasks=[

                                    # subject to files / product of subject to files for snapshot.
                                    SnapshottedProcess(ClasspathEntry,
                                                       Javac, (Select(JavaSources),Select(JavaOutputDir)),
                                                       java_sources_to_javac_args, process_result_to_classpath_entry),
                                    [Javac, [], javac_bin]
                                  ],
                                  # Not sure what to put here yet.
                                  goals=None,

                                  project_tree=project_tree)

    # maybe we want a snapshot of the classpathentry?
    request = scheduler.execution_request(
      #[Snapshot.of(ClasspathEntry)],
      [ClasspathEntry],
                                          [sources])
    LocalSerialEngine(scheduler).reduce(request)

    root_entries = scheduler.root_entries(request).items()
    self.assertEquals(1, len(root_entries))
    state = self.assertFirstEntryIsReturn(root_entries, scheduler)
    classpath_entry = state.value
    self.assertIsInstance(classpath_entry, ClasspathEntry)
    self.assertTrue(os.path.exists(os.path.join(classpath_entry.path, 'simple', 'Simple.class')))

  def assertReturn(self, state, root, scheduler):
    is_return = isinstance(state, Return)
    if is_return:
      return
    else:
      self.fail('Expected a Return, but found a {}. trace below:\n{}'
                .format(state, '\n'.join(scheduler.product_graph.trace(root))))
      #
    #try:
    #  self.assertReturn(state)
    #except AssertionError:
    #  if isinstance(state, Noop):
    #    for d in scheduler.product_graph.dependencies_of(root):
    #      print(d)
    #      print(scheduler.product_graph.state(d))
    #    # print(tuple(scheduler.product_graph.dependencies_of(root)))
    #    raise
