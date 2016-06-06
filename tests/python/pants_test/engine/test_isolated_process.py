# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import unittest

from pants.engine.engine import LocalSerialEngine
from pants.engine.fs import Dir, Files
from pants.engine.isolated_process import (ProcessOrchestrationNode, SnapshotNode,
                                           SnapshottedProcessRequest)
from pants.engine.nodes import Return, StepContext
from pants.engine.scheduler import SnapshottedProcess
from pants.engine.selectors import Select
from pants.util.objects import datatype
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


class ShellCat(object):
  pass


def file_list_to_args_for_cat(files):
  print('A')
  print('A')
  print('A')
  print('A')
  print('A')
  print('A')
  print(files)
  return SnapshottedProcessRequest(tuple(f.path for f in files.dependencies), 'maybe-dont-need-this')


def process_result_to_concatted(process_result):
  return Concatted(process_result.stdout)


def shell_cat_binary():
  return ShellCat()


class SomeTest(SchedulerTestBase, unittest.TestCase):

  def test_snapshot(self):
    #snapshot ops
    # unpack snapshot
    #
    SnapshotNode

    pass

  def test_blah(self):
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

  # TODO cases
  #   if output task raises, should be Throw
  #   if input task raises should be Throw
  #   if task returns None, the noop should come from the tasknode, maybe
  #
  def test_integration(self):
    project_tree = self.mk_fs_tree(os.path.join(os.path.dirname(__file__), 'examples'))

    scheduler = self.mk_scheduler(tasks=[
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
    self.assertIsInstance(state, Return)
    concatted = state.value
    self.assertIsInstance(concatted, Concatted)

    self.assertEqual('one\ntwo', concatted.value)
