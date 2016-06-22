# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import subprocess
from abc import abstractproperty

from pants.engine.fs import Dir, PathGlob
from pants.engine.nodes import Node, Noop, Return, State, TaskNode, Throw, Waiting
from pants.engine.rule import Rule
from pants.engine.selectors import Select
from pants.util.objects import datatype
from pants.util.process_handler import SubprocessProcessHandler


class Snapshot(datatype('Snapshot', ['archive'])):
  """Holds a reference to the archived snapshot of something."""
  pass


class Binary(datatype('Binary', [])):
  """Represents a binary in the product graph. Still working out the contract here."""

  @abstractproperty
  def bin_path(self):
    pass


class SnapshottedProcessRequest(datatype('SnapshottedProcessRequest', ['args'])):
  def __new__(cls, args, **kwargs):
    if not isinstance(args, tuple):
      args = tuple(args)
    return super(SnapshottedProcessRequest, cls).__new__(cls, args, **kwargs)


class SnapshottedProcessResult(datatype('SnapshottedProcessResult', ['stdout', 'stderr'])):
  pass


class SnapshotRule(Rule):
  """A rule for constructing snapshot nodes."""

  def as_node(self, subject, product_type, variants):
    return CreateSnapshotNode(subject, product_type)

class CreateSnapshotNode(datatype('CreateSnapshotNode', ['subject', 'product']), Node):
  """Represents the op for creating a snapshot from some kind of file or path like collection."""

  is_cacheable=False
  is_inlineable=False

  @classmethod
  def as_intrinsic_rules(cls):
    # subject type, product type
    #Files
    #Dirs - not sure if it should use dirs, since what would it collect?
    #PathGlob - obvi
    return {
    PathGlob
      (Dir, Snapshot): SnapshotRule()

    }

  def step(self, step_context):
    # get the root dir somehow. For now just get it off of the project_tree
    step_context.project_tree
    # maybe we could construct a tmp "project_tree" for a checked out snapshot? :)
    pass


class CheckoutSnapshotNode(datatype('Checkout', [])):
  pass


class UncacheableTaskNode(TaskNode):
  """A task node that isn't cacheable."""
  is_cacheable = False


class SnapshotNode(datatype('SnapshotNode', ['binary', 'process_request']), Node):
  is_cacheable = False
  is_inlineable = False

  def step(self, step_context):
    raise NotImplementedError('Not used')
    #return Return(
    #  SnapshottedProcessResult('blah', 'stdout', 'stderr')
    #)


class ProcessExecutionNode(datatype('ProcessNode', ['binary', 'process_request']), Node):
  # TODO how will this work with
  # TODO - nailgun?
  # TODO - snapshots?

  is_cacheable = False
  is_inlineable = False

  def step(self, step_context):
    popen = subprocess.Popen(tuple([self.binary.bin_path]) + self.process_request.args,
                             stderr=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             # TODO, clean this up so that it's a bit better abstracted
                             cwd=step_context.project_tree.build_root)

    # Not sure why I'm doing this at this point. It might be necessary later though.
    handler_popen = SubprocessProcessHandler(popen)
    handler_popen.wait()

    return Return(
      SnapshottedProcessResult(popen.stdout.read(), popen.stderr.read())
    )


class ProcessOrchestrationNode(datatype('ProcessOrchestrationNode', ['subject', 'snapshotted_process']), Node):
  is_cacheable = True
  is_inlineable = False

  def _snapshot_node(self):
    return SnapshotNode()

  def step(self, step_context):
    # Create task node with selects for input types and input_to_process_request.

    task_state = step_context.get(self._request_task_node())
    if type(task_state) in (Waiting, Throw):
      return task_state
    elif type(task_state) is Noop:
      print('nooooooping 1')
      return Noop('couldnt find something {} while looking for {}'.format(task_state, self.snapshotted_process.input_selectors))
      #return task_state # Maybe need a specific one where
    elif type(task_state) is not Return:
      State.raise_unrecognized(task_state)
    #elif type(task_state) is Return:
    process_request = task_state.value

    print("=============select inputs and map to process request finished!")

    binary_state = step_context.get(self._binary_select_node(step_context))
    if type(binary_state) in (Waiting, Throw):
      return binary_state
    elif type(binary_state) is Noop:
      print('nooooooping 2')
      return Noop('couldnt find something {} while looking for {}'.format(binary_state, self.snapshotted_process.binary_type))
    elif type(binary_state) is not Return:
      State.raise_unrecognized(binary_state)
    #elif type(binary_state) is Return:
    binary_value = binary_state.value

    print("========binary type found!")

    exec_node = self._process_exec_node(binary_value, process_request)
    exec_state = step_context.get(exec_node)
    if type(exec_state) in (Waiting, Throw):
      return exec_state
    elif type(exec_state) is Noop:
      return Noop('couldnt find something {} while looking for {}'.format(exec_state, binary_value))
      #return exec_state # Maybe need a specific one where
    elif type(exec_state) is not Return:
      State.raise_unrecognized(exec_state)
    #elif type(exec_state) is Return:
    process_result = exec_state.value

    return Return(self.snapshotted_process.output_conversion(process_result))

  def _process_exec_node(self, binary_value, process_request):
    return ProcessExecutionNode(binary_value, process_request)

  def _binary_select_node(self, step_context):
    return step_context.select_node(Select(self.snapshotted_process.binary_type),
                                    # TODO figure out what these should be
                                    subject=None,
                                    variants=None)

  def _request_task_node(self):
    return UncacheableTaskNode(subject=self.subject,
                    product=SnapshottedProcessRequest,
                    variants=None,  # TODO figure out what this should be
                    func=self.snapshotted_process.input_conversion,
                    clause=self.snapshotted_process.input_selectors)

  def __repr__(self):
    return 'ProcessOrchestrationNode(subject={}, snapshotted_process={}'\
      .format(self.subject, self.snapshotted_process)

  def __str__(self):
    return repr(self)
