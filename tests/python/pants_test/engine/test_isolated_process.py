# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import unittest

from pants.build_graph.address import Address
from pants.engine.engine import LocalSerialEngine
from pants.engine.fs import Dir, Files
from pants.engine.isolated_process import (Binary, ProcessExecutionNode, ProcessOrchestrationNode,
                                           Snapshot, SnapshotNode, SnapshottedProcessRequest,
                                           SnapshottedProcessResult)
from pants.engine.nodes import Noop, Return, StepContext
from pants.engine.scheduler import SnapshottedProcess
from pants.engine.selectors import Select
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


class ClasspathEntry(datatype('ClasspathEntry', ['path'])):
  """A classpath entry for a subject. This assumes that its the compiled classpath entry, not like, sources on the classpath or something."""


def process_result_to_classpath_entry(args):
  pass


class SomeTest(SchedulerTestBase, unittest.TestCase):

  def test_snapshot(self):
    #snapshot ops
    # unpack snapshot
    #
    SnapshotNode

    pass

  def test_blah(self):
    return
    node = ProcessOrchestrationNode('MySubject', SnapshottedProcess(FakeClassPath,
                                                             CoolBinary,
                                                                    (Select(Blah),),
                                                              blah_to_request,
                                                             request_to_fake_classpath
                                                             ))
    context = StepContext(None, None, tuple(), False)
    waiting = node.step(context)

    self.assertEquals(1, len(waiting.dependencies))



    self.fail()

  # TODO test if orchestration node's input creation fns returns None, the orchestration should Noop.

  def test_gather_snapshot_of_dir(self):
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))

    scheduler = self.mk_scheduler(tasks=[
                                    # subject to files / product of subject to files for snapshot.
                                    #SnapshottedProcess(Concatted,
                                    #                   ShellCat, (Select(Files),),
                                    #                   file_list_to_args_for_cat, process_result_to_concatted),
                                    #[ShellCat, [], shell_cat_binary]
      # Snapshotting is intrinsic
                                  ],
                                  # Not sure what to put here yet.
                                  goals=None,

                                  project_tree=project_tree)

    request = scheduler.execution_request([Snapshot], [Dir('fs_test/a/b')])
    LocalSerialEngine(scheduler).reduce(request)

    root_entries = scheduler.root_entries(request).items()
    self.assertEquals(1, len(root_entries))
    root, state = root_entries[0]
    self.assertIsInstance(state, Return)
    concatted = state.value


  def test_integration_simple_concat_test(self):
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))

    scheduler = self.mk_scheduler(tasks=[
                                    # subject to files / product of subject to files for snapshot.
                                    SnapshottedProcess(Concatted,
                                                       ShellCat, (Select(Files),),
                                                       file_list_to_args_for_cat, process_result_to_concatted),
                                    [ShellCat, [], shell_cat_binary]
                                  ],
                                  # Not sure what to put here yet.
                                  goals=None,

                                  project_tree=project_tree)

    request = scheduler.execution_request([Concatted], [Dir('fs_test/a/b')])
    LocalSerialEngine(scheduler).reduce(request)

    root_entries = scheduler.root_entries(request).items()
    self.assertEquals(1, len(root_entries))
    root, state = root_entries[0]
    try:
      self.assertIsInstance(state, Return)
    except AssertionError:
      if isinstance(state, Noop):
        for d in scheduler.product_graph.dependencies_of(root):
          print(d)
          print(scheduler.product_graph.state(d))
        #print(tuple(scheduler.product_graph.dependencies_of(root)))
        raise
    concatted = state.value

    self.assertEqual(Concatted('one\ntwo\n'), concatted)

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
    root, state = root_entries[0]
    self.assertIsInstance(state, Return)
    classpath_entry = state.value
    self.assertIsInstance(classpath_entry, ClasspathEntry)
    self.assertTrue(os.path.exists(os.path.join(classpath_entry.path, 'simple', 'Simple.class')))
