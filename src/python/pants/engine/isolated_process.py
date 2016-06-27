# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import os
import subprocess
from abc import abstractproperty

from pants.engine.fs import Files
from pants.engine.nodes import Node, Noop, Return, State, TaskNode, Throw, Waiting
from pants.engine.rule import Rule
from pants.engine.selectors import Select
from pants.util.contextutil import open_tar, temporary_dir
from pants.util.dirutil import safe_mkdir
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

  def prefix_of_command(self):
    return tuple([self.bin_path])


class Checkout(datatype('Checkout', ['path'])):
  pass


class SnapshottedProcessRequest(
  datatype('SnapshottedProcessRequest', ['args', 'snapshot_subjects'])):
  """
  args - arguments to the binary being run.
  snapshot_subjects - subjects for requesting snapshots that will be checked out into the work dir for the process
  """

  def __new__(cls, args, snapshot_subjects=tuple(), **kwargs):
    # TODO test the below things.
    if not isinstance(args, tuple):
      args = tuple(args)
    if not isinstance(snapshot_subjects, tuple):
      snapshot_subjects = tuple(snapshot_subjects)
    return super(SnapshottedProcessRequest, cls).__new__(cls, args, snapshot_subjects, **kwargs)


class SnapshottedProcessResult(datatype('SnapshottedProcessResult', ['stdout', 'stderr'])):
  pass


class UncacheableTaskNode(TaskNode):
  """A task node that isn't cacheable."""
  is_cacheable = False


class ProcessExecutionNode(datatype('ProcessNode', ['binary', 'process_request', 'checkout']),
                           Node):
  # TODO how will this work with
  # TODO - nailgun?
  # TODO - snapshots?

  is_cacheable = False
  is_inlineable = False

  def __eq__(self, other):
    if self is other:
      return True
      # Compare types and fields.
    return type(other) == type(self) and (
    self.binary == other.binary and self.process_request == other.process_request)

  def __hash__(self):
    return hash((type(self), self.binary, self.process_request))

  def step(self, step_context):
    command = self.binary.prefix_of_command() + self.process_request.args
    print('command {}'.format(command))
    popen = subprocess.Popen(command,
                             stderr=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             # TODO, clean this up so that it's a bit better abstracted
                             cwd=self.checkout.path)

    # Not sure why I'm doing this at this point. It might be necessary later though.
    handler_popen = SubprocessProcessHandler(popen)
    handler_popen.wait()
    print('DONE with process exec in {}'.format(self.checkout.path))

    return Return(
      SnapshottedProcessResult(popen.stdout.read(), popen.stderr.read())
    )


class ProcessOrchestrationNode(
  datatype('ProcessOrchestrationNode', ['subject', 'snapshotted_process']), Node):
  is_cacheable = True
  is_inlineable = False

  @property
  def product(self):
    return self.snapshotted_process.product_type

  def step(self, step_context):
    # Create task node with selects for input types and input_to_process_request.

    # ...

    # collect appropriate snapshots
    #
    # create checkout of snapshots
    # ...
    # Run process
    # maybe resnapshot something in the checkout
    # tear down checkout
    #

    # We could change how this works so that instead of
    # something something
    # project into snapshots something
    task_state = step_context.get(self._request_task_node())
    if type(task_state) in (Waiting, Throw):
      return task_state
    elif type(task_state) is Noop:
      print('nooooooping 1')
      return Noop('couldnt find something {} while looking for {}'.format(task_state,
                                                                          self.snapshotted_process.input_selectors))
      # return task_state # Maybe need a specific one where
    elif type(task_state) is not Return:
      State.raise_unrecognized(task_state)
    # elif type(task_state) is Return:
    process_request = task_state.value

    print("=============select inputs and map to process request finished!")

    binary_state = step_context.get(self._binary_select_node(step_context))
    if type(binary_state) in (Waiting, Throw):
      return binary_state
    elif type(binary_state) is Noop:
      print('nooooooping 2')
      return Noop('couldnt find something {} while looking for {}'.format(binary_state,
                                                                          self.snapshotted_process.binary_type))
    elif type(binary_state) is not Return:
      State.raise_unrecognized(binary_state)
    # elif type(binary_state) is Return:
    binary_value = binary_state.value

    print("========binary type found!")

    if process_request.snapshot_subjects:
      # There's probably a way to convert this into either a dependency op or a projection
      open_node = OpenCheckoutNode(process_request)
      state_open = step_context.get(open_node)
      if type(state_open) in (Waiting, Throw, Noop):
        return state_open  # maybe ought to have a separate noop clause
      # else is return
      checkout = state_open.value

      sses = []
      for ss in process_request.snapshot_subjects:
        ss_apply_node = ApplyCheckoutNode(ss, checkout)
        ss_state = step_context.get(ss_apply_node)
        if type(ss_state) is Return:
          sses.append(ss_state.value)
        elif type(ss_state) in (Waiting, Throw, Noop):  # maybe ought to have a separate noop clause
          return ss_state
          # All of the snapshots have been checked out now.


    else:
      # If there are no things to snapshot, then do no snapshotting or checking out and just use the project dir.
      checkout = Checkout(step_context.project_tree.build_root)

    exec_node = self._process_exec_node(binary_value, process_request, checkout)
    exec_state = step_context.get(exec_node)
    if type(exec_state) in (Waiting, Throw):
      print('waiting or throwing for exec {}'.format(exec_state))
      return exec_state
    elif type(exec_state) is Noop:
      return Noop('couldnt find something {} while looking for {}'.format(exec_state, binary_value))
      # return exec_state # Maybe need a specific one where
    elif type(exec_state) is not Return:
      State.raise_unrecognized(exec_state)
    # elif type(exec_state) is Return:
    process_result = exec_state.value

    converted_output = self.snapshotted_process.output_conversion(process_result, checkout)

    # TODO here: rm the checkout

    return Return(converted_output)

  def _process_exec_node(self, binary_value, process_request, checkout):
    return ProcessExecutionNode(binary_value, process_request, checkout)

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
    return 'ProcessOrchestrationNode(subject={}, snapshotted_process={}' \
      .format(self.subject, self.snapshotted_process)

  def __str__(self):
    return repr(self)


class SnapshotNode(datatype('SnapshotNode', ['subject']), Node):
  is_inlineable = False
  product = Snapshot
  is_cacheable = True  # TODO need to test this somehow.

  def variants(self):  # TODO do snapshots need variants? What would that mean?
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
        return Noop('Was missing (at least) input for {} of {}. Original {}', selector,
                    self.subject, dep_state)
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
  output_product_type = Snapshot

  def as_node(self, subject, product_type, variants):
    assert product_type == Snapshot
    # TODO variants
    return SnapshotNode(subject)


def snapshotting_fn(file_list, archive_dir, build_root):
  print('snapshotting for files: {}'.format(file_list))
  # TODO might need some notion of a source root for snapshots.
  tar_location = os.path.join(archive_dir, 'my-tar.tar')
  with open_tar(tar_location, mode='w:gz', ) as tar:
    for file in file_list.dependencies:
      tar.add(os.path.join(build_root, file.path), file.path)
  return Snapshot(tar_location)


class CheckoutNode(datatype('CheckoutNode', ['subject']), Node):
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
        return Noop('Was missing (at least) input for {} of {}. Original {}', selector,
                    self.subject, dep_state)
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


class OpenCheckoutNode(datatype('CheckoutNode', ['subject']), Node):
  is_inlineable = False
  product = Checkout
  is_cacheable = True

  def step(self, step_context):
    print('yay constructing checkout for {}'.format(self.subject))
    with temporary_dir(cleanup=False) as outdir:
      return Return(Checkout(outdir))

  def variants(self):
    pass


class ApplyCheckoutNode(datatype('CheckoutNode', ['subject', 'checkout']), Node):
  is_inlineable = False
  product = Checkout
  is_cacheable = False

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
        return Noop('Was missing (at least) input for {} of {}. Original {}', selector,
                    self.subject, dep_state)
    elif type(dep_state) is Throw:
      # NB: propagate thrown exception directly.
      return dep_state
    else:
      State.raise_unrecognized(dep_state)

    with open_tar(dep_values[0].archive, errorlevel=1) as tar:
      tar.extractall(self.checkout.path)
    print('extracted {} snapshot to {}'.format(self.subject, self.checkout.path))
    return Return('DONE')

  def variants(self):
    pass


class CheckoutingRule(Rule):
  input_selects = Select(Snapshot)
  output_product_type = Checkout

  def as_node(self, subject, product_type, variants):
    return CheckoutNode(subject)


class MultisnapshotCheckoutingRule(CheckoutingRule):
  pass
