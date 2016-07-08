# coding=utf-8
# Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import logging
import os
import shutil
import subprocess
from abc import abstractproperty
from hashlib import sha1

from pants.engine.fs import Files, PathGlobs
from pants.engine.nodes import Node, Noop, Return, State, TaskNode, Throw, Waiting
from pants.engine.selectors import Select, SelectDependencies
from pants.util.contextutil import open_tar, temporary_dir, temporary_file_path
from pants.util.dirutil import safe_mkdir
from pants.util.objects import datatype


logger = logging.getLogger(__name__)


def _create_snapshot_archive(file_list, step_context):
  logger.debug('snapshotting files: {}'.format(file_list))

  # Constructs the snapshot tar in a temporary location, then fingerprints it and moves it to the final path.
  with temporary_file_path(cleanup=False) as tmp_path:
    with open_tar(tmp_path, mode='w:gz') as tar:
      for file in file_list.dependencies:
        tar.add(os.path.join(step_context.project_tree.build_root, file.path), file.path)
    snapshot = Snapshot(_fingerprint_files_in_tar(file_list, tmp_path))
  tar_location = _snapshot_path(snapshot, step_context.project_tree)

  shutil.move(tmp_path, tar_location)

  return snapshot


def _fingerprint_files_in_tar(file_list, tar_location):
  hasher = sha1()
  with open_tar(tar_location, mode='r:gz') as tar:
    for file in file_list.dependencies:
      hasher.update(file.path)
      hasher.update(tar.extractfile(file.path).read())
  return hasher.hexdigest()


def _snapshot_path(snapshot, project_tree):
  # TODO Create / find snapshot directory via configuration.
  # TODO Consider naming snapshot archive based also on the subject and not just the fingerprint of the contained files.
  archive_dir = os.path.join(project_tree.build_root, '.snapshots')
  safe_mkdir(archive_dir)
  tar_location = os.path.join(archive_dir, '{}.tar'.format(snapshot.fingerprint))
  return tar_location


def _extract_snapshot(step_context, snapshot, checkout, subject):
  with open_tar(_snapshot_path(snapshot, step_context.project_tree), errorlevel=1) as tar:
    tar.extractall(checkout.path)
  logger.debug('extracted {} snapshot to {}'.format(subject, checkout.path))


class Snapshot(datatype('Snapshot', ['fingerprint'])):
  """A snapshot of a collection of files fingerprinted by their contents.

  Snapshots are used to make it easier to isolate process execution by fixing the contents of the files being operated
  on and easing their movement to and from isolated execution sandboxes.
  """


class Binary(datatype('Binary', [])):
  """Binary in the product graph.

  TODO these should use BinaryUtil to find binaries."""

  @abstractproperty
  def bin_path(self):
    pass

  def prefix_of_command(self):
    return tuple([self.bin_path])


class Checkout(datatype('Checkout', ['path'])):
  """Checkout directory of one or more snapshots."""


class SnapshottedProcessRequest(datatype('SnapshottedProcessRequest',
                                         ['args', 'snapshot_subjects', 'directories_to_create'])):
  """Request for execution with binary args and snapshots to extract."""

  def __new__(cls, args, snapshot_subjects=tuple(), directories_to_create=tuple(), **kwargs):
    """

    :param args: Arguments to the binary being run.
    :param snapshot_subjects: Subjects used to request snapshots that will be checked out into the sandbox.
    :param directories_to_create: Directories to ensure exist in the sandbox before execution.
    """
    if not isinstance(args, tuple):
      raise ValueError('args must be a tuple.')
    if not isinstance(snapshot_subjects, tuple):
      raise ValueError('snapshot_subjects must be a tuple.')
    if not isinstance(directories_to_create, tuple):
      raise ValueError('directories_to_create must be a tuple.')
    return super(SnapshottedProcessRequest, cls).__new__(cls, args, snapshot_subjects, directories_to_create, **kwargs)


class SnapshottedProcessResult(datatype('SnapshottedProcessResult', ['stdout', 'stderr', 'exit_code'])):
  """Contains the stdout, stderr and exit code from executing a process."""


class ProcessExecutionNode(datatype('ProcessOrchestrationNode',
                                    ['subject', 'snapshotted_process']),
                           Node):
  """Wraps a process execution, preparing and tearing down the execution environment."""

  is_cacheable = True
  is_inlineable = False
  variants = None

  @property
  def product(self):
    return self.snapshotted_process.product_type

  def step(self, step_context):
    # Create the request from the request callback.
    task_state = step_context.get(self._request_task_node())

    if type(task_state) in (Waiting, Throw):
      return task_state
    elif type(task_state) is Noop:
      return Noop("Couldn't construct process request: {}".format(task_state))
    elif type(task_state) is not Return:
      State.raise_unrecognized(task_state)

    process_request = task_state.value

    # Get the binary.
    binary_state = step_context.get(self._binary_select_node(step_context))
    if type(binary_state) in (Waiting, Throw):
      return binary_state
    elif type(binary_state) is Noop:
      return Noop("Couldn't find binary: {}".format(binary_state))
    elif type(binary_state) is not Return:
      State.raise_unrecognized(binary_state)

    binary_value = binary_state.value

    # If the process requires snapshots, request a checkout with the requested snapshots applied.
    if process_request.snapshot_subjects:
      node = step_context.select_node(SelectDependencies(Snapshot, SnapshottedProcessRequest, 'snapshot_subjects'),
                                      process_request, self.variants)
      state = step_context.get(node)
      if type(state) is not Return:
        return state

      snapshots_and_subjects = zip(state.value, process_request.snapshot_subjects)

      with temporary_dir(cleanup=False) as outdir:
        checkout = Checkout(outdir)

      for snapshot, subject in snapshots_and_subjects:
        _extract_snapshot(step_context, snapshot, checkout, subject)

      # All of the snapshots have been checked out now.
      if process_request.directories_to_create:
        for d in process_request.directories_to_create:
          safe_mkdir(os.path.join(checkout.path, d))
    else:
      # If there are no things to snapshot, then do no snapshotting or checking out and just use the
      # project dir.
      checkout = Checkout(step_context.project_tree.build_root)

    command = binary_value.prefix_of_command() + tuple(process_request.args)
    logger.debug('Running command: "{}" in {}'.format(command, checkout.path))

    popen = subprocess.Popen(command,
                             stderr=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             cwd=checkout.path)
    # TODO At some point, we may want to replace this blocking wait with a timed one that returns
    # some kind of in progress state.
    popen.wait()

    logger.debug('Done running command in {}'.format(checkout.path))

    process_result = SnapshottedProcessResult(popen.stdout.read(), popen.stderr.read(), popen.returncode)

    converted_output = self.snapshotted_process.output_conversion(process_result, checkout)

    # TODO clean up the checkout.

    return Return(converted_output)

  def _binary_select_node(self, step_context):
    return step_context.select_node(Select(self.snapshotted_process.binary_type),
                                    # TODO figure out what these should be
                                    subject=None,
                                    variants=None)

  def _request_task_node(self):
    return TaskNode(subject=self.subject,
                    product=SnapshottedProcessRequest,
                    variants=None,  # TODO figure out what this should be
                    func=self.snapshotted_process.input_conversion,
                    clause=self.snapshotted_process.input_selectors)

  def __repr__(self):
    return 'ProcessOrchestrationNode(subject={}, snapshotted_process={}' \
      .format(self.subject, self.snapshotted_process)

  def __str__(self):
    return repr(self)


class SnapshotNode(datatype('SnapshotNode', ['subject', 'variants']), Node):
  is_inlineable = False
  is_cacheable = True
  product = Snapshot

  @classmethod
  def as_intrinsics(cls):
    return {(Files, Snapshot): cls.create,
            (PathGlobs, Snapshot): cls.create}

  @classmethod
  def create(cls, subject, product_type, variants):
    assert product_type == Snapshot
    return SnapshotNode(subject, variants)

  def step(self, step_context):
    selector = Select(Files)
    node = step_context.select_node(selector, self.subject, self.variants)
    select_state = step_context.get(node)

    if type(select_state) in {Waiting, Noop, Throw}:
      return select_state
    elif type(select_state) is not Return:
      State.raise_unrecognized(select_state)
    file_list = select_state.value

    snapshot = _create_snapshot_archive(file_list, step_context)

    return Return(snapshot)
